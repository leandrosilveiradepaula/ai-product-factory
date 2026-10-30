from __future__ import annotations

from dataclasses import dataclass

from .change_set_store import ChangeSetIntegrationItem,SupabaseChangeSetStore
from .github_rest import GitHubPullRequest,GitHubRestAdapter
from .commit_provenance import provenance_commit_message
from .pinned_nonproduction_target import PinnedNonproductionTarget
from .journey_delivery_binding import JourneyBinding, JourneyBindingBlocked


@dataclass(frozen=True)
class ChangeSetIntegrationResult:
    change_set_id:str
    wave:int
    status:str
    candidate_commit:str
    changed_files:tuple[str,...]
    pull_request:GitHubPullRequest|None=None


class ChangeSetIntegrator:
    def __init__(self,*,github:GitHubRestAdapter,store:SupabaseChangeSetStore)->None:
        self.github=github;self.store=store

    def _recover_committed_candidate(
        self, *, item: ChangeSetIntegrationItem, files: dict[str, str], message: str,
    ) -> str | None:
        """Recognize one exact commit left by a crash before DB completion.

        A recovered commit is admissible only when the branch head has the
        expected parent, the complete Factory provenance message, and every
        declared file has the exact verified content.  Any concurrent or
        ambiguous branch movement remains blocked rather than being rebased or
        overwritten.
        """
        candidate = self.github.get_branch_sha(item.integration_branch)
        try:
            observed_message, parents = self.github.get_commit_provenance(candidate)
        except (RuntimeError, ValueError):
            return None
        if observed_message != message or parents != (item.candidate_commit,):
            return None
        # A forged commit can preserve the expected parent, trailer and files
        # while introducing extra unauthorized paths. Prove the whole delta.
        self.github.verify_integration_commit_tree(
            parent_sha=item.candidate_commit, candidate_sha=candidate,
            expected_paths=tuple(files),
        )
        for path, expected in files.items():
            if self.github.get_file_text(path, ref=candidate) != expected:
                return None
        return candidate

    def integrate(self,item:ChangeSetIntegrationItem)->ChangeSetIntegrationResult:
        if not item.work_units:
            raise ValueError("integration requires completed work units")
        if not isinstance(item.current_wave,int) or isinstance(item.current_wave,bool) or item.current_wave<1:
            raise ValueError("integration wave must be positive")
        if not isinstance(item.integration_branch,str) or not item.integration_branch.startswith("factory/"):
            raise ValueError("integration branch must be factory-scoped")
        if not isinstance(item.project_key,str) or not item.project_key.strip():
            raise ValueError("integration project identity is missing")
        if not isinstance(item.repository,str) or item.repository.count("/")!=1:
            raise ValueError("integration repository identity is invalid")
        if not isinstance(item.source_commit,str) or not item.source_commit.strip():
            raise ValueError("integration source identity is missing")
        if not isinstance(item.change_set_id,str) or not item.change_set_id.strip():
            raise ValueError("integration change set identity is missing")
        if not isinstance(item.candidate_commit,str) or not item.candidate_commit.strip():
            raise ValueError("integration candidate identity is missing")
        if len(item.work_units)>100:
            raise ValueError("integration exceeds work unit limit")
        if item.journey_binding is not None:
            try:
                binding=JourneyBinding.parse(item.journey_binding,project_id=str(item.project_id or ""),
                    request_id=str(item.request_id or ""),repository=item.repository)
            except JourneyBindingBlocked as exc:
                raise PermissionError(str(exc)) from exc
            if item.source_commit != binding.source_commit or item.integration_branch != binding.integration_branch:
                raise PermissionError("integration V2 binding differs from claimed Change Set")
            if self.github.get_branch_sha(binding.source_ref) != binding.source_commit:
                raise PermissionError("integration V2 source reference changed")
            # PR base and Preview promotion must agree. A Preview-only
            # integration is not a production release candidate.
            destination=binding.implementation_pr_base_ref()
        elif item.project_kind == "existing":
            target=PinnedNonproductionTarget.parse(item.delivery_target,repository=item.repository)
            if item.source_commit != target.sha:
                raise PermissionError("integration source differs from pinned candidate")
            target.verify(self.github)
            destination=target.branch
        elif item.project_kind == "platform":
            if item.delivery_target not in (None,{}):
                raise PermissionError("platform integration cannot use an imported-project target")
            if getattr(self.github,"repository",item.repository)!=item.repository:
                raise PermissionError("platform integration GitHub repository identity mismatch")
            # Fail before GitHub mutations if protected production main moved
            # since the Change Set was bound. Never silently rebase a result
            # produced by a model against a different source tree.
            if self.github.get_branch_sha("main") != item.source_commit:
                raise PermissionError("platform integration main advanced; reconcile exact SHA")
            destination="main"
        elif item.project_kind in (None,"","greenfield"):
            destination="main"
        else:
            raise PermissionError("unrecognized project kind")
        owners={}
        files={}
        pending_reads=[]
        for unit in item.work_units:
            if not isinstance(unit,dict):
                raise ValueError("integration work unit must be an object")
            if str(unit.get("base_commit") or "")!=item.candidate_commit:
                raise RuntimeError("work unit base commit does not match current integration candidate")
            output=str(unit.get("output_commit") or "")
            if not output:
                raise RuntimeError("work unit output commit is missing")
            if output==item.candidate_commit:
                raise RuntimeError("work unit output equals candidate base")
            task_key=unit.get("plan_task_key")
            if not isinstance(task_key,str) or not task_key.strip():
                raise ValueError("integration task identity is missing")
            paths=unit.get("changed_files")
            if isinstance(paths,(tuple,list)) and len(paths)>200:
                raise ValueError("integration work unit exceeds path limit")
            if not isinstance(paths,(tuple,list)) or not paths:
                raise ValueError("integration work unit must declare changed files")
            for path in paths:
                if not isinstance(path,str) or not path.strip():
                    raise ValueError("integration changed path must be a nonempty string")
                path=str(path)
                if path in owners:
                    raise RuntimeError(f"Change Set file conflict: {path} changed by {owners[path]} and {task_key}")
                owners[path]=task_key
                pending_reads.append((path,output))

        if len(pending_reads)>500:
            raise ValueError("integration exceeds total file limit")
        if not pending_reads:
            raise RuntimeError("integration produced no files")
        for path,output in pending_reads:
            content=self.github.get_file_text(path,ref=output)
            if not isinstance(content,str):
                raise RuntimeError("integration source file is not text")
            files[path]=content
        # Do not create or reset an integration branch until every unit is verified.
        message=provenance_commit_message(
            f"integrate(change-set): {item.change_set_id[:8]} wave {item.current_wave}",
            {"Factory-Change-Set":item.change_set_id,"Factory-Wave":str(item.current_wave)},
        )
        try:
            self.github.ensure_branch_at_sha(item.integration_branch,item.candidate_commit)
        except RuntimeError as exc:
            # A retry may observe a commit that was written immediately before
            # an interruption.  Recover only a complete, exact receipt; any
            # other moved branch is still an unsafe candidate drift.
            candidate=self._recover_committed_candidate(item=item,files=files,message=message)
            if candidate is None:
                raise RuntimeError("integration branch moved without recoverable Factory commit") from exc
        else:
            candidate=self.github.commit_files(item.integration_branch,files,message=message)
        if not isinstance(candidate,str) or not candidate.strip():
            raise RuntimeError("integration commit returned no candidate")
        if candidate==item.candidate_commit:
            raise RuntimeError("integration commit did not advance candidate")
        # Verify the branch still points at the commit we are about to persist.
        if self.github.get_branch_sha(item.integration_branch)!=candidate:
            raise RuntimeError("integration branch moved before candidate persistence")
        completed=self.store.complete_integration(
            item=item,candidate_commit=candidate,changed_files=tuple(sorted(files)),
        )
        if not isinstance(completed,dict):
            raise RuntimeError("integration completion returned an invalid result")
        status=completed.get("status")
        if status not in ("building","review_ready"):
            raise RuntimeError("integration completion returned an unsupported status")
        if completed.get("change_set_id")!=item.change_set_id:
            raise RuntimeError("integration completion changed Change Set identity")
        if completed.get("candidate_commit")!=candidate:
            raise RuntimeError("integration completion changed candidate commit")
        completed_wave=completed.get("current_wave")
        if isinstance(completed_wave,bool) or not isinstance(completed_wave,int):
            raise RuntimeError("integration completion returned an invalid wave")
        if status=="building" and completed_wave<=item.current_wave:
            raise RuntimeError("integration completion did not advance the wave")
        if status=="review_ready" and completed_wave!=item.current_wave:
            raise RuntimeError("integration completion changed final wave")
        repairs=completed.get("repair_jobs_integrated")
        if isinstance(repairs,bool) or not isinstance(repairs,int) or repairs<0:
            raise RuntimeError("atomic integration completion missing repair outcome")
        pull_request=None
        if status=="review_ready":
            marker=f"Factory change set: {item.change_set_id}"
            issue=self.github.find_open_issue_containing(marker)
            if issue is None:
                issue=self.github.create_issue(
                    title=f"[factory] Change Set {item.change_set_id[:8]} - {item.project_key}",
                    body=f"{marker}\n\nIntegrated release candidate produced by the Factory. Production merge remains human-gated.",
                )
            pull_request=self.github.find_open_pull_request_containing(marker)
            if pull_request is None:
                pull_request=self.github.create_pull_request(
                    title=f"feat(factory): Change Set {item.change_set_id[:8]}",
                    body=f"{marker}\n\nIntegrated candidate: {candidate}\n\nDo not merge until CI, specialist review and Preview evidence pass.",
                    head=item.integration_branch,base=destination,
                )
            if item.project_kind in ("existing","platform") and getattr(pull_request,"base_ref",None) != destination:
                raise PermissionError("Change Set PR base must match the verified destination branch")
            if not isinstance(pull_request.number,int) or isinstance(pull_request.number,bool) or pull_request.number<1:
                raise RuntimeError("integration PR number is invalid")
            if pull_request.head_sha!=candidate:
                raise RuntimeError("final Change Set PR head does not match integrated candidate")
            if not isinstance(issue.number,int) or isinstance(issue.number,bool) or issue.number<1:
                raise RuntimeError("integration issue number is invalid")
            release=self.store.prepare_release(
                item=item,issue_number=issue.number,issue_url=issue.html_url,
                pr_number=pull_request.number,candidate_commit=candidate,branch=item.integration_branch,
            )
            if not isinstance(release,dict) or release.get("status")!="ci_pending":
                raise RuntimeError("integration release returned an invalid status")
            if release.get("change_set_id")!=item.change_set_id:
                raise RuntimeError("integration release changed Change Set identity")
            release_run_id=release.get("release_run_id")
            if not isinstance(release_run_id,str) or not release_run_id.strip():
                raise RuntimeError("integration release missing durable run")
            status="ci_pending"
        return ChangeSetIntegrationResult(
            change_set_id=item.change_set_id,wave=item.current_wave,status=status,
            candidate_commit=candidate,changed_files=tuple(sorted(files)),pull_request=pull_request,
        )
