"""Bounded settlement of terminal CI-repair source runs; never a release action."""
from __future__ import annotations

import json
from typing import Callable
from urllib import error, request

from .supabase_server import resolve_supabase_server_config

Post = Callable[[str, dict, dict[str, str]], tuple[int, object]]
_RPC = "/rest/v1/rpc/factory_settle_terminal_ci_repair_sources_v1"


def _post(url: str, payload: dict, headers: dict[str, str]) -> tuple[int, object]:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    req = request.Request(url, data=body, headers=headers, method="POST")
    with request.urlopen(req, timeout=30) as response:
        raw = response.read(16384)
        return response.status, json.loads(raw) if raw else None


def settle_terminal_ci_repair_sources(*, max_items: int = 3, post: Post = _post) -> dict:
    """Only one service-role RPC; no Github writes, merges or paid agents.

    Before the authorized migration is applied the scheduler remains inert.
    Other HTTP/permission/identity failures are not interpreted as success.
    """
    if type(max_items) is not int or not 1 <= max_items <= 4:
        raise ValueError("max_items must be between 1 and 4")
    cfg = resolve_supabase_server_config()
    try:
        http_status, result = post(
            cfg.url + _RPC, {"p_max_items": max_items},
            {**cfg.headers, "Content-Type": "application/json"},
        )
    except error.HTTPError as exc:
        # A missing versioned RPC is a real administrative migration gate.
        # Never hide a 404 from a different endpoint/permission problem.
        if exc.code == 404 and b"PGRST202" in exc.read(4096):
            return {"status": "blocked_migration_not_applied",
                    "settled": 0, "max_items": max_items,
                    "paid_model_calls": 0, "release_authorized": False}
        raise RuntimeError(f"terminal CI repair settlement unavailable (HTTP {exc.code})") from None
    except (OSError, TimeoutError) as exc:
        raise RuntimeError("terminal CI repair settlement unavailable") from exc
    if (http_status not in (200, 201) or not isinstance(result, dict)
        or result.get("status") not in ("settled", "idle")
        or type(result.get("settled")) is not int
        or not 0 <= result["settled"] <= max_items
        or result.get("max_items") != max_items
        or result.get("paid_model_calls") != 0
        or result.get("release_authorized") is not False
        or (result["status"] == "settled") != (result["settled"] > 0)):
        raise RuntimeError("invalid terminal CI repair settlement receipt")
    return result
