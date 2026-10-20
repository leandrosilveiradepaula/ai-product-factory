"""Fail-closed operator checkpoint for deterministic external followups.

A scheduled wake is not an authorization to dispatch CI, start a deployment,
persist a specialist result or finalize a release. The project control is
read from the privileged Control Plane for *each* effectful continuation.

This is an additional checkpoint, not an atomic external-API transaction:
the database's claimed-run/lease gates remain authoritative, and a pause
cannot retroactively cancel an already-accepted external API operation.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
import uuid
from urllib.parse import quote

from .supabase_server import resolve_supabase_server_config

_PROJECT_KEY = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$", re.ASCII)


class ProjectFollowupPaused(PermissionError):
    """Known disallowed project state; never start a new external effect."""


class SupabaseProjectFollowupGuard:
    def __init__(self, *, url: str | None = None, secret_key: str | None = None,
                 service_role_key: str | None = None) -> None:
        cfg = resolve_supabase_server_config(url=url, secret_key=secret_key,
                                             service_role_key=service_role_key)
        self.url = cfg.url.rstrip("/")
        self.headers = cfg.headers

    def _request(self, endpoint: str, *, payload: dict | None = None):
        headers = dict(self.headers)
        kw = {}
        if payload is not None:
            headers["Content-Type"] = "application/json"
            kw["data"] = json.dumps(payload).encode("utf-8")
            kw["method"] = "POST"
        req = urllib.request.Request(self.url + "/rest/v1/" + endpoint,
                                     headers=headers, **kw)
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            # PT409 from the privileged SQL assertion means the operator
            # paused after the read; defer rather than converting pause to
            # a failed runner or exposing the database response payload.
            if exc.code == 409 and endpoint == "rpc/factory_assert_project_running":
                raise ProjectFollowupPaused("project_control_waiting") from None
            raise RuntimeError("project control checkpoint unavailable") from None
        except urllib.error.URLError:
            raise RuntimeError("project control checkpoint unavailable") from None
        if not body:
            return None
        try:
            return json.loads(body)
        except (ValueError, TypeError):
            raise RuntimeError("invalid project control checkpoint response") from None

    def assert_running(self, project_key: str) -> int:
        if not isinstance(project_key, str) or not _PROJECT_KEY.fullmatch(project_key):
            raise RuntimeError("invalid project checkpoint identity")
        projects = self._request(
            "factory_projects?select=id,is_active&project_key=eq."
            + quote(project_key, safe="") + "&limit=2")
        if not isinstance(projects, list) or len(projects) != 1 or not isinstance(projects[0], dict):
            raise RuntimeError("project checkpoint identity unavailable")
        project = projects[0]
        try:
            project_id = str(uuid.UUID(str(project["id"])))
        except (KeyError, TypeError, ValueError, AttributeError):
            raise RuntimeError("invalid project checkpoint UUID") from None
        if project.get("is_active") is not True:
            raise ProjectFollowupPaused("project_control_waiting")
        controls = self._request(
            "factory_project_execution_controls?select=project_id,state,generation"
            "&project_id=eq." + quote(project_id, safe="") + "&limit=2")
        if not isinstance(controls, list) or len(controls) != 1 or not isinstance(controls[0], dict):
            raise RuntimeError("project execution control checkpoint unavailable")
        control = controls[0]
        if control.get("project_id") != project_id:
            raise RuntimeError("project execution control identity mismatch")
        generation = control.get("generation")
        if type(generation) is not int or generation < 1:
            raise ProjectFollowupPaused("project_control_waiting")
        if control.get("state") != "running":
            if control.get("state") not in ("draft", "pausing", "paused", "stopping", "stopped"):
                raise RuntimeError("unknown project execution state")
            raise ProjectFollowupPaused("project_control_waiting")
        # Single-statement privileged database assertion. The SQL migration
        # #1011 additionally enforces generation and project liveness.
        self._request("rpc/factory_assert_project_running", payload={"p_project_id": project_id})
        return generation
