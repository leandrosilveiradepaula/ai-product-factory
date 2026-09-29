from __future__ import annotations

from dataclasses import dataclass,replace
from typing import Protocol

from .change_set_store import ChangeSetBinding,SupabaseChangeSetStore
from .execution_worker import DirectExecutionItem,ImplementationArtifact,ImplementationProducer
from .github_rest import GitHubRestAdapter
from .impact_engine import SupabaseImpactEngine


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
    def __init__(self,*,github:GitHubRestAdapter,store:SupabaseChangeSetStore,producer:ImplementationProducer,impact_engine:SupabaseImpactEngine|None=None)->None:
        self.github=github;self.store=store;self.producer=producer;self.impact_engine=impact_engine or SupabaseImpactEngine()

    def execute(self,item:DirectExecutionItem)->ChangeSetWorkResult:
        if item.human_gate_required:
            raise PermissionError("task requires human approval before implementation")
        if not item.change_set_id or not item.work_unit_id:
            raise ValueError("Change Set identity is required")
        observed_main=self.github.get_branch_sha("main")
        integration_branch=f"factory/change-set-{item.change_set_id[:8]}"
        binding=self.store.bind_source(
            run_id=item.run_id,source_commit=observed_main,
            integration_branch=integration_branch,work_branch=item.branch,
        )
        self.github.ensure_branch_at_sha(item.branch,binding.base_commit)
        impact=self.impact_engine.analyze_run(
            project_key=item.project_key,task_id=item.task_id,run_id=item.run_id,change_set_id=item.change_set_id
        )
        item=replace(item,impact_context=impact.as_context(),base_commit=binding.base_commit)
        artifact=self.producer.produce(item)
        if not artifact.files:raise ValueError("implementation producer returned no files")
        output=self.github.commit_files(item.branch,artifact.files,message=artifact.commit_message)
        self.store.complete_work_unit(
            run_id=item.run_id,output_commit=output,changed_files=tuple(sorted(artifact.files)),
        )
        return ChangeSetWorkResult(
            run_id=item.run_id,change_set_id=binding.change_set_id,work_unit_id=binding.work_unit_id,
            output_commit=output,changed_files=tuple(sorted(artifact.files)),base_commit=binding.base_commit,branch=item.branch,
        )
