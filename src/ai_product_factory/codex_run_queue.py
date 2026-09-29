from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from .supabase_server import resolve_supabase_server_config


@dataclass(frozen=True)
class CodexExecutionItem:
    run_id: str
    task_id: str
    project_key: str
    repository: str
    issue_number: int | None
    title: str
    description: str
    branch: str
    codex_level: int
    human_gate_required: bool = False
    change_set_id: str | None = None
    work_unit_id: str | None = None
    wave: int | None = None
    base_commit: str | None = None


class SupabaseCodexRunQueue:
    """Service-side queue for already-routed Codex runs."""

    def __init__(self, *, url: str | None = None, service_role_key: str | None = None) -> None:
        cfg = resolve_supabase_server_config(url=url, service_role_key=service_role_key)
        self.url = cfg.url
        self.key = cfg.key
        self.headers = cfg.headers

    def claim_next(self, worker_id: str, agent_key: str | None = None, run_id: str | None = None) -> CodexExecutionItem | None:
        req = urllib.request.Request(
            f"{self.url}/rest/v1/rpc/factory_claim_next_agent_codex_run",
            data=json.dumps({"p_worker_id": worker_id, "p_agent_key": agent_key, "p_run_id": run_id}).encode(),
            method="POST",
            headers={**self.headers, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = response.read().decode()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                f"control-plane RPC failed: factory_claim_next_agent_codex_run ({exc.code})"
            ) from exc
        if not raw:
            return None
        data = json.loads(raw)
        if data is None:
            return None
        return CodexExecutionItem(
            run_id=data["run_id"],
            task_id=data["task_id"],
            project_key=data["project_key"],
            repository=data["repository"],
            issue_number=data.get("issue_number"),
            title=data["title"],
            description=data.get("description") or "",
            branch=data["branch"],
            codex_level=int(data.get("codex_level") or 1),
            human_gate_required=bool(data.get("human_gate_required", False)),
            change_set_id=str(data["change_set_id"]) if data.get("change_set_id") else None,
            work_unit_id=str(data["work_unit_id"]) if data.get("work_unit_id") else None,
            wave=int(data["wave"]) if data.get("wave") is not None else None,
        )
