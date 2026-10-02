from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import quote

from .supabase_server import resolve_supabase_server_config


@dataclass(frozen=True)
class ProjectGitHubAccessItem:
    project_id: str
    project_key: str
    repository: str
    auth_mode: str
    observed_capabilities: dict
    manifest: dict


class SupabaseProjectGitHubAccessStore:
    def __init__(self, *, url: str | None = None, secret_key: str | None = None, service_role_key: str | None = None) -> None:
        cfg = resolve_supabase_server_config(url=url, secret_key=secret_key, service_role_key=service_role_key)
        self.url = cfg.url
        self.headers = cfg.headers

    def _get(self, path: str):
        req = urllib.request.Request(f"{self.url}/rest/v1/{path}", headers=self.headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = response.read().decode()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"control-plane read failed: {path} ({exc.code})") from exc
        return [] if not raw else json.loads(raw)

    def _rpc(self, name: str, payload: dict):
        req = urllib.request.Request(
            f"{self.url}/rest/v1/rpc/{name}",
            data=json.dumps(payload).encode(),
            headers={**self.headers, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = response.read().decode()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"control-plane RPC failed: {name} ({exc.code})") from exc
        return None if not raw else json.loads(raw)

    def next_pending(self, project_key: str | None = None) -> ProjectGitHubAccessItem | None:
        if project_key:
            projects = self._get(
                "factory_projects?select=id,project_key,repository,is_active,manifest"
                f"&project_key=eq.{quote(project_key)}&is_active=eq.true&limit=1"
            )
            candidates = projects
        else:
            access = self._get(
                "factory_project_github_access?select=project_id,status,updated_at"
                "&status=in.(unverified,stale)&order=updated_at.asc&limit=20"
            )
            if not access:
                return None
            ids = ",".join(str(row["project_id"]) for row in access)
            candidates = self._get(
                "factory_projects?select=id,project_key,repository,is_active,manifest"
                f"&id=in.({ids})&is_active=eq.true&limit=20"
            )
            order = {str(row["project_id"]): index for index, row in enumerate(access)}
            candidates.sort(key=lambda row: order.get(str(row["id"]), 9999))
        for project in candidates:
            repository = str(project.get("repository") or "").strip()
            if not repository:
                continue
            rows = self._get(
                "factory_project_github_access?select=auth_mode,observed_capabilities"
                f"&project_id=eq.{quote(str(project['id']))}&limit=1"
            )
            row = rows[0] if rows else {}
            return ProjectGitHubAccessItem(
                project_id=str(project["id"]),
                project_key=str(project["project_key"]),
                repository=repository,
                auth_mode=str(row.get("auth_mode") or "fine_grained_pat"),
                observed_capabilities=dict(row.get("observed_capabilities") or {}),
                manifest=dict(project.get("manifest") or {}),
            )
        return None

    def record(
        self,
        item: ProjectGitHubAccessItem,
        *,
        auth_mode: str,
        required_capabilities: dict,
        observed_capabilities: dict,
        status: str,
        error: str | None,
        evidence: dict,
        repository_id: int | None,
        installation_id: int | None = None,
    ) -> dict:
        return self._rpc(
            "factory_record_project_github_access",
            {
                "p_project_id": item.project_id,
                "p_repository": item.repository,
                "p_auth_mode": auth_mode,
                "p_required_capabilities": required_capabilities,
                "p_observed_capabilities": observed_capabilities,
                "p_status": status,
                "p_last_error": error,
                "p_evidence": evidence,
                "p_installation_id": installation_id,
                "p_repository_id": repository_id,
            },
        )

    def record_preview_policy(self, item: ProjectGitHubAccessItem, *, policy: dict, evidence: dict) -> dict:
        return self._rpc(
            "factory_record_project_preview_policy",
            {
                "p_project_id": item.project_id,
                "p_policy": policy,
                "p_evidence": evidence,
            },
        )

    def require_capabilities(self, project_key: str, capabilities: tuple[str, ...]) -> None:
        projects = self._get(
            "factory_projects?select=id,repository"
            f"&project_key=eq.{quote(project_key)}&is_active=eq.true&limit=1"
        )
        if not projects:
            raise PermissionError(f"GitHub capability check failed: project {project_key} was not found")
        project_id = str(projects[0]["id"])
        rows = self._get(
            "factory_project_github_access?select=status,observed_capabilities,last_error"
            f"&project_id=eq.{quote(project_id)}&limit=1"
        )
        if not rows:
            raise PermissionError("GitHub capability preflight has not been completed for this project")
        observed = dict(rows[0].get("observed_capabilities") or {})
        missing = [name for name in capabilities if str(observed.get(name) or "") != "verified"]
        if missing:
            detail = str(rows[0].get("last_error") or "").strip()
            suffix = f" ({detail})" if detail else ""
            raise PermissionError(
                "GitHub capabilities are not ready for this stage: " + ", ".join(missing) + suffix
            )
