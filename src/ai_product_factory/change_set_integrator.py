from __future__ import annotations

from dataclasses import dataclass

from .change_set_store import ChangeSetIntegrationItem,SupabaseChangeSetStore
from .github_rest import GitHubPullRequest,GitHubRestAdapter


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

    def integrate(self,item:ChangeSetIntegrationItem)->ChangeSetIntegrationResult:
        if not item.work_units:
            raise ValueError("integration requires completed work units")
        self.github.ensure_branch_at_sha(item.integration_branch,item.candidate_commit)

        owners={}
        files={}
        for unit in item.work_units:
            if str(unit.get("base_commit") or "")!=item.candidate_commit:
                raise RuntimeError("work unit base commit does not match current integration candidate")
            output=str(unit.get("output_commit") or "")
            if not output:
                raise RuntimeError("work unit output commit is missing")
            task_key=str(unit.get("plan_task_key") or "")
            for path in unit.get("changed_files") or []:
                path=str(path)
                if path in owners:
                    raise RuntimeError(f"Change Set file conflict: {path} changed by {owners[path]} and {task_key}")
                owners[path]=task_key
                files[path]=self.github.get_file_text(path,ref=output)

        if not files:
            raise RuntimeError("integration produced no files")
        candidate=self.github.commit_files(
            item.integration_branch,files,
            message=f"integrate(change-set): {item.change_set_id[:8]} wave {item.current_wave}",
        )
        completed=self.store.complete_integration(
            change_set_id=item.change_set_id,candidate_commit=candidate,
            changed_files=tuple(sorted(files)),
        )
        status=str(completed.get("status") or "")
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
                    head=item.integration_branch,base="main",
                )
            if pull_request.head_sha!=candidate:
                raise RuntimeError("final Change Set PR head does not match integrated candidate")
            self.store.prepare_release(
                change_set_id=item.change_set_id,issue_number=issue.number,issue_url=issue.html_url,
                pr_number=pull_request.number,candidate_commit=candidate,branch=item.integration_branch,
            )
            status="ci_pending"
        return ChangeSetIntegrationResult(
            change_set_id=item.change_set_id,wave=item.current_wave,status=status,
            candidate_commit=candidate,changed_files=tuple(sorted(files)),pull_request=pull_request,
        )
