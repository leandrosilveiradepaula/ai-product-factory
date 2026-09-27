from __future__ import annotations

import json
import urllib.error
import urllib.request

from .supabase_server import resolve_supabase_server_config


class SupabaseCodexUsageRecorder:
    """Durably increments the Codex invocation ledger at the actual call boundary."""

    def __init__(self, *, url: str | None = None, service_role_key: str | None = None) -> None:
        cfg = resolve_supabase_server_config(url=url, service_role_key=service_role_key)
        self.url = cfg.url
        self.headers = cfg.headers

    def record_invocation(self, *, run_id: str, reported_usage: dict | None = None) -> dict:
        req = urllib.request.Request(
            f"{self.url}/rest/v1/rpc/factory_record_codex_invocation",
            data=json.dumps(
                {
                    "p_run_id": run_id,
                    "p_reported_usage": reported_usage or {"status": "started"},
                }
            ).encode(),
            method="POST",
            headers={**self.headers, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = response.read().decode()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                f"control-plane RPC failed: factory_record_codex_invocation ({exc.code})"
            ) from exc
        return {} if not raw else json.loads(raw)
