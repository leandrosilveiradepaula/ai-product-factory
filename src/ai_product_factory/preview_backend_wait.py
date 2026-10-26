"""Read-only guard for an exact-SHA Preview's recorded backend-503 blocker.

On a subsequent scheduled run, probe session availability BEFORE preparing
Playwright or calling deployment adapters. Never convert health into browser
success; the original failed evaluation remains durable until a new real E2E.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from urllib.parse import urlencode
import urllib.error
import urllib.request

from .preview_session_probe import (
    PreviewEnvironmentNotReady, is_session_backend_503, preview_origin, probe_session,
)
from .supabase_server import resolve_supabase_server_config


_SHA = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
_UUID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\Z", re.ASCII)


@dataclass(frozen=True)
class PreviewBackendWait:
    preview_url: str
    waiting: bool
    reason: str


def evaluate_preview_backend_wait(*, run_id: str, candidate_commit: str,
                                  read, probe=probe_session) -> PreviewBackendWait | None:
    """Return None for ordinary runs; an environmental wait ONLY for proven 503.

    Evidence must be bound to the same run, exact SHA and successful Preview
    deployment. All remote reads are privileged server-side, never browser-side.
    """
    if (not isinstance(run_id, str) or not _UUID.fullmatch(run_id)
        or not isinstance(candidate_commit, str) or not _SHA.fullmatch(candidate_commit)):
        raise ValueError("invalid pinned Preview backend identity")

    latest = read("factory_evaluations", {
        "select": "id,status,baseline_ref,result",
        "run_id": "eq." + run_id,
        "eval_type": "eq.browser_e2e",
        "order": "created_at.desc,id.desc", "limit": "1",
    })
    if not isinstance(latest, list) or len(latest) > 1 or any(not isinstance(x,dict) for x in latest):
        raise RuntimeError("invalid latest browser-evidence selection")
    if not latest:
        return None
    evaluation = latest[0]
    payload = evaluation.get("result")
    if not isinstance(payload,dict):
        raise RuntimeError("invalid previous browser-evidence payload")
    if evaluation.get("status") != "failure" or not is_session_backend_503(payload.get("detail")):
        return None

    raw_url = evaluation.get("baseline_ref")
    url = preview_origin(raw_url)
    if url != raw_url or payload.get("preview_url") != url:
        raise RuntimeError("backend blocker has untrusted browser origin")

    deployments = read("factory_deployments", {
        "select": "status,metadata",
        "run_id": "eq." + run_id,
        "environment": "eq.preview",
        "status": "eq.success",
        "order": "created_at.desc", "limit": "20",
    })
    if not isinstance(deployments,list) or len(deployments)>20 or any(not isinstance(x,dict) for x in deployments):
        raise RuntimeError("invalid Preview deployment inventory")
    bound = any(
        row.get("status") == "success"
        and isinstance(row.get("metadata"),dict)
        and row["metadata"].get("candidate_commit") == candidate_commit
        and row["metadata"].get("preview_url") == url
        for row in deployments
    )
    if not bound:
        raise RuntimeError("backend failure has no exact-SHA Preview deployment evidence")

    try:
        result = probe(url)
    except PreviewEnvironmentNotReady as exc:
        # Only sanitized enum-like error codes are emitted. Credentials and
        # response bodies are NEVER recorded, nor is the failed eval overwritten.
        return PreviewBackendWait(url, True, str(exc))
    if (not isinstance(result,dict)
        or result.get("kind") != "unauthenticated_json_session_probe"
        or result.get("url") != url + "/api/session"
        or result.get("http_status") not in ("200","401")
        or not isinstance(result.get("content_type"),str)
        or re.fullmatch(r"application/json(?:;.*)?",result["content_type"]) is None):
        raise RuntimeError("unverified Preview session probe response")
    return PreviewBackendWait(url, False, "environment_probe_ready_browser_still_required")


class SupabasePreviewBackendWaitReader:
    """Privileged, read-only selector; no Vercel token or app credential."""

    def __init__(self, *, url: str | None = None,
                 secret_key: str | None = None,
                 service_role_key: str | None = None) -> None:
        cfg=resolve_supabase_server_config(
            url=url,secret_key=secret_key,service_role_key=service_role_key)
        self.url=cfg.url
        self.headers=cfg.headers

    def _read(self, table: str, params: dict) -> list[dict]:
        if table not in ("factory_evaluations","factory_deployments"):
            raise ValueError("invalid Preview evidence read surface")
        request=urllib.request.Request(
            self.url + "/rest/v1/" + table + "?" + urlencode(params),
            headers=self.headers,method="GET",
        )
        try:
            with urllib.request.urlopen(request,timeout=20) as response:
                payload=json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Preview evidence read failed ({exc.code})") from exc
        if not isinstance(payload,list):
            raise RuntimeError("invalid Preview evidence API response")
        return payload

    def check(self, *, run_id: str,
              candidate_commit: str) -> PreviewBackendWait | None:
        return evaluate_preview_backend_wait(
            run_id=run_id,candidate_commit=candidate_commit,
            read=self._read,probe=probe_session,
        )
