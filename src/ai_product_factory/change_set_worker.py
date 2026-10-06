from __future__ import annotations

from dataclasses import dataclass,replace
import re
from typing import Protocol

from .change_set_store import ChangeSetBinding,SupabaseChangeSetStore
from .execution_worker import DirectExecutionItem,ImplementationArtifact,ImplementationProducer,ImplementationBlocked
from .github_rest import GitHubRestAdapter
from .impact_engine import SupabaseImpactEngine
from .work_unit_context import build_context_packet,enforce_write_scopes,redact_repository_text
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
    _DISCOVERY_STOP={"application","implementation","remediation","coverage","regression","route","task","change","update","fix","feature","work"}
    _TEXT_EXTENSIONS=(".py",".ts",".tsx",".js",".jsx",".mjs",".cjs",".json",".sql",".md",".yaml",".yml",".toml")

    def __init__(self,*,github:GitHubRestAdapter,store:SupabaseChangeSetStore,producer:ImplementationProducer,
                 impact_engine:SupabaseImpactEngine|None=None,provenance:SupabaseProvenanceStore|None=None,
                 execution_route:str="direct")->None:
        self.github=github;self.store=store;self.producer=producer;self.impact_engine=impact_engine or SupabaseImpactEngine()
        self.provenance=provenance or SupabaseProvenanceStore();self.execution_route=execution_route

    @classmethod
    def _tokens(cls,value:object)->set[str]:
        parts=re.findall(r"[a-z0-9]+",str(value or "").lower())
        return {part for part in parts if len(part)>=3 and part not in cls._DISCOVERY_STOP}

    @staticmethod
    def _normalize_path(value:object)->str:
        return str(value or "").strip().replace("\\","/").removeprefix("./").strip("/")

    @classmethod
    def _is_test_scope(cls,value:str)->bool:
        tokens=cls._tokens(value)
        return bool(tokens & {"test","tests","testing","spec","specs","regression"})

    @classmethod
    def _governance_paths(cls,paths:tuple[str,...])->tuple[str,...]:
        preferred=("AGENTS.md","docs/codex/CURRENT_TASK.md")
        return tuple(path for path in preferred if path in paths)

    @classmethod
    def _score_path(cls,path:str,tokens:set[str])->int:
        lower=path.lower()
        score=0
        for token in tokens:
            if token in lower:
                score+=3 if f"/{token}/" in f"/{lower}/" else 1
        if lower.endswith((".ts",".tsx",".js",".jsx",".py")):
            score+=1
        if lower.startswith(("docs/","documentation/")):
            score-=1
        return score

    def _resolved_repository_context(self,*,source:dict,base_commit:str)->tuple[dict,tuple[str,...]]:
        assignment=dict(source.get("assignment") if isinstance(source.get("assignment"),dict) else {})
        explicit=assignment.get("context_paths") if isinstance(assignment.get("context_paths"),list) else []
        all_paths=self.github.list_file_paths(ref=base_commit)
        governance=self._governance_paths(all_paths)

        if explicit:
            context_paths=[self._normalize_path(path) for path in explicit]
        else:
            task=source.get("task") if isinstance(source.get("task"),dict) else {}
            raw_scopes=assignment.get("scope_keys") if isinstance(assignment.get("scope_keys"),list) else []
            tokens=set()
            for value in (
                source.get("plan_task_key"),task.get("title"),task.get("description"),
                " ".join(str(x) for x in (task.get("acceptance_criteria") or [])),
                " ".join(str(x) for x in raw_scopes),
            ):
                tokens.update(self._tokens(value))
            ranked=[
                (self._score_path(path,tokens),path)
                for path in all_paths
                if path.endswith(self._TEXT_EXTENSIONS) and path not in governance
            ]
            ranked=[row for row in ranked if row[0]>0]
            ranked.sort(key=lambda row:(-row[0],len(row[1]),row[1]))
            context_paths=[path for _,path in ranked[:8]]
            if not context_paths:
                raise RuntimeError("repository context discovery found no relevant files; replan with explicit context_paths")

        context_paths=list(dict.fromkeys([*governance,*context_paths]))
        if len(context_paths)>12:
            raise ValueError("too many repository context paths")

        raw_scopes=assignment.get("scope_keys") if isinstance(assignment.get("scope_keys"),list) else []
        resolved_scopes=[]
        semantic_scopes=[]
        for raw in raw_scopes:
            scope=self._normalize_path(raw)
            if not scope:
                continue
            prefix=scope[:-3].rstrip("/") if scope.endswith("/**") else scope.rstrip("/")
            if scope=="." or any(path==prefix or path.startswith(prefix+"/") for path in all_paths):
                resolved_scopes.append(scope)
            else:
                semantic_scopes.append(scope)

        editable_context=[path for path in context_paths if path not in governance]
        for semantic in semantic_scopes:
            if self._is_test_scope(semantic):
                semantic_tokens=self._tokens(semantic)-{"test","tests","testing","spec","specs","regression"}
                test_matches=[
                    path for path in all_paths
                    if ("test" in path.lower() or "spec" in path.lower())
                    and (not semantic_tokens or any(token in path.lower() for token in semantic_tokens))
                    and path.endswith(self._TEXT_EXTENSIONS)
                ]
                if test_matches:
                    resolved_scopes.extend(test_matches[:6])
                else:
                    conventional=next((root for root in ("test","tests") if any(path.startswith(root+"/") for path in all_paths)),None)
                    if conventional:
                        resolved_scopes.append(conventional+"/**")
                    else:
                        raise RuntimeError(f"semantic test scope could not be resolved safely: {semantic}")
            else:
                semantic_tokens=self._tokens(semantic)
                matches=[
                    path for path in editable_context
                    if not semantic_tokens or any(token in path.lower() for token in semantic_tokens)
                ]
                if not matches:
                    matches=editable_context[:1] if len(editable_context)==1 else []
                if not matches:
                    raise RuntimeError(f"semantic write scope could not be resolved safely: {semantic}")
                resolved_scopes.extend(matches)

        resolved_scopes=list(dict.fromkeys(resolved_scopes))
        if not resolved_scopes:
            raise PermissionError("work unit has no safely resolved write scopes")

        assignment["scope_keys"]=resolved_scopes
        assignment["context_paths"]=context_paths
        enriched=dict(source)
        enriched["assignment"]=assignment
        return enriched,tuple(context_paths)

    def _repository_snapshot(self,*,source:dict,base_commit:str)->dict[str,str]:
        assignment=source.get("assignment") if isinstance(source.get("assignment"),dict) else {}
        paths=assignment.get("context_paths") if isinstance(assignment.get("context_paths"),list) else []
        if len(paths)>12:
            raise ValueError("too many repository context paths")
        snapshot={}
        total=0
        for raw in paths:
            path=str(raw).strip().replace("\\","/").removeprefix("./")
            if not path or path.startswith("/") or path.startswith("../") or "/../" in path:
                raise ValueError("invalid repository context path")
            text=redact_repository_text(self.github.get_file_text(path,ref=base_commit))
            if len(text.encode("utf-8"))>32768:
                raise ValueError("repository context file too large")
            total+=len(text.encode("utf-8"))
            if total>131072:
                raise ValueError("repository context snapshot too large")
            snapshot[path]=text
        return snapshot

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
        source,_=self._resolved_repository_context(source=source,base_commit=binding.base_commit)
        snapshot=self._repository_snapshot(source=source,base_commit=binding.base_commit)
        if not snapshot:
            raise RuntimeError("repository context preflight produced an empty snapshot")
        packet=build_context_packet(
            source=source,impact=impact.as_context(),base_commit=binding.base_commit,branch=item.branch,
            repository_snapshot=snapshot,
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
        try:
            artifact=self.producer.produce(item)
        except Exception as exc:
            self.store.block_work_unit(
                run_id=item.run_id,
                reason=f"{type(exc).__name__}: {str(exc)}",
                blocker_type="implementation_producer_error",
            )
            raise
        if artifact.blocked_reason:
            self.store.block_work_unit(
                run_id=item.run_id,
                reason=artifact.blocked_reason,
                blocker_type="repository_governance",
            )
            raise ImplementationBlocked(artifact.blocked_reason)
        if not artifact.files:
            self.store.block_work_unit(
                run_id=item.run_id,
                reason="implementation producer returned no files",
                blocker_type="implementation_producer_error",
            )
            raise ValueError("implementation producer returned no files")
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
