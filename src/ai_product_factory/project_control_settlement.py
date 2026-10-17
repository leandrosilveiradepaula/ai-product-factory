"""Fail-closed, keyset-paginated settlement of pending project controls.

Settling a page removes its rows from the pending filter. OFFSET pagination
would therefore silently skip rows. Pagination uses an immutable UUID cursor.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid

from .supabase_server import resolve_supabase_server_config

_PAGE_SIZE = 100
_PROJECT_KEY = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


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
        results: list[dict] = []
        seen: set[uuid.UUID] = set()
        cursor: uuid.UUID | None = None
        pending = 0
        while True:
            path = (
                "factory_project_execution_controls?select=project_id,state"
                "&state=in.(pausing,stopping)&order=project_id.asc"
                f"&limit={_PAGE_SIZE}"
            )
            if cursor is not None:
                path += "&project_id=gt." + urllib.parse.quote(str(cursor), safe="")
            controls = self._request(path)
            if not isinstance(controls, list) or len(controls) > _PAGE_SIZE:
                raise RuntimeError("invalid pending project controls response")
            if not controls:
                break
            for control in controls:
                if not isinstance(control, dict) or control.get("state") not in ("pausing", "stopping"):
                    raise RuntimeError("invalid pending project control")
                project_id = control.get("project_id")
                if not isinstance(project_id, str):
                    raise RuntimeError("missing project identifier")
                try:
                    project_uuid = uuid.UUID(project_id)
                except (ValueError, AttributeError) as exc:
                    raise RuntimeError("invalid project identifier") from exc
                if str(project_uuid) != project_id.lower() or project_uuid in seen or (
                    cursor is not None and project_uuid <= cursor
                ):
                    raise RuntimeError("non-monotonic project control page")
                seen.add(project_uuid)
                cursor = project_uuid
                projects = self._request(
                    "factory_projects?select=project_key&id=eq."
                    + urllib.parse.quote(project_id, safe="") + "&limit=1"
                )
                if not isinstance(projects, list) or len(projects) != 1 or not isinstance(projects[0], dict):
                    raise RuntimeError("project lookup failed")
                project_key = projects[0].get("project_key")
                if not isinstance(project_key, str) or not _PROJECT_KEY.fullmatch(project_key):
                    raise RuntimeError("invalid project key")
                result = self._request(
                    "rpc/factory_settle_project_control_v1", {"p_project_key": project_key}
                )
                if (not isinstance(result, dict)
                    or result.get("state") not in ("pausing", "paused", "stopping", "stopped")
                    or type(result.get("changed")) is not bool
                    or type(result.get("version")) is not int
                    or result["version"] < 0
                    or (result["changed"] and result["state"] not in ("paused", "stopped"))):
                    raise RuntimeError("invalid project settlement response")
                results.append({"project_key": project_key, "state": result["state"], "changed": result["changed"]})
            pending += len(controls)
            if len(controls) < _PAGE_SIZE:
                break
        return {"pending": pending, "settled": sum(item["changed"] for item in results), "results": results}
