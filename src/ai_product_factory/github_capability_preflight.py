from __future__ import annotations

import os
from dataclasses import dataclass

from .github_rest import GitHubRequestError, GitHubRestAdapter
from .project_github_access import ProjectGitHubAccessItem, SupabaseProjectGitHubAccessStore
from .preview_onboarding import detect_github_vercel_preview_policy


READ_CAPABILITIES = (
    "metadata_read",
    "contents_read",
    "issues_read",
    "pull_requests_read",
    "actions_read",
    "commit_statuses_read",
    "ci_evidence_read",
)
OPTIONAL_CAPABILITIES = (
    "checks_read",
)
WRITE_CAPABILITIES = (
    "contents_write",
    "issues_write",
    "pull_requests_write",
)
ALL_CAPABILITIES = READ_CAPABILITIES + OPTIONAL_CAPABILITIES + WRITE_CAPABILITIES


@dataclass(frozen=True)
class GitHubCapabilityPreflightResult:
    project_key: str
    repository: str
    auth_mode: str
    status: str
    required_capabilities: dict
    observed_capabilities: dict
    repository_id: int | None
    error: str | None
    preview_policy: dict | None = None
    preview_evidence: dict | None = None

    def as_json(self) -> dict:
        return {
            "project_key": self.project_key,
            "repository": self.repository,
            "auth_mode": self.auth_mode,
            "status": self.status,
            "required_capabilities": self.required_capabilities,
            "observed_capabilities": self.observed_capabilities,
            "repository_id": self.repository_id,
            "error": self.error,
            "preview_policy": self.preview_policy,
            "preview_evidence": self.preview_evidence,
        }


class GitHubCapabilityPreflight:
    def __init__(self, github: GitHubRestAdapter) -> None:
        self.github = github

    def _safe_get(self, path: str, *, query: dict[str, str] | None = None):
        try:
            return "verified", self.github._call("GET", path, query=query), None
        except GitHubRequestError as exc:
            if exc.status in {401, 403, 404}:
                return "missing", None, exc.status
            raise

    def run(self, item: ProjectGitHubAccessItem) -> GitHubCapabilityPreflightResult:
        observed = {name: str(item.observed_capabilities.get(name) or "unverified") for name in ALL_CAPABILITIES}
        evidence: dict[str, object] = {}
        sha = ""
        status_payload: dict = {}
        checks_payload: dict = {}

        metadata_state, metadata, metadata_status = self._safe_get(f"/repos/{item.repository}")
        observed["metadata_read"] = metadata_state
        repository_id = int(metadata["id"]) if metadata_state == "verified" and metadata and metadata.get("id") is not None else None
        default_branch = str((metadata or {}).get("default_branch") or "main")
        evidence["metadata_http_status"] = 200 if metadata_state == "verified" else metadata_status

        if metadata_state == "verified":
            state, _, status = self._safe_get(
                f"/repos/{item.repository}/contents",
                query={"ref": default_branch, "per_page": "1"},
            )
            observed["contents_read"] = state
            evidence["contents_http_status"] = 200 if state == "verified" else status

            state, _, status = self._safe_get(
                f"/repos/{item.repository}/issues",
                query={"state": "open", "per_page": "1"},
            )
            observed["issues_read"] = state
            evidence["issues_http_status"] = 200 if state == "verified" else status

            state, _, status = self._safe_get(
                f"/repos/{item.repository}/pulls",
                query={"state": "open", "per_page": "1"},
            )
            observed["pull_requests_read"] = state
            evidence["pull_requests_http_status"] = 200 if state == "verified" else status

            state, _, status = self._safe_get(
                f"/repos/{item.repository}/actions/runs",
                query={"per_page": "1"},
            )
            observed["actions_read"] = state
            evidence["actions_http_status"] = 200 if state == "verified" else status

            sha_state, ref, ref_status = self._safe_get(
                f"/repos/{item.repository}/git/ref/heads/{default_branch}"
            )
            evidence["default_branch_ref_http_status"] = 200 if sha_state == "verified" else ref_status
            sha = str(((ref or {}).get("object") or {}).get("sha") or "")
            if sha:
                state, status_payload, status = self._safe_get(f"/repos/{item.repository}/commits/{sha}/status")
                observed["commit_statuses_read"] = state
                evidence["commit_statuses_http_status"] = 200 if state == "verified" else status

                checks_state, checks_payload, checks_status = self._safe_get(
                    f"/repos/{item.repository}/commits/{sha}/check-runs",
                    query={"per_page": "100"},
                )
                observed["checks_read"] = checks_state
                evidence["checks_read"] = checks_state
                evidence["checks_http_status"] = 200 if checks_state == "verified" else checks_status
            else:
                observed["commit_statuses_read"] = "missing"
                evidence["commit_statuses_http_status"] = ref_status

        observed["ci_evidence_read"] = (
            "verified"
            if evidence.get("checks_read") == "verified"
            or (
                observed.get("actions_read") == "verified"
                and observed.get("commit_statuses_read") == "verified"
            )
            else "missing"
        )

        native_repository = os.getenv("GITHUB_REPOSITORY", "").strip()
        auth_mode = "native_github_token" if native_repository == item.repository else item.auth_mode
        if auth_mode == "native_github_token":
            for name in WRITE_CAPABILITIES:
                observed[name] = "verified"
            evidence["write_capabilities_source"] = "workflow_permissions"
        else:
            for name in WRITE_CAPABILITIES:
                if observed.get(name) != "verified":
                    observed[name] = "unverified"
            evidence["write_capabilities_source"] = "not_safely_probeable_without_mutation"

        required = {name: True for name in READ_CAPABILITIES + WRITE_CAPABILITIES}
        required.update({name: False for name in OPTIONAL_CAPABILITIES})
        missing_read = [name for name in READ_CAPABILITIES if observed.get(name) != "verified"]
        missing_write = [name for name in WRITE_CAPABILITIES if observed.get(name) != "verified"]

        if missing_read:
            status = "blocked"
            error = "Missing GitHub read capabilities: " + ", ".join(missing_read)
        elif missing_write:
            status = "partial"
            error = (
                "Read capabilities are verified, but write capabilities are still unverified: "
                + ", ".join(missing_write)
                + ". Use a GitHub App or another explicitly approved credential before Direct delivery."
            )
        else:
            status = "ready"
            error = None

        evidence["default_branch"] = default_branch
        evidence["missing_read"] = missing_read
        evidence["missing_write"] = missing_write
        statuses=list((status_payload or {}).get("statuses", [])) if isinstance(status_payload,dict) else []
        checks=list((checks_payload or {}).get("check_runs", [])) if isinstance(checks_payload,dict) else []
        preview=detect_github_vercel_preview_policy(
            manifest=item.manifest or {},
            default_branch=default_branch,
            commit_sha=sha if metadata_state=="verified" else "",
            statuses=statuses,
            checks=checks,
        )
        return GitHubCapabilityPreflightResult(
            project_key=item.project_key,
            repository=item.repository,
            auth_mode=auth_mode,
            status=status,
            required_capabilities=required,
            observed_capabilities=observed,
            repository_id=repository_id,
            error=error,
            preview_policy=preview.policy,
            preview_evidence=preview.evidence,
        )


def run_project_github_preflight(project_key: str | None = None) -> dict:
    store = SupabaseProjectGitHubAccessStore()
    item = store.next_pending(project_key)
    if item is None:
        return {"claimed": False, "status": "empty"}
    result = GitHubCapabilityPreflight(GitHubRestAdapter(repository=item.repository)).run(item)
    evidence = {
        "source": "safe_read_probe",
        "write_probe_mutation_performed": False,
        "checks_optional_when_actions_and_statuses_are_verified": True,
        "checks_read": result.observed_capabilities.get("checks_read"),
    }
    store.record(
        item,
        auth_mode=result.auth_mode,
        required_capabilities=result.required_capabilities,
        observed_capabilities=result.observed_capabilities,
        status=result.status,
        error=result.error,
        evidence=evidence,
        repository_id=result.repository_id,
    )
    preview_record=None
    if result.preview_policy is not None:
        preview_record=store.record_preview_policy(
            item,
            policy=result.preview_policy,
            evidence=result.preview_evidence or {},
        )
    return {"claimed": True, **result.as_json(), "preview_record": preview_record}
