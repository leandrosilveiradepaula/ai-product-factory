from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Callable
from urllib import error, parse, request

from .github_loop import CIState
from .github_auth import resolve_github_token


Transport = Callable[[str, str, dict[str, str], bytes | None], tuple[int, Any]]


class GitHubRequestError(RuntimeError):
    def __init__(self,status:int)->None:
        super().__init__(f"GitHub request failed with HTTP {status}")
        self.status=status


class GitHubCapabilityError(RuntimeError):
    def __init__(self,capability:str,detail:str)->None:
        super().__init__(detail)
        self.capability=capability


def _default_transport(method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, Any]:
    req = request.Request(url, data=body, headers=headers, method=method)
    with request.urlopen(req, timeout=30) as response:
        raw = response.read().decode("utf-8")
        return response.status, json.loads(raw) if raw else None


@dataclass(frozen=True)
class GitHubIssue:
    number: int
    title: str
    body: str
    html_url: str


@dataclass(frozen=True)
class GitHubPullRequest:
    number: int
    head_sha: str
    html_url: str
    merged: bool = False
    merge_commit_sha: str | None = None
    state: str = "open"
    head_ref: str | None = None
    base_ref: str | None = None
    head_repository: str | None = None


@dataclass(frozen=True)
class GitHubCheckFailure:
    name: str
    conclusion: str
    details_url: str | None = None
    summary: str | None = None


class GitHubRestAdapter:
    """Server-side GitHub REST adapter used by the autonomous loop."""

    def __init__(
        self,
        *,
        repository: str,
        token: str | None = None,
        api_url: str = "https://api.github.com",
        transport: Transport | None = None,
    ) -> None:
        if "/" not in repository:
            raise ValueError("repository must be in owner/name form")
        self.repository = repository
        self.token = resolve_github_token(repository, explicit_token=token)
        self.api_url = api_url.rstrip("/")
        self.transport = transport or _default_transport
        self.last_ci_evidence_source: str | None = None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _call(self, method: str, path: str, *, query: dict[str, str] | None = None, payload: Any = None) -> Any:
        suffix = "?" + parse.urlencode(query) if query else ""
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        try:
            status, data = self.transport(method, f"{self.api_url}{path}{suffix}", self._headers(), body)
        except error.HTTPError as exc:
            raise GitHubRequestError(exc.code) from exc
        if status < 200 or status >= 300:
            raise GitHubRequestError(status)
        return data

    def create_issue(self, *, title: str, body: str) -> GitHubIssue:
        row = self._call("POST", f"/repos/{self.repository}/issues", payload={"title": title, "body": body})
        return GitHubIssue(row["number"], row["title"], row.get("body") or "", row["html_url"])

    def find_open_issue_containing(self, marker: str) -> GitHubIssue | None:
        if not marker.strip():
            raise ValueError("marker cannot be empty")
        query = f'repo:{self.repository} is:issue is:open in:body "{marker}"'
        rows = self._call("GET", "/search/issues", query={"q": query, "per_page": "10"}).get("items", [])
        for row in rows:
            if "pull_request" in row:
                continue
            body = row.get("body") or ""
            if marker in body:
                return GitHubIssue(row["number"], row["title"], body, row["html_url"])
        return None

    def find_open_pull_request_containing(self, marker: str) -> GitHubPullRequest | None:
        if not marker.strip():
            raise ValueError("marker cannot be empty")
        query = f'repo:{self.repository} is:pr is:open in:body "{marker}"'
        rows = self._call("GET", "/search/issues", query={"q": query, "per_page": "10"}).get("items", [])
        for row in rows:
            if "pull_request" not in row:
                continue
            body = row.get("body") or ""
            if marker in body:
                return self.get_pull_request(int(row["number"]))
        return None

    def get_issue(self, issue_number: int) -> GitHubIssue:
        row = self._call("GET", f"/repos/{self.repository}/issues/{issue_number}")
        if "pull_request" in row:
            raise ValueError(f"#{issue_number} is a pull request, not an issue")
        return GitHubIssue(row["number"], row["title"], row.get("body") or "", row["html_url"])

    def get_branch_sha(self, branch: str) -> str:
        encoded = parse.quote(branch, safe="")
        row = self._call("GET", f"/repos/{self.repository}/git/ref/heads/{encoded}")
        return row["object"]["sha"]

    def create_branch(self, branch: str, *, base_branch: str = "main") -> str:
        base_sha = self.get_branch_sha(base_branch)
        self._call("POST", f"/repos/{self.repository}/git/refs",
                   payload={"ref": f"refs/heads/{branch}", "sha": base_sha})
        return base_sha

    def create_branch_at_sha(self, branch: str, sha: str) -> str:
        if not sha.strip():
            raise ValueError("sha is required")
        self._call("POST", f"/repos/{self.repository}/git/refs",
                   payload={"ref": f"refs/heads/{branch}", "sha": sha})
        return sha

    def ensure_branch_at_sha(self, branch: str, sha: str) -> str:
        try:
            current=self.get_branch_sha(branch)
        except GitHubRequestError as exc:
            if exc.status!=404:
                raise
            try:
                return self.create_branch_at_sha(branch,sha)
            except GitHubRequestError as create_exc:
                if create_exc.status not in {409,422}:
                    raise
                current=self.get_branch_sha(branch)
        if current!=sha:
            raise RuntimeError(f"branch {branch} does not match expected candidate SHA")
        return current

    def get_file_text(self, path: str, *, ref: str) -> str:
        row=self._call("GET",f"/repos/{self.repository}/contents/{parse.quote(path,safe='/')}",query={"ref":ref})
        if row.get("type")!="file" or row.get("encoding")!="base64":
            raise RuntimeError(f"GitHub path is not a base64 file: {path}")
        return base64.b64decode(str(row.get("content") or "").replace("\n","")).decode("utf-8")

    def commit_files(self, branch: str, files: dict[str, str], *, message: str) -> str:
        if not files:
            raise ValueError("files cannot be empty")
        base_sha = self.get_branch_sha(branch)
        commit = self._call("GET", f"/repos/{self.repository}/git/commits/{base_sha}")
        base_tree_sha = commit["tree"]["sha"]

        tree = []
        for path, content in files.items():
            blob = self._call("POST", f"/repos/{self.repository}/git/blobs",
                              payload={"content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
                                       "encoding": "base64"})
            tree.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})

        new_tree = self._call("POST", f"/repos/{self.repository}/git/trees",
                              payload={"base_tree": base_tree_sha, "tree": tree})
        new_commit = self._call("POST", f"/repos/{self.repository}/git/commits",
                                payload={"message": message, "tree": new_tree["sha"], "parents": [base_sha]})
        self._call("PATCH", f"/repos/{self.repository}/git/refs/heads/{parse.quote(branch, safe='')}",
                   payload={"sha": new_commit["sha"], "force": False})
        return new_commit["sha"]

    def create_pull_request(self, *, title: str, body: str, head: str, base: str = "main") -> GitHubPullRequest:
        row = self._call("POST", f"/repos/{self.repository}/pulls",
                         payload={"title": title, "body": body, "head": head, "base": base, "draft": False})
        return GitHubPullRequest(
            number=row["number"],
            head_sha=row["head"]["sha"],
            html_url=row["html_url"],
            merged=bool(row.get("merged",False)),
            merge_commit_sha=row.get("merge_commit_sha"),
            state=str(row.get("state") or "open"),
            head_ref=row.get("head",{}).get("ref"),
            base_ref=row.get("base",{}).get("ref"),
            head_repository=(row.get("head",{}).get("repo") or {}).get("full_name"),
        )

    def get_pull_request(self, pr_number: int) -> GitHubPullRequest:
        row = self._call("GET", f"/repos/{self.repository}/pulls/{pr_number}")
        return GitHubPullRequest(
            number=row["number"],
            head_sha=row["head"]["sha"],
            html_url=row["html_url"],
            merged=bool(row.get("merged",False)),
            merge_commit_sha=row.get("merge_commit_sha"),
            state=str(row.get("state") or "open"),
            head_ref=row.get("head",{}).get("ref"),
            base_ref=row.get("base",{}).get("ref"),
            head_repository=(row.get("head",{}).get("repo") or {}).get("full_name"),
        )

    def get_pull_request_files(self, pr_number: int) -> tuple[str, ...]:
        rows = self._call("GET", f"/repos/{self.repository}/pulls/{pr_number}/files", query={"per_page": "100"})
        return tuple(str(row["filename"]) for row in rows if row.get("filename"))

    def get_pull_request_file_details(self, pr_number: int) -> tuple[dict[str, Any], ...]:
        rows = self._call("GET", f"/repos/{self.repository}/pulls/{pr_number}/files", query={"per_page": "100"})
        return tuple({
            "filename": str(row.get("filename") or ""),
            "status": str(row.get("status") or ""),
            "patch": str(row.get("patch") or ""),
            "additions": int(row.get("additions") or 0),
            "deletions": int(row.get("deletions") or 0),
        } for row in rows if row.get("filename"))


    def _fine_grained_ci_evidence(self, head_sha: str) -> tuple[list[dict], list[dict]]:
        try:
            workflow_payload = self._call(
                "GET",
                f"/repos/{self.repository}/actions/runs",
                query={"head_sha": head_sha, "per_page": "100"},
            )
            status_payload = self._call(
                "GET",
                f"/repos/{self.repository}/commits/{head_sha}/status",
            )
        except GitHubRequestError as exc:
            if exc.status in {403, 404}:
                raise GitHubCapabilityError(
                    "ci_evidence",
                    "GitHub CI evidence is unavailable: check-runs are not accessible and the "
                    "fine-grained fallback requires Actions: read plus Commit statuses: read",
                ) from exc
            raise
        workflows = workflow_payload.get("workflow_runs", []) if isinstance(workflow_payload, dict) else []
        statuses = status_payload.get("statuses", []) if isinstance(status_payload, dict) else []
        return list(workflows), list(statuses)

    @staticmethod
    def _ci_state_from_fine_grained_evidence(workflows: list[dict], statuses: list[dict]) -> CIState:
        if not workflows:
            return CIState.PENDING
        passing = {"success", "neutral", "skipped"}
        if any(str(run.get("status") or "") != "completed" for run in workflows):
            return CIState.PENDING
        if any(str(run.get("conclusion") or "") not in passing for run in workflows):
            return CIState.FAILURE
        status_states = {str(item.get("state") or "") for item in statuses}
        if status_states & {"error", "failure"}:
            return CIState.FAILURE
        if status_states and status_states - {"success"}:
            return CIState.PENDING
        return CIState.SUCCESS

    def _check_runs_or_fine_grained_evidence(self, head_sha: str) -> tuple[str, list[dict], list[dict]]:
        try:
            checks = self._call(
                "GET",
                f"/repos/{self.repository}/commits/{head_sha}/check-runs",
                query={"per_page": "100"},
            ).get("check_runs", [])
        except GitHubRequestError as exc:
            if exc.status != 403:
                raise
            workflows, statuses = self._fine_grained_ci_evidence(head_sha)
            self.last_ci_evidence_source = "github_actions_statuses"
            return self.last_ci_evidence_source, workflows, statuses
        self.last_ci_evidence_source = "github_checks"
        return self.last_ci_evidence_source, list(checks), []

    def get_ci_state(self, pr_number: int) -> CIState:
        pr = self.get_pull_request(pr_number)
        source, primary, statuses = self._check_runs_or_fine_grained_evidence(pr.head_sha)
        if source == "github_actions_statuses":
            return self._ci_state_from_fine_grained_evidence(primary, statuses)
        checks = primary
        if not checks or any(check.get("status") != "completed" for check in checks):
            return CIState.PENDING
        passing = {"success", "neutral", "skipped"}
        if any(check.get("conclusion") not in passing for check in checks):
            return CIState.FAILURE
        return CIState.SUCCESS

    def get_failed_checks(self, pr_number: int) -> tuple[GitHubCheckFailure, ...]:
        pr = self.get_pull_request(pr_number)
        source, primary, statuses = self._check_runs_or_fine_grained_evidence(pr.head_sha)
        passing = {"success", "neutral", "skipped"}
        failures = []
        if source == "github_actions_statuses":
            for run in primary:
                conclusion = str(run.get("conclusion") or "")
                if str(run.get("status") or "") != "completed" or conclusion in passing:
                    continue
                failures.append(
                    GitHubCheckFailure(
                        name=str(run.get("name") or "github-actions"),
                        conclusion=conclusion or "failure",
                        details_url=run.get("html_url"),
                        summary=f"GitHub Actions workflow concluded {conclusion or 'failure'}",
                    )
                )
            for status in statuses:
                state = str(status.get("state") or "")
                if state not in {"error", "failure"}:
                    continue
                failures.append(
                    GitHubCheckFailure(
                        name=str(status.get("context") or "commit-status"),
                        conclusion=state,
                        details_url=status.get("target_url"),
                        summary=status.get("description"),
                    )
                )
            return tuple(failures)
        for check in primary:
            if check.get("status") != "completed" or check.get("conclusion") in passing:
                continue
            output = check.get("output") or {}
            failures.append(
                GitHubCheckFailure(
                    name=check.get("name") or "unnamed-check",
                    conclusion=check.get("conclusion") or "failure",
                    details_url=check.get("details_url"),
                    summary=output.get("summary") or output.get("title"),
                )
            )
        return tuple(failures)

    def close_issue(self, issue_number: int) -> None:
        self._call("PATCH", f"/repos/{self.repository}/issues/{issue_number}",
                   payload={"state": "closed", "state_reason": "completed"})
