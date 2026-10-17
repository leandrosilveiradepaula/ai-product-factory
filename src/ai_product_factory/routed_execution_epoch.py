"""Server-side routed run checkpoint, never usable from browser credentials."""
from __future__ import annotations
import json
import urllib.error
import urllib.request
from .supabase_server import resolve_supabase_server_config

def assert_routed_epoch(project_id: str, generation: int, run_id: str, worker_id: str) -> None:
    if not project_id or not run_id or not worker_id or generation < 1:
        raise PermissionError("missing routed run capability")
    cfg = resolve_supabase_server_config()
    req = urllib.request.Request(
        f"{cfg.url}/rest/v1/rpc/factory_assert_routed_run_epoch",
        data=json.dumps({
            "p_project_id": project_id,
            "p_generation": generation,
            "p_run_id": run_id,
            "p_worker_id": worker_id,
        }).encode(),
        headers={**cfg.headers, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            if response.status != 200:
                raise PermissionError("routed execution checkpoint denied")
    except (urllib.error.URLError, TimeoutError) as exc:
        raise PermissionError("routed execution checkpoint unavailable") from exc
