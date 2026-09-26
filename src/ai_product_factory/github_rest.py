from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import Any, Callable
from urllib import parse, request

from .github_loop import CIState


Transport = Callable[[str, str, dict[str, str], bytes | None], tuple[int, Any]]


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
        self.token = token or os.environ.get("GITHUB_TOKEN", "")
        if not self.token:
            raise ValueError("GITHUB_TOKEN is required")
        self.api_url = api_url.rstrip("/")
        self.transport = transport or _default_transport

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
        status, data = self.transport(method, f"{self.api_url}{path}{suffix}", self._headers(), body)
        if status < 200 or status >= 300:
            raise RuntimeError(f"GitHub request failed with HTTP {status}")
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
        return GitHubPullRequest(row["number"], row["head"]["sha"], row["html_url"], bool(row.get("merged",False)), row.get("merge_commit_sha"), str(row.get("state") or "open"))

    def get_pull_request(self, pr_number: int) -> GitHubPullRequest:
        row = self._call("GET", f"/repos/{self.repository}/pulls/{pr_number}")
        return GitHubPullRequest(row["number"], row["head"]["sha"], row["html_url"], bool(row.get("merged",False)), row.get("merge_commit_sha"), str(row.get("state") or "open"))

    def get_ci_state(self, pr_number: int) -> CIState:
        pr = self.get_pull_request(pr_number)
        checks = self._call("GET", f"/repos/{self.repository}/commits/{pr.head_sha}/check-runs",
                            query={"per_page": "100"}).get("check_runs", [])
        if not checks or any(check.get("status") != "completed" for check in checks):
            return CIState.PENDING
        passing = {"success", "neutral", "skipped"}
        if any(check.get("conclusion") not in passing for check in checks):
            return CIState.FAILURE
        return CIState.SUCCESS

    def get_failed_checks(self, pr_number: int) -> tuple[GitHubCheckFailure, ...]:
        pr = self.get_pull_request(pr_number)
        checks = self._call(
            "GET",
            f"/repos/{self.repository}/commits/{pr.head_sha}/check-runs",
            query={"per_page": "100"},
        ).get("check_runs", [])
        passing = {"success", "neutral", "skipped"}
        failures = []
        for check in checks:
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

    def merge_pull_request(self, pr_number: int) -> str:
        pr = self.get_pull_request(pr_number)
        row = self._call("PUT", f"/repos/{self.repository}/pulls/{pr_number}/merge",
                         payload={"merge_method": "squash", "sha": pr.head_sha})
        if not row.get("merged"):
            raise RuntimeError(row.get("message") or "GitHub did not merge the pull request")
        return row["sha"]

    def close_issue(self, issue_number: int) -> None:
        self._call("PATCH", f"/repos/{self.repository}/issues/{issue_number}",
                   payload={"state": "closed", "state_reason": "completed"})
