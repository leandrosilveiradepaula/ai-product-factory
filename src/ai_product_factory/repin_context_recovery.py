"""Bounded, model-free recovery of source-repin proof missing from Direct context.

A migration-gated service-role RPC owns all CAS, epoch, provenance and audit
conditions. Never use generic failed-run retries or bypass review/release.
"""
from __future__ import annotations

import json
from typing import Callable
from urllib import error, request

from .supabase_server import resolve_supabase_server_config

Post = Callable[[str, dict, dict[str, str]], tuple[int, object]]
_RPC = "/rest/v1/rpc/factory_resume_blocked_repin_context_v1"


def _post(url: str, payload: dict, headers: dict[str, str]) -> tuple[int, object]:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    req = request.Request(url, data=body, headers=headers, method="POST")
    with request.urlopen(req, timeout=30) as response:
        raw = response.read(16384)
        return response.status, json.loads(raw) if raw else None


def resume_blocked_repin_context(*, max_items: int = 2, post: Post = _post) -> dict:
    if type(max_items) is not int or not 1 <= max_items <= 2:
        raise ValueError("max_items must be between 1 and 2")
    cfg = resolve_supabase_server_config()
    try:
        status, payload = post(
            cfg.url + _RPC, {"p_max_items": max_items},
            {**cfg.headers, "Content-Type": "application/json"},
        )
    except error.HTTPError as exc:
        if exc.code == 404 and b"PGRST202" in exc.read(4096):
            return {
                "status": "blocked_migration_not_applied", "requeued": 0,
                "max_items": max_items, "product_stage_replayed": False,
                "release_authorized": False, "paid_model_calls": 0,
            }
        raise RuntimeError(f"repin context recovery unavailable (HTTP {exc.code})") from None
    except (OSError, TimeoutError) as exc:
        raise RuntimeError("repin context recovery unavailable") from exc
    if (status not in (200, 201) or not isinstance(payload, dict)
        or payload.get("status") not in ("requeued", "idle")
        or type(payload.get("requeued")) is not int
        or not 0 <= payload["requeued"] <= max_items
        or payload.get("max_items") != max_items
        or payload.get("paid_model_calls") != 0
        or payload.get("product_stage_replayed") is not False
        or payload.get("release_authorized") is not False
        or ((payload["status"] == "requeued") != (payload["requeued"] > 0))):
        raise RuntimeError("invalid repin context recovery receipt")
    return payload
