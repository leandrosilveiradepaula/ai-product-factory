"""Read-only queued-task inventory. A queued row is not dispatch authorization."""
from __future__ import annotations

import json
import uuid
import urllib.error
import urllib.request
from collections import defaultdict

from .supabase_server import resolve_supabase_server_config

# Diagnostic statuses only; never use inventory counts to authorize dispatch.
# A completed parent satisfies dependencies and may still have actionable children.
TERMINAL_PARENT = {"completed", "integrated", "cancelled"}
ACTIVE_UNIT = {"queued", "pending", "running"}
# Mirrors the verified factory_change_set_work_units_status_check constraint.
ALLOWED_UNIT_STATUS = frozenset({"pending", "queued", "running", "completed", "integrated", "failed", "blocked"})


def valid_id(value: object) -> str:
    try:
        if not isinstance(value, str):
            raise ValueError("not a UUID")
        return str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise RuntimeError("backlog inventory returned invalid UUID") from exc


def bounded(value: object, limit: int, label: str) -> list[dict]:
    if not isinstance(value, list) or len(value) > limit:
        raise RuntimeError(f"{label} exceeds verified {limit}-row boundary")
    if not all(isinstance(row, dict) for row in value):
        raise RuntimeError(f"{label} includes malformed row")
    return value


class SupabaseBacklogInventoryReader:
    """Never mutate or reactivate historical tasks, plans or Work Units."""

    def __init__(self, *, url: str | None = None, secret_key: str | None = None,
                 service_role_key: str | None = None):
        cfg = resolve_supabase_server_config(
            url=url, secret_key=secret_key, service_role_key=service_role_key
        )
        self.url, self.headers = cfg.url, cfg.headers

    def _get(self, path: str):
        req = urllib.request.Request(
            f"{self.url}/rest/v1/{path}", method="GET", headers=self.headers
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = response.read().decode()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"backlog inventory read failed ({exc.code})") from exc
        return [] if not raw else json.loads(raw)

    def read(self) -> dict:
        projects = bounded(self._get(
            "factory_projects?select=id,project_key,is_active&order=project_key.asc&limit=101"
        ), 100, "projects")
        indexed = {}
        for project in projects:
            pid = valid_id(project.get("id"))
            if (pid in indexed or not isinstance(project.get("project_key"), str)
                    or not project["project_key"].strip()
                    or not isinstance(project.get("is_active"), bool)):
                raise RuntimeError("invalid project inventory")
            indexed[pid] = project

        queued = bounded(self._get(
            "factory_tasks?select=id,project_id,parent_task_id,status"
            "&status=eq.queued&order=created_at.asc&limit=101"
        ), 100, "queued tasks")
        if not queued:
            return {"status": "observed", "read_only": True, "queued_tasks": 0,
                    "active_work_units": 0, "with_active_units": 0,
                    "historical_children_without_active_units": 0,
                    "other_queued_without_active_units": 0,
                    "completed_parent_without_work_units": 0,
                    "completed_parent_with_inactive_work_units": 0,
                    "unverified_parent_status_without_active_units": 0,
                    "projects": []}

        task_ids, parent_ids = set(), set()
        for row in queued:
            tid, pid = valid_id(row.get("id")), valid_id(row.get("project_id"))
            if tid in task_ids or pid not in indexed or row.get("status") != "queued":
                raise RuntimeError("inconsistent queued task inventory")
            task_ids.add(tid)
            if row.get("parent_task_id") is not None:
                parent_ids.add(valid_id(row["parent_task_id"]))

        parents = {}
        if parent_ids:
            query = ",".join(sorted(parent_ids))
            matches = bounded(self._get(
                f"factory_tasks?select=id,project_id,status&id=in.({query})&limit=101"
            ), 100, "parent tasks")
            for parent in matches:
                pid = valid_id(parent.get("id"))
                if pid in parents:
                    raise RuntimeError("duplicate parent task")
                parents[pid] = parent
            if parent_ids != set(parents):
                raise RuntimeError("parent task unavailable for backlog classification")

        query = ",".join(sorted(task_ids))
        units = bounded(self._get(
            "factory_change_set_work_units?select=id,task_id,status"
            f"&task_id=in.({query})&limit=501"
        ), 500, "work units")
        active_by_task = defaultdict(int)
        all_units_by_task = defaultdict(int)
        unit_ids = set()
        for row in units:
            uid, tid = valid_id(row.get("id")), valid_id(row.get("task_id"))
            if uid in unit_ids or tid not in task_ids:
                raise RuntimeError("inconsistent work-unit inventory")
            if row.get("status") not in ALLOWED_UNIT_STATUS:
                raise RuntimeError("unknown work-unit status in backlog inventory")
            unit_ids.add(uid)
            all_units_by_task[tid] += 1
            if row["status"] in ACTIVE_UNIT:
                active_by_task[tid] += 1

        stats = {
            pid: {"project_key": project["project_key"], "is_active": project["is_active"],
                  "queued_tasks": 0, "active_work_units": 0, "with_active_units": 0,
                  "historical_children_without_active_units": 0,
                  "other_queued_without_active_units": 0,
                  "completed_parent_without_work_units": 0,
                  "completed_parent_with_inactive_work_units": 0,
                  "unverified_parent_status_without_active_units": 0}
            for pid, project in indexed.items()
        }
        for row in queued:
            pid, tid = valid_id(row["project_id"]), valid_id(row["id"])
            project_stats = stats[pid]
            project_stats["queued_tasks"] += 1
            units_count = active_by_task[tid]
            project_stats["active_work_units"] += units_count
            if units_count:
                project_stats["with_active_units"] += 1
                continue
            parent_id = row.get("parent_task_id")
            if parent_id is not None:
                parent = parents[valid_id(parent_id)]
                if valid_id(parent.get("project_id")) != pid:
                    raise RuntimeError("cross-project queued-task parent")
                parent_status=parent.get("status")
                if not isinstance(parent_status,str) or not parent_status.strip():
                    raise RuntimeError("invalid parent task status for backlog classification")
                if parent_status=="completed":
                    # Completed dependencies may still have unmaterialized children.
                    # Keep the legacy historical counter for compatibility, but
                    # explicitly surface these separately for operator review.
                    if all_units_by_task[tid]==0:
                        project_stats["completed_parent_without_work_units"] += 1
                    else:
                        project_stats["completed_parent_with_inactive_work_units"] += 1
                if parent_status in TERMINAL_PARENT:
                    project_stats["historical_children_without_active_units"] += 1
                    continue
                project_stats["unverified_parent_status_without_active_units"] += 1
            project_stats["other_queued_without_active_units"] += 1

        result = sorted((v for v in stats.values() if v["queued_tasks"]),
                        key=lambda v: v["project_key"])
        names = ("queued_tasks", "active_work_units", "with_active_units",
                 "historical_children_without_active_units",
                 "other_queued_without_active_units",
                 "completed_parent_without_work_units",
                 "completed_parent_with_inactive_work_units",
                 "unverified_parent_status_without_active_units")
        return {"status": "observed", "read_only": True,
                **{k: sum(p[k] for p in result) for k in names},
                "projects": result,
                "disclaimer": (
                    "Inventory counts do not establish dispatch eligibility. "
                    "Completed parents may have unmaterialized actionable children; "
                    "historical is a diagnostic label, not a terminal verdict."
                )}
