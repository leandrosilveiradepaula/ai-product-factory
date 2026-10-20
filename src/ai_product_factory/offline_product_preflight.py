"""Read-only offline source preflight for one already recorded Product Stage run.

No RPCs, claims, retry, model invocation, project mutations or paid API calls.
A passing source check never means the run completed or budget is approved.
"""
from __future__ import annotations

import re
from urllib.parse import quote

from .supabase_runtime_queue import SupabaseRuntimeQueue

_UUID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\Z", re.I)
_KEY = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")
_TERMINAL = frozenset({"failed", "completed", "cancelled", "canceled"})
_PENDING = frozenset({"queued", "created"})
_SUPPORTED = {
    "reconciliation": ("reconciliation", "gap_analysis", "planning"),
    "discovery": ("discovery", "specification", "planning"),
}


def _one(rows: object, *, field: str, expected: str) -> dict:
    if (not isinstance(rows, list) or len(rows) != 1
            or not isinstance(rows[0], dict)
            or rows[0].get(field) != expected):
        raise PermissionError("offline preflight cannot verify exact record identity")
    return rows[0]


def check_recorded_product_run(
    *, project_key: str, run_id: str,
    queue: SupabaseRuntimeQueue | None = None,
) -> dict:
    """Compare immutable source evidence to the exact project/run; never claim it.

    This method also examines terminal runs for diagnostics. Those runs remain
    terminal, even when current source inspection now succeeds.
    """
    if not isinstance(project_key, str) or not _KEY.fullmatch(project_key):
        raise ValueError("invalid project key")
    if not isinstance(run_id, str) or not _UUID.fullmatch(run_id):
        raise ValueError("invalid run UUID")
    run_id = run_id.lower()
    result = {
        "project_key": project_key, "run_id": run_id,
        "state": "blocked", "reason_code": "unverifiable_source",
        "source_preflight": "blocked", "source_commit": None,
        "inspected_paths": [], "issue_reference": None,
        "model_tested": False, "paid_model_calls": 0, "writes": 0,
        "budget_authorized": False, "e2e_verified": False,
    }
    reader = queue or SupabaseRuntimeQueue()
    try:
        project = _one(reader._get(
            "factory_projects?select=id,project_key,project_kind,repository,manifest,is_active"
            "&project_key=eq." + quote(project_key, safe="") + "&limit=2"
        ), field="project_key", expected=project_key)
        if project.get("is_active") is not True:
            raise PermissionError("project is inactive")
        project_id = project.get("id")
        if not isinstance(project_id, str) or not _UUID.fullmatch(project_id):
            raise PermissionError("project identity malformed")
        run = _one(reader._get(
            "factory_runs?select=id,task_id,status,metadata,created_at"
            "&id=eq." + run_id + "&limit=2"
        ), field="id", expected=run_id)
        task_id = run.get("task_id")
        if not isinstance(task_id, str) or not _UUID.fullmatch(task_id):
            raise PermissionError("task identity malformed")
        task = _one(reader._get(
            "factory_tasks?select=id,project_id,status"
            "&id=eq." + task_id + "&limit=2"
        ), field="id", expected=task_id)
        if task.get("project_id") != project_id:
            raise PermissionError("run belongs to another project")
        meta = run.get("metadata")
        if not isinstance(meta, dict):
            raise PermissionError("run metadata missing")
        stages = meta.get("stages")
        if not isinstance(stages, list) or not stages:
            raise PermissionError("run has no Product Stage contract")
        first = stages[0]
        if first not in _SUPPORTED or stages != list(_SUPPORTED[first]):
            raise PermissionError("unsupported Product Stage sequence")

        run_status = run.get("status")
        if run_status not in _PENDING | _TERMINAL:
            result["state"] = "in_progress_or_unverified"
        elif run_status in _TERMINAL:
            result["state"] = "historical_terminal"
        else:
            control = _one(reader._get(
                "factory_project_execution_controls?select=project_id,state,generation"
                "&project_id=eq." + quote(project_id, safe="") + "&limit=2"
            ), field="project_id", expected=project_id)
            epoch = meta.get("execution_generation")
            if (control.get("state") != "running"
                    or type(epoch) is not int or epoch < 1
                    or epoch != control.get("generation")
                    or task.get("status") != "queued"):
                result["state"] = "blocked"
                result["reason_code"] = "project_control_or_epoch_not_eligible"
                return result
            result["state"] = "recorded_pending"

        if first == "reconciliation":
            context = reader._reconciliation_context(project_id, {"manifest": project.get("manifest")})
            snapshot = context.get("state_snapshot")
            if (not isinstance(snapshot, dict)
                    or not isinstance(snapshot.get("summary"), str)
                    or not snapshot["summary"].strip()
                    or not (snapshot.get("evidence") or snapshot.get("source_status"))):
                result["reason_code"] = "durable_reconciliation_snapshot_missing"
                return result
            context = reader._live_candidate_context(project_id, context)
            live = ((context.get("current_state_facts") or {}).get("live_candidate") or {})
            if not isinstance(live, dict) or not re.fullmatch(
                r"[0-9a-f]{40}", str(live.get("sha") or "")
            ):
                raise PermissionError("exact candidate source missing")
            evidence = live.get("source_evidence") or {}
            if not isinstance(evidence, dict) or evidence.get("assessed_commit") != live["sha"]:
                raise PermissionError("source evidence does not match candidate SHA")
            result["source_commit"] = live["sha"]
            result["inspected_paths"] = [
                str(row.get("path")) for row in evidence.get("inspected_files", [])
                if isinstance(row, dict) and isinstance(row.get("path"), str)
            ][:3]
            result["issue_reference"] = evidence.get("issue_reference")
            if evidence.get("status") != "bounded_source_inspected":
                result["reason_code"] = "source_paths_not_inspected"
                return result
        result["source_preflight"] = "verified"
        result["reason_code"] = "source_only_no_model_or_execution"
        # Recheck the exact run status: no verification of a disappearing or
        # swapped row can silently count as source readiness.
        after = _one(reader._get(
            "factory_runs?select=id,task_id,status"
            "&id=eq." + run_id + "&limit=2"
        ), field="id", expected=run_id)
        if after.get("task_id") != task_id or after.get("status") != run_status:
            result["state"] = "blocked"
            result["source_preflight"] = "blocked"
            result["reason_code"] = "run_changed_during_preflight"
        return result
    except Exception:
        # No HTTP bodies, tokens, user content, task descriptions, prompts, or
        # arbitrary exception strings may leak into the JSON report.
        result["state"] = "blocked"
        result["source_preflight"] = "blocked"
        result["reason_code"] = "unverifiable_source"
        return result
