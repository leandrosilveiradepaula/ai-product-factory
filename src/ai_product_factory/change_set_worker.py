from __future__ import annotations

from dataclasses import dataclass,replace
from typing import Protocol

from .change_set_store import ChangeSetBinding,SupabaseChangeSetStore
from .execution_worker import DirectExecutionItem,ImplementationArtifact,ImplementationProducer
from .github_rest import GitHubRestAdapter
from .impact_engine import SupabaseImpactEngine
from .work_unit_context import build_context_packet,enforce_write_scopes
from .provenance_replay import SupabaseProvenanceStore,build_run_provenance
from .commit_provenance import provenance_commit_message


@dataclass(frozen=True)
class ChangeSetWorkResult:
    run_id:str
    change_set_id:str
    work_unit_id:str
    output_commit:str
    changed_files:tuple[str,...]
    base_commit:str
    branch:str


class ChangeSetBuilderWorker:
    def __init__(self,*,github:GitHubRestAdapter,store:SupabaseChangeSetStore,producer:ImplementationProducer,
                 impact_engine:SupabaseImpactEngine|None=None,provenance:SupabaseProvenanceStore|None=None,
                 execution_route:str="direct")->None:
        self.github=github;self.store=store;self.producer=producer;self.impact_engine=impact_engine or SupabaseImpactEngine()
        self.provenance=provenance or SupabaseProvenanceStore();self.execution_route=execution_route

    def execute(self,item:DirectExecutionItem)->ChangeSetWorkResult:
        if item.human_gate_required:
            raise PermissionError("task requires human approval before implementation")
        if not item.change_set_id or not item.work_unit_id:
            raise ValueError("Change Set identity is required")
        observed_main=self.github.get_branch_sha("main")
        frozen_source=self.store.frozen_source_commit(item.change_set_id)
        source_commit=frozen_source or observed_main
        integration_branch=f"factory/change-set-{item.change_set_id[:8]}"
        binding=self.store.bind_source(
            run_id=item.run_id,source_commit=source_commit,
            integration_branch=integration_branch,work_branch=item.branch,
        )
        self.github.ensure_branch_at_sha(item.branch,binding.base_commit)
        impact=self.impact_engine.analyze_run(
            project_key=item.project_key,task_id=item.task_id,run_id=item.run_id,change_set_id=item.change_set_id
        )
        source=self.store.context_source(item.run_id)
        packet=build_context_packet(
            source=source,impact=impact.as_context(),base_commit=binding.base_commit,branch=item.branch,
        )
        self.store.record_context(run_id=item.run_id,packet_hash=packet.sha256,packet=packet.as_dict())
        provenance=build_run_provenance(
            run_id=item.run_id,project_key=item.project_key,route=self.execution_route,
            agent_key=str(source.get("agent_key") or "") or None,context_packet=packet.as_dict(),
            team_plan={"version":source.get("team_plan_version")} if source.get("team_plan_version") is not None else None,
            project_manifest=source.get("project_manifest") if isinstance(source.get("project_manifest"),dict) else {},
            candidate_commit=binding.base_commit,
        )
        self.provenance.record(run_id=item.run_id,snapshot=provenance)
        write_scopes=tuple(packet.payload["repository"]["write_scopes"])
        item=replace(
            item,impact_context=impact.as_context(),base_commit=binding.base_commit,
            context_packet=packet.as_dict(),write_scopes=write_scopes,
        )
        self.store.set_repair_status(run_id=item.run_id,status="running")
        artifact=self.producer.produce(item)
        if not artifact.files:raise ValueError("implementation producer returned no files")
        enforce_write_scopes(artifact.files.keys(),write_scopes)
        commit_message=provenance_commit_message(artifact.commit_message,{
            "Factory-Run":item.run_id,
            "Factory-Change-Set":binding.change_set_id,
            "Factory-Work-Unit":binding.work_unit_id,
            "Factory-Agent":str(source.get("agent_key") or "unknown"),
            "Factory-Context-SHA256":packet.sha256,
        })
        output=self.github.commit_files(item.branch,artifact.files,message=commit_message)
        self.store.complete_work_unit(
            run_id=item.run_id,output_commit=output,changed_files=tuple(sorted(artifact.files)),
        )
        return ChangeSetWorkResult(
            run_id=item.run_id,change_set_id=binding.change_set_id,work_unit_id=binding.work_unit_id,
            output_commit=output,changed_files=tuple(sorted(artifact.files)),base_commit=binding.base_commit,branch=item.branch,
        )
