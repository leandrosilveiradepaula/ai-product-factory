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
    base_sha: str | None = None
    head_repository: str | None = None


@dataclass(frozen=True)
class GitHubCheckFailure:
    name: str
    conclusion: str
    details_url: str | None = None
    summary: str | None = None
    failure_class: str = "unknown"


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
        self.last_ci_evidence_present: bool | None = None
        self.last_ci_workflow_runs: list[dict] = []

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

    def compare_commits(self, previous_commit: str, new_commit: str) -> dict[str, Any]:
        """GitHub comparison evidence; never assume a moved head is trusted."""
        import re
        if not re.fullmatch(r"[0-9a-f]{40}", previous_commit) or not re.fullmatch(r"[0-9a-f]{40}", new_commit):
            raise ValueError("comparison requires full lowercase commit SHAs")
        comparison=self._call("GET",f"/repos/{self.repository}/compare/{previous_commit}...{new_commit}")
        return {"status":comparison.get("status"),"ahead_by":comparison.get("ahead_by"),
                "behind_by":comparison.get("behind_by"),
                "files":[row.get("filename") for row in comparison.get("files",[])]}

    def get_commit_statuses(self, sha: str) -> list[dict[str, Any]]:
        """Read exact commit statuses; feedback checks cannot represent READY."""
        import re
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise ValueError("commit status lookup requires full lowercase SHA")
        data = self._call("GET", f"/repos/{self.repository}/commits/{sha}/status")
        rows = data.get("statuses") if isinstance(data, dict) else None
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise RuntimeError("GitHub commit statuses are not a valid list")
        return rows

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

    def list_file_paths(self, *, ref: str) -> tuple[str, ...]:
        if not ref.strip():
            raise ValueError("ref is required")
        commit=self._call("GET",f"/repos/{self.repository}/git/commits/{parse.quote(ref,safe='')}")
        tree_sha=str((commit.get("tree") or {}).get("sha") or "")
        if not tree_sha:
            raise RuntimeError("GitHub commit did not expose a tree SHA")
        tree=self._call(
            "GET",
            f"/repos/{self.repository}/git/trees/{parse.quote(tree_sha,safe='')}",
            query={"recursive":"1"},
        )
        if bool(tree.get("truncated")):
            raise RuntimeError("GitHub repository tree is truncated")
        rows=tree.get("tree") if isinstance(tree,dict) else None
        if not isinstance(rows,list):
            raise RuntimeError("GitHub repository tree is invalid")
        paths=tuple(
            str(row.get("path") or "")
            for row in rows
            if isinstance(row,dict) and row.get("type")=="blob" and str(row.get("path") or "").strip()
        )
        if len(paths)>10000:
            raise RuntimeError("GitHub repository tree exceeds safe discovery limit")
        return paths

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
            base_sha=row.get("base",{}).get("sha"),
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
            base_sha=row.get("base",{}).get("sha"),
            head_repository=(row.get("head",{}).get("repo") or {}).get("full_name"),
        )

    def _all_pr_file_rows(self, pr_number: int) -> tuple[dict[str, Any], ...]:
        """Read every candidate file; a truncated page must never waive Preview.

        GitHub returns at most 100 files/page and caps its list at 3000.
        The exact 3000-boundary is rejected rather than treated as complete.
        """
        if type(pr_number) is not int or pr_number < 1:
            raise ValueError("invalid pull request number")
        files: list[dict[str, Any]] = []
        seen: set[str] = set()
        for page in range(1, 31):
            rows = self._call(
                "GET", f"/repos/{self.repository}/pulls/{pr_number}/files",
                query={"per_page": "100", "page": str(page)},
            )
            if not isinstance(rows, list) or len(rows) > 100:
                raise RuntimeError("unbounded or malformed PR file response")
            for row in rows:
                if not isinstance(row, dict):
                    raise RuntimeError("malformed PR file record")
                name = row.get("filename")
                if (not isinstance(name, str) or not name or name in seen
                    or name.startswith("/") or "\\" in name
                    or any(p in ("", ".", "..") for p in name.split("/"))):
                    raise RuntimeError("invalid or duplicate PR changed-file path")
                previous = row.get("previous_filename")
                if previous is not None and (
                    not isinstance(previous, str) or not previous
                    or previous.startswith("/") or "\\" in previous
                    or any(p in ("", ".", "..") for p in previous.split("/"))
                ):
                    raise RuntimeError("invalid renamed PR file path")
                seen.add(name)
                files.append(row)
            if len(rows) < 100:
                return tuple(files)
        raise RuntimeError("PR changed-file inventory reached unverified GitHub limit")

    def get_pull_request_files(self, pr_number: int) -> tuple[str, ...]:
        paths: list[str] = []
        for row in self._all_pr_file_rows(pr_number):
            paths.append(row["filename"])
            if row.get("status") == "renamed" and row.get("previous_filename"):
                # Both old and new paths matter for Preview required_paths.
                paths.append(row["previous_filename"])
        return tuple(dict.fromkeys(paths))

    def get_pull_request_file_details(self, pr_number: int) -> tuple[dict[str, Any], ...]:
        return tuple({
            "filename": row["filename"],
            "status": str(row.get("status") or ""),
            "patch": str(row.get("patch") or ""),
            "additions": int(row.get("additions") or 0),
            "deletions": int(row.get("deletions") or 0),
        } for row in self._all_pr_file_rows(pr_number))

    def commit_exists(self, sha: str) -> bool:
        """Check an implementation commit really exists in the target repository."""
        import re
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise ValueError("implementation commit must be an exact lowercase SHA")
        try:
            record = self._call("GET", f"/repos/{self.repository}/commits/{sha}")
        except GitHubRequestError as exc:
            if exc.status == 404:
                return False
            raise
        if not isinstance(record, dict) or record.get("sha") != sha:
            raise RuntimeError("GitHub commit identity mismatch")
        return True


    def _fine_grained_ci_evidence(self, head_sha: str) -> tuple[list[dict], list[dict]]:
        """Require authoritative Actions evidence, even if a Vercel check passed.

        One passing check run is NOT the completion of a multi-job workflow.
        Any missing Actions:read permission must fail closed, never fall back
        to external deployment checks or a favorable combined commit status.
        """
        try:
            workflow_payload = self._call(
                "GET", f"/repos/{self.repository}/actions/runs",
                query={"head_sha": head_sha, "per_page": "100"},
            )
            status_payload = self._call(
                "GET", f"/repos/{self.repository}/commits/{head_sha}/status",
            )
        except GitHubRequestError as exc:
            if exc.status in {403, 404}:
                raise GitHubCapabilityError(
                    "ci_evidence",
                    "GitHub CI evidence requires Actions: read and Commit statuses: read "
                    "for the exact candidate SHA",
                ) from exc
            raise
        if not isinstance(workflow_payload, dict) or not isinstance(status_payload, dict):
            raise RuntimeError("GitHub CI inventory must be an object")
        workflows = workflow_payload.get("workflow_runs")
        statuses = status_payload.get("statuses")
        count = workflow_payload.get("total_count", len(workflows) if isinstance(workflows,list) else None)
        if (
            not isinstance(workflows,list)
            or not isinstance(statuses,list)
            or len(workflows)>100 or isinstance(count,bool)
            or not isinstance(count,int) or count>100 or count<len(workflows)
            or any(not isinstance(row,dict) for row in workflows+statuses)
        ):
            raise RuntimeError("GitHub CI inventory is malformed or exceeds verified 100-run limit")
        return workflows, statuses

    @staticmethod
    def _trusted_workflows(workflows: list[dict], sha: str, branch: str | None) -> list[dict]:
        """Keep the latest *attempt* of each candidate-bound workflow/event.

        Actions lists every run on a SHA, not only the latest one.  A failed
        earlier run must not poison a later successful retry; conversely an
        older success cannot hide a newer pending/failed run.  Different
        workflow files and trigger events retain independent CI obligations.
        """
        latest: dict[tuple, dict] = {}
        for run in workflows:
            if (run.get("head_sha") != sha
                or run.get("event") not in {"pull_request", "push", "workflow_dispatch"}
                or (branch and run.get("head_branch") != branch)):
                continue
            if (not isinstance(run.get("status"), str)
                or not isinstance(run.get("name"), str) or not run["name"].strip()):
                raise RuntimeError("trusted GitHub Actions run has invalid identity")
            workflow_id = run.get("workflow_id")
            path = run.get("path")
            if workflow_id is not None:
                if type(workflow_id) is not int or workflow_id < 1:
                    raise RuntimeError("trusted GitHub Actions workflow ID is invalid")
                identity = ("workflow_id", workflow_id)
            elif path is not None:
                if not isinstance(path, str) or not path.strip():
                    raise RuntimeError("trusted GitHub Actions workflow path is invalid")
                identity = ("path", path.strip())
            else:
                # Older test adapters expose only the display name.  A
                # single record is safe; ambiguous retries fail closed.
                identity = ("name", run["name"].strip())
            key = (run["event"], identity)
            previous = latest.get(key)
            if previous is None:
                latest[key] = run
                continue
            # Never select by response order: the API can return out of order.
            current_id, previous_id = run.get("id"), previous.get("id")
            current_attempt, previous_attempt = run.get("run_attempt", 1), previous.get("run_attempt", 1)
            if (type(current_id) is not int or current_id < 1
                or type(previous_id) is not int or previous_id < 1
                or type(current_attempt) is not int or current_attempt < 1
                or type(previous_attempt) is not int or previous_attempt < 1):
                raise RuntimeError("ambiguous GitHub Actions workflow retry identity")
            if (current_id, current_attempt) == (previous_id, previous_attempt):
                if run != previous:
                    raise RuntimeError("conflicting GitHub Actions workflow retry evidence")
                continue
            if (current_id, current_attempt) > (previous_id, previous_attempt):
                latest[key] = run
        return list(latest.values())

    @staticmethod
    def _latest_ci_checks(checks: list[dict], workflows: list[dict]) -> list[dict]:
        """Bind GitHub Actions job checks to the selected workflow check suites.

        Older attempts and unrelated issue_comment/observer suites on the
        same SHA are not candidate CI evidence.  On reruns in one suite,
        the highest check-run ID is the latest job attempt by its stable name.
        """
        if not workflows:
            return []
        workflow_suites = [run.get("check_suite_id") for run in workflows]
        bound = any(suite is not None for suite in workflow_suites)
        if bound and any(type(suite) is not int or suite < 1 for suite in workflow_suites):
            raise RuntimeError("incomplete GitHub Actions workflow check-suite identity")
        allowed_suites = set(workflow_suites) if bound else set()
        newest: dict[tuple, dict] = {}
        for check in checks:
            suite = check.get("check_suite")
            suite_id = suite.get("id") if isinstance(suite, dict) else None
            if bound:
                if type(suite_id) is not int or suite_id < 1:
                    raise RuntimeError("GitHub Actions job check is missing a verifiable check suite")
                if suite_id not in allowed_suites:
                    continue
            elif suite_id is not None:
                # A partial workflow/check-suite contract cannot certify CI.
                raise RuntimeError("check-suite IDs require workflow-suite evidence")
            name = check.get("name") or "unnamed-check"
            if not isinstance(name, str) or not name.strip():
                raise RuntimeError("GitHub Actions job check has invalid name")
            key = (suite_id, name)
            previous = newest.get(key)
            if previous is None:
                newest[key] = check
                continue
            # Distinct jobs with the same name but no attempt IDs are
            # ambiguous; do not silently allow a green result.
            current_id, previous_id = check.get("id"), previous.get("id")
            if (type(current_id) is not int or current_id < 1
                or type(previous_id) is not int or previous_id < 1):
                raise RuntimeError("ambiguous GitHub Actions check-run retry identity")
            if current_id == previous_id:
                if check != previous:
                    raise RuntimeError("conflicting GitHub Actions check-run retry evidence")
                continue
            if current_id > previous_id:
                newest[key] = check
        return list(newest.values())

    @staticmethod
    def _ci_state_from_fine_grained_evidence(workflows: list[dict], statuses: list[dict]) -> CIState:
        if not workflows:
            return CIState.PENDING
        passing = {"success", "neutral", "skipped"}
        if any(str(run.get("status") or "") != "completed" for run in workflows):
            return CIState.PENDING
        if any(str(run.get("conclusion") or "") not in passing for run in workflows):
            return CIState.FAILURE
        # All workflows being skipped/neutral is NOT evidence that tests ran.
        if not any(run.get("conclusion") == "success" for run in workflows):
            return CIState.PENDING
        status_states = {str(item.get("state") or "") for item in statuses}
        if status_states & {"error", "failure"}:
            return CIState.FAILURE
        if status_states and status_states - {"success"}:
            return CIState.PENDING
        return CIState.SUCCESS

    def _check_runs_or_fine_grained_evidence(
        self, head_sha: str, head_branch: str | None = None
    ) -> tuple[str, list[dict], list[dict]]:
        workflows, statuses = self._fine_grained_ci_evidence(head_sha)
        trusted = self._trusted_workflows(workflows, head_sha, head_branch)
        self.last_ci_workflow_runs = trusted
        # Vercel and other external checks never suppress a needed CI dispatch.
        self.last_ci_evidence_present = bool(trusted)
        try:
            payload = self._call(
                "GET", f"/repos/{self.repository}/commits/{head_sha}/check-runs",
                query={"per_page": "100"},
            )
        except GitHubRequestError as exc:
            if exc.status != 403:
                raise
            self.last_ci_evidence_source = "github_actions_statuses"
            return self.last_ci_evidence_source, trusted, statuses
        checks = payload.get("check_runs") if isinstance(payload,dict) else None
        count = payload.get("total_count",len(checks) if isinstance(checks,list) else None) if isinstance(payload,dict) else None
        if (not isinstance(checks,list) or len(checks)>100
            or isinstance(count,bool) or not isinstance(count,int)
            or count>100 or count<len(checks)
            or any(not isinstance(row,dict) for row in checks)):
            raise RuntimeError("GitHub check-run inventory is malformed or exceeds verified 100-run limit")
        github_actions_checks = [
            check for check in checks
            if isinstance(check.get("app"),dict)
               and check["app"].get("slug") == "github-actions"
               and check.get("head_sha") == head_sha
        ]
        latest_checks = self._latest_ci_checks(github_actions_checks, trusted)
        self.last_ci_evidence_source = "github_checks"
        return self.last_ci_evidence_source, latest_checks, statuses

    def get_ci_state(self, pr_number: int) -> CIState:
        pr = self.get_pull_request(pr_number)
        source, primary, statuses = self._check_runs_or_fine_grained_evidence(pr.head_sha,pr.head_ref)
        # Deployment/Preview commit statuses are not CI jobs. Keep these gates separate.
        workflow_state = self._ci_state_from_fine_grained_evidence(self.last_ci_workflow_runs, [])
        if workflow_state != CIState.SUCCESS:
            return workflow_state
        if source == "github_actions_statuses":
            return workflow_state
        checks = primary
        # Every successful workflow suite must have current job evidence.
        # A missing suite must never be covered by an unrelated green job.
        suites = [run.get("check_suite_id") for run in self.last_ci_workflow_runs]
        if suites and all(type(s) is int and s > 0 for s in suites):
            observed = {
                check["check_suite"]["id"] for check in checks
                if isinstance(check.get("check_suite"), dict)
                and type(check["check_suite"].get("id")) is int
            }
            if any(run["check_suite_id"] not in observed
                   for run in self.last_ci_workflow_runs if run.get("conclusion") == "success"):
                return CIState.PENDING
        if not checks or any(check.get("status") != "completed" for check in checks):
            return CIState.PENDING
        passing = {"success", "neutral", "skipped"}
        if any(check.get("conclusion") not in passing for check in checks):
            return CIState.FAILURE
        if not any(check.get("conclusion") == "success" for check in checks):
            return CIState.PENDING
        return CIState.SUCCESS

    @staticmethod
    def _failure_class(*, name: object, conclusion: object, summary: object) -> str:
        """Classify only from bounded check metadata, never opaque log content."""
        value = " ".join(str(part or "") for part in (name, conclusion, summary)).lower()
        if any(token in value for token in ("permission", "forbidden", "unauthorized", "access denied", "authentication")):
            return "permission"
        if any(token in value for token in ("quota", "rate limit", "billing", "credit", "capacity exhausted")):
            return "quota"
        if any(token in value for token in ("runner", "no hosted runner", "runner unavailable", "runner lost")):
            return "runner"
        if any(token in value for token in ("infrastructure", "service unavailable", "network", "outage", "platform incident")):
            return "infrastructure"
        if any(token in value for token in ("test", "pytest", "lint", "typecheck", "type check", "build", "compile", "coverage")):
            return "code"
        return "unknown"

    @classmethod
    def _check_failure(cls, *, name: object, conclusion: object, details_url: object = None, summary: object = None) -> GitHubCheckFailure:
        safe_name = str(name or "unnamed-check")[:240]
        safe_conclusion = str(conclusion or "failure")[:80]
        safe_summary = str(summary)[:2000] if summary else None
        safe_url = str(details_url)[:1000] if details_url else None
        return GitHubCheckFailure(
            name=safe_name, conclusion=safe_conclusion, details_url=safe_url,
            summary=safe_summary,
            failure_class=cls._failure_class(name=safe_name, conclusion=safe_conclusion, summary=safe_summary),
        )

    def get_failed_checks(self, pr_number: int, *, expected_head_sha: str | None = None) -> tuple[GitHubCheckFailure, ...]:
        pr = self.get_pull_request(pr_number)
        if expected_head_sha is not None:
            import re
            if not re.fullmatch(r"[0-9a-f]{40}", expected_head_sha):
                raise ValueError("expected CI failure evidence SHA is invalid")
            if pr.head_sha != expected_head_sha:
                raise RuntimeError("CI failure evidence PR head diverged from candidate SHA")
        source, primary, statuses = self._check_runs_or_fine_grained_evidence(pr.head_sha,pr.head_ref)
        passing = {"success", "neutral", "skipped"}
        failures = []
        if source == "github_actions_statuses":
            for run in primary:
                conclusion = str(run.get("conclusion") or "")
                if str(run.get("status") or "") != "completed" or conclusion in passing:
                    continue
                failures.append(self._check_failure(
                    name=run.get("name") or "github-actions", conclusion=conclusion or "failure",
                    details_url=run.get("html_url"),
                    summary=f"GitHub Actions workflow concluded {conclusion or 'failure'}",
                ))
            # Commit statuses include Vercel/Preview and other deployment
            # providers.  They are not native CI failures and must never
            # turn an exact-SHA code repair into an unknown/quota failure.
            # The candidate CI gate already uses authoritative Actions runs.
            return tuple(failures)
        for check in primary:
            if check.get("status") != "completed" or check.get("conclusion") in passing:
                continue
            output = check.get("output") or {}
            failures.append(self._check_failure(
                name=check.get("name") or "unnamed-check",
                conclusion=check.get("conclusion") or "failure",
                details_url=check.get("details_url"), summary=output.get("summary") or output.get("title"),
            ))
        seen = {(failure.name, failure.conclusion) for failure in failures}
        for run in self.last_ci_workflow_runs:
            conclusion = str(run.get("conclusion") or "")
            if run.get("status") == "completed" and conclusion not in passing:
                name = str(run.get("name") or "github-actions")
                if (name, conclusion) not in seen:
                    failures.append(self._check_failure(
                        name=name, conclusion=conclusion or "failure",
                        details_url=run.get("html_url"),
                        summary="GitHub Actions workflow concluded " + conclusion,
                    ))
        return tuple(failures)

    def dispatch_workflow(self, workflow: str, *, ref: str) -> None:
        if not workflow.strip() or not ref.strip():
            raise ValueError("workflow and ref are required")
        encoded=parse.quote(workflow.strip(),safe="")
        self._call(
            "POST",
            f"/repos/{self.repository}/actions/workflows/{encoded}/dispatches",
            payload={"ref":ref.strip()},
        )

    def close_issue(self, issue_number: int) -> None:
        self._call("PATCH", f"/repos/{self.repository}/issues/{issue_number}",
                   payload={"state": "closed", "state_reason": "completed"})
