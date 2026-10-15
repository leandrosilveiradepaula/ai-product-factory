"""Run-linked audit of Product Stage readiness when a scheduled worker skips work.

Never calls a model, claims a run, creates a task or authorizes paid execution.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Mapping

from .supabase_operational_health import SupabaseOperationalHealthReader
from .supabase_server import resolve_supabase_server_config

UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
RUN_LIMIT = 40
AUDIT_LIMIT = 5
DEDUP_WINDOW = timedelta(minutes=30)


def primary_readiness_blocker(env: Mapping[str, str] | None = None, *, health_reader=None) -> str | None:
    """Return a normalized code only: no secrets or raw exception details."""
    cfg = os.environ if env is None else env
    if cfg.get("FACTORY_PRIMARY_MODEL_ENABLED") != "true":
        return "model_disabled"
    mode = cfg.get("FACTORY_PRIMARY_AUTH_MODE", "auto").strip()
    key_ready = bool(cfg.get("OPENAI_API_KEY", "").strip())
    wif_vars = ("OPENAI_IDENTITY_PROVIDER_ID", "OPENAI_SERVICE_ACCOUNT_ID", "OPENAI_WIF_AUDIENCE")
    wif_any = any(cfg.get(v, "").strip() for v in wif_vars)
    wif_ready = all(cfg.get(v, "").strip() for v in wif_vars)
    if mode == "api_key":
        auth_ready = key_ready
    elif mode == "wif":
        auth_ready = wif_ready
    elif mode in {"", "auto"}:
        auth_ready = wif_ready if wif_any else key_ready
    else:
        auth_ready = False
    if not auth_ready:
        return "primary_auth_missing"
    try:
        budget = Decimal(cfg.get("FACTORY_MODEL_BUDGET_USD", ""))
        reserve = Decimal(cfg.get("FACTORY_MODEL_RESERVE_USD", ""))
        if not all(value.is_finite() and value > 0 for value in (budget, reserve)):
            return "budget_not_configured"
    except (InvalidOperation, ValueError):
        return "budget_not_configured"
    try:
        health = (health_reader or SupabaseOperationalHealthReader()).read(budget=budget)
        known = Decimal(str(health.known_cost))
        if not known.is_finite() or known < 0:
            return "cost_ledger_unavailable"
        if int(health.unknown_cost_events) > 0:
            return "paid_cost_unknown"
        if known + reserve > budget:
            return "budget_exhausted"
    except Exception:
        return "cost_ledger_unavailable"
    return None


class SupabaseProductBlockerAudit:
    """Privileged, bounded, server-only read-and-append audit adapter."""

    def __init__(self) -> None:
        cfg = resolve_supabase_server_config()
        self.url, self.headers = cfg.url, cfg.headers

    def _get(self, path: str) -> list[dict]:
        request = urllib.request.Request(
            f"{self.url}/rest/v1/{path}", headers=self.headers, method="GET"
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode())
        if not isinstance(data, list) or any(not isinstance(r, dict) for r in data):
            raise RuntimeError("malformed Product Stage read")
        return data

    def _post(self, table: str, payload: dict) -> None:
        request = urllib.request.Request(
            f"{self.url}/rest/v1/{table}",
            data=json.dumps(payload).encode(),
            headers={**self.headers, "Content-Type": "application/json", "Prefer": "return=minimal"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status not in (200, 201, 204):
                raise RuntimeError("Product Stage audit was not persisted")

    def pending_candidates(self) -> list[dict[str, str]]:
        runs = self._get(
            "factory_runs?select=id,task_id,status,started_at,created_at"
            "&status=in.(created,queued)&order=created_at.asc"
            f"&limit={RUN_LIMIT}"
        )
        if len(runs) >= RUN_LIMIT:
            raise RuntimeError("pending Product Stage inventory reached verified bound")
        candidates = [
            r for r in runs
            if r.get("status") in {"created", "queued"}
            and r.get("started_at") is None
            and isinstance(r.get("id"), str) and UUID.fullmatch(r["id"])
            and isinstance(r.get("task_id"), str) and UUID.fullmatch(r["task_id"])
        ]
        if not candidates:
            return []
        task_ids = sorted({r["task_id"] for r in candidates})
        tasks = self._get(
            "factory_tasks?select=id,project_id,status&id=in.(" + ",".join(task_ids) + ")"
        )
        if any(t.get("id") not in task_ids for t in tasks):
            raise RuntimeError("inconsistent Product Stage task link")
        eligible = {
            t["id"]: t["project_id"] for t in tasks
            if t.get("status") == "queued"
            and isinstance(t.get("project_id"), str) and UUID.fullmatch(t["project_id"])
        }
        if not eligible:
            return []
        project_ids = sorted(set(eligible.values()))
        projects = self._get(
            "factory_projects?select=id,is_active&id=in.(" + ",".join(project_ids) + ")"
        )
        if any(p.get("id") not in project_ids for p in projects):
            raise RuntimeError("inconsistent Product Stage project link")
        active = {p["id"] for p in projects if p.get("is_active") is True}
        return [
            {"run_id": r["id"], "task_id": r["task_id"], "project_id": eligible[r["task_id"]]}
            for r in candidates if eligible.get(r["task_id"]) in active
        ][:AUDIT_LIMIT]

    def last_blocker(self, run_id: str) -> tuple[str, datetime] | None:
        rows = self._get(
            "factory_audit_events?select=payload,created_at"
            f"&run_id=eq.{run_id}&event_type=eq.product.worker_blocked"
            "&order=created_at.desc&limit=1"
        )
        if not rows:
            return None
        item = rows[0]
        payload = item.get("payload")
        if not isinstance(payload, dict) or not isinstance(payload.get("reason_code"), str):
            raise RuntimeError("invalid Product Stage blocker payload")
        when = datetime.fromisoformat(str(item["created_at"]).replace("Z", "+00:00"))
        if when.tzinfo is None:
            raise RuntimeError("Product Stage audit missing timezone")
        return payload["reason_code"], when

    def still_pending(self, candidate: dict[str, str]) -> bool:
        rows = self._get(
            "factory_runs?select=id,task_id,status,started_at"
            f"&id=eq.{candidate['run_id']}&limit=1"
        )
        return len(rows) == 1 and (
            rows[0].get("id") == candidate["run_id"]
            and rows[0].get("task_id") == candidate["task_id"]
            and rows[0].get("status") in {"created", "queued"}
            and rows[0].get("started_at") is None
        )

    def record(self, candidate: dict[str, str], reason: str, workflow_id: str | None) -> None:
        self._post("factory_audit_events", {
            "project_id": candidate["project_id"],
            "run_id": candidate["run_id"],
            "task_id": candidate["task_id"],
            "actor_type": "system",
            "actor_ref": "gha-product-stage-readiness",
            "event_type": "product.worker_blocked",
            "payload": {
                "reason_code": reason,
                "source": "product_stage_preflight",
                "workflow_run_id": workflow_id,
                "claimed": False,
            },
        })


def record_product_worker_readiness(
    *, env: Mapping[str, str] | None = None, health_reader=None,
    audit: SupabaseProductBlockerAudit | None = None,
    now: datetime | None = None,
) -> dict:
    cfg = os.environ if env is None else env
    reason = primary_readiness_blocker(cfg, health_reader=health_reader)
    if reason is None:
        return {"ready": True, "status": "ready", "reason_code": None,
                "recorded": 0, "deduplicated": 0}
    client = audit if audit is not None else SupabaseProductBlockerAudit()
    observed = now or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        raise ValueError("readiness evidence timestamp requires timezone")
    gh_id = cfg.get("GITHUB_RUN_ID", "")
    workflow_id = gh_id if re.fullmatch(r"[0-9]{1,20}", gh_id) else None
    candidates = client.pending_candidates()
    recorded, deduplicated, superseded = 0, 0, 0
    for candidate in candidates:
        prior = client.last_blocker(candidate["run_id"])
        if prior and prior[0] == reason and observed - prior[1] < DEDUP_WINDOW:
            deduplicated += 1
            continue
        if not client.still_pending(candidate):
            superseded += 1
            continue
        client.record(candidate, reason, workflow_id)
        recorded += 1
    return {
        "ready": False, "status": "blocked", "reason_code": reason,
        "pending_observed": len(candidates), "recorded": recorded,
        "deduplicated": deduplicated, "superseded": superseded,
    }
