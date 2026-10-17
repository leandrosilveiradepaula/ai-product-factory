"""Fail-closed settlement of pending manual pause/stop transitions."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from .supabase_server import resolve_supabase_server_config


class SupabaseProjectControlSettlement:
    def __init__(self, *, url: str | None = None, service_role_key: str | None = None):
        cfg = resolve_supabase_server_config(url=url, service_role_key=service_role_key)
        self.url = cfg.url.rstrip("/")
        self.headers = cfg.headers

    def _request(self, path: str, payload: dict | None = None):
        headers = dict(self.headers)
        if payload is None:
            request = urllib.request.Request(self.url + "/rest/v1/" + path, headers=headers)
        else:
            headers["Content-Type"] = "application/json"
            request = urllib.request.Request(
                self.url + "/rest/v1/" + path, headers=headers,
                data=json.dumps(payload).encode(), method="POST",
            )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"project control settlement HTTP {exc.code}") from exc

    def settle_pending(self) -> dict:
        controls = self._request(
            "factory_project_execution_controls?select=project_id,state&state=in.(pausing,stopping)&order=project_id.asc&limit=100"
        )
        if not isinstance(controls, list):
            raise RuntimeError("invalid pending project controls response")
        results = []
        for control in controls:
            if not isinstance(control, dict) or control.get("state") not in ("pausing", "stopping"):
                raise RuntimeError("invalid pending project control")
            project_id = control.get("project_id")
            if not isinstance(project_id, str) or not project_id:
                raise RuntimeError("missing project identifier")
            projects = self._request(
                "factory_projects?select=project_key&id=eq."
                + urllib.parse.quote(project_id, safe="") + "&limit=1"
            )
            if not isinstance(projects, list) or len(projects) != 1:
                raise RuntimeError("project lookup failed")
            project_key = projects[0].get("project_key")
            if not isinstance(project_key, str) or not project_key:
                raise RuntimeError("invalid project key")
            result = self._request(
                "rpc/factory_settle_project_control_v1", {"p_project_key": project_key}
            )
            if not isinstance(result, dict) or result.get("state") not in (
                "pausing", "paused", "stopping", "stopped"
            ) or not isinstance(result.get("changed"), bool):
                raise RuntimeError("invalid project settlement response")
            results.append({"project_key": project_key, "state": result["state"], "changed": result["changed"]})
        return {"pending": len(controls), "settled": sum(item["changed"] for item in results), "results": results}
