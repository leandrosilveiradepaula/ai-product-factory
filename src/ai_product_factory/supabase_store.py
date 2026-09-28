from __future__ import annotations

import json
import os
from typing import Any, Callable
from urllib import parse, request

from .control_plane import (
    CodexUsageRecord,
    DecisionRecord,
    ProjectRecord,
    RunRecord,
    TaskRecord,
    ToolUsageRecord,
)


Transport = Callable[[str, str, dict[str, str], bytes | None], tuple[int, Any]]
_UNSET = object()


def _default_transport(method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, Any]:
    req = request.Request(url, data=body, headers=headers, method=method)
    with request.urlopen(req, timeout=30) as response:
        raw = response.read().decode("utf-8")
        return response.status, json.loads(raw) if raw else None


class SupabaseControlPlaneStore:
    """Server-side PostgREST adapter for the factory control plane.

    Credentials are read from environment variables only. SUPABASE_SECRET_KEY
    must never be shipped to a browser or committed to source control.
    """

    def __init__(
        self,
        *,
        url: str | None = None,
        secret_key: str | None = None,
        transport: Transport | None = None,
    ) -> None:
        self.url = (url or os.environ.get("SUPABASE_URL", "")).rstrip("/")
        self.secret_key = secret_key or os.environ.get("SUPABASE_SECRET_KEY", "")
        if not self.url:
            raise ValueError("SUPABASE_URL is required")
        if not self.secret_key:
            raise ValueError("SUPABASE_SECRET_KEY is required")
        self.transport = transport or _default_transport

    def _headers(self, *, prefer: str | None = None) -> dict[str, str]:
        headers = {
            "apikey": self.secret_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def _call(
        self,
        method: str,
        table: str,
        *,
        query: dict[str, str] | None = None,
        payload: Any = None,
        prefer: str | None = None,
    ) -> Any:
        suffix = ""
        if query:
            suffix = "?" + parse.urlencode(query, safe=".,()*:")
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        status, data = self.transport(
            method,
            f"{self.url}/rest/v1/{table}{suffix}",
            self._headers(prefer=prefer),
            body,
        )
        if status < 200 or status >= 300:
            raise RuntimeError(f"Supabase request failed with HTTP {status}")
        return data

    @staticmethod
    def _project(row: dict[str, Any]) -> ProjectRecord:
        return ProjectRecord(
            id=row["id"],
            project_key=row["project_key"],
            name=row["name"],
            repository=row.get("repository") or "",
            project_kind=row["project_kind"],
            lifecycle_stage=row.get("lifecycle_stage", "discovery"),
        )

    @staticmethod
    def _task(row: dict[str, Any]) -> TaskRecord:
        return TaskRecord(
            id=row["id"],
            project_id=row["project_id"],
            title=row["title"],
            description=row.get("description") or "",
            status=row.get("status", "queued"),
            complexity=row.get("complexity", "low"),
            acceptance_criteria=tuple(row.get("acceptance_criteria") or []),
        )

    @staticmethod
    def _run(row: dict[str, Any]) -> RunRecord:
        return RunRecord(
            id=row["id"],
            task_id=row["task_id"],
            status=row.get("status", "created"),
            execution_route=row.get("execution_route"),
            source_commit=row.get("source_commit"),
            candidate_commit=row.get("candidate_commit"),
            branch_name=row.get("branch_name"),
        )

    def create_project(self, *, project_key: str, name: str, repository: str, project_kind: str) -> ProjectRecord:
        rows = self._call(
            "POST",
            "factory_projects",
            payload={
                "project_key": project_key,
                "name": name,
                "repository": repository,
                "project_kind": project_kind,
            },
            prefer="return=representation",
        )
        return self._project(rows[0])

    def get_project_by_key(self, project_key: str) -> ProjectRecord | None:
        rows = self._call(
            "GET",
            "factory_projects",
            query={
                "project_key": f"eq.{project_key}",
                "select": "id,project_key,name,repository,project_kind,lifecycle_stage",
                "limit": "1",
            },
        )
        return self._project(rows[0]) if rows else None

    def create_task(
        self,
        *,
        project_id: str,
        title: str,
        description: str = "",
        complexity: str = "low",
        acceptance_criteria: tuple[str, ...] = (),
    ) -> TaskRecord:
        rows = self._call(
            "POST",
            "factory_tasks",
            payload={
                "project_id": project_id,
                "title": title,
                "description": description,
                "complexity": complexity,
                "acceptance_criteria": list(acceptance_criteria),
            },
            prefer="return=representation",
        )
        return self._task(rows[0])

    def update_task_status(self, task_id: str, status: str) -> TaskRecord:
        rows = self._call(
            "PATCH",
            "factory_tasks",
            query={"id": f"eq.{task_id}"},
            payload={"status": status},
            prefer="return=representation",
        )
        return self._task(rows[0])

    def create_run(
        self,
        *,
        task_id: str,
        execution_route: str | None = None,
        source_commit: str | None = None,
        branch_name: str | None = None,
    ) -> RunRecord:
        rows = self._call(
            "POST",
            "factory_runs",
            payload={
                "task_id": task_id,
                "execution_route": execution_route,
                "source_commit": source_commit,
                "branch_name": branch_name,
            },
            prefer="return=representation",
        )
        return self._run(rows[0])

    def update_run_status(self, run_id: str, status: str, *, candidate_commit: str | None = None) -> RunRecord:
        payload: dict[str, Any] = {"status": status}
        if candidate_commit is not None:
            payload["candidate_commit"] = candidate_commit
        rows = self._call(
            "PATCH",
            "factory_runs",
            query={"id": f"eq.{run_id}"},
            payload=payload,
            prefer="return=representation",
        )
        return self._run(rows[0])

    def record_decision(
        self,
        *,
        project_id: str,
        decision_type: str,
        decision: dict[str, Any],
        decided_by: str,
        task_id: str | None = None,
        question: str | None = None,
    ) -> DecisionRecord:
        rows = self._call(
            "POST",
            "factory_decisions",
            payload={
                "project_id": project_id,
                "task_id": task_id,
                "decision_type": decision_type,
                "question": question,
                "decision": decision,
                "decided_by": decided_by,
            },
            prefer="return=representation",
        )
        row = rows[0]
        return DecisionRecord(
            id=row["id"], project_id=row["project_id"], task_id=row.get("task_id"),
            decision_type=row["decision_type"], decision=row["decision"],
            decided_by=row["decided_by"], question=row.get("question"),
        )

    def record_tool_usage(
        self,
        *,
        run_id: str,
        tool_family: str,
        operation: str | None = None,
        usage_units: float | None = None,
        estimated_cost: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ToolUsageRecord:
        rows = self._call(
            "POST",
            "factory_tool_usage",
            payload={
                "run_id": run_id,
                "tool_family": tool_family,
                "operation": operation,
                "usage_units": usage_units,
                "estimated_cost": estimated_cost,
                "metadata": metadata or {},
            },
            prefer="return=representation",
        )
        row = rows[0]
        return ToolUsageRecord(
            id=str(row["id"]), run_id=row["run_id"], tool_family=row["tool_family"],
            operation=row.get("operation"), usage_units=row.get("usage_units"),
            estimated_cost=row.get("estimated_cost"), metadata=row.get("metadata") or {},
        )

    def update_tool_usage(
        self,
        usage_id: str | int,
        *,
        operation: str | None = None,
        usage_units: float | None = None,
        estimated_cost: float | None | object = _UNSET,
        metadata: dict[str, Any] | None = None,
    ) -> ToolUsageRecord:
        payload: dict[str, Any] = {}
        if operation is not None:
            payload["operation"] = operation
        if usage_units is not None:
            payload["usage_units"] = usage_units
        if estimated_cost is not _UNSET:
            payload["estimated_cost"] = estimated_cost
        if metadata is not None:
            payload["metadata"] = metadata
        rows = self._call(
            "PATCH",
            "factory_tool_usage",
            query={"id": f"eq.{usage_id}"},
            payload=payload,
            prefer="return=representation",
        )
        row = rows[0]
        return ToolUsageRecord(
            id=str(row["id"]), run_id=row["run_id"], tool_family=row["tool_family"],
            operation=row.get("operation"), usage_units=row.get("usage_units"),
            estimated_cost=row.get("estimated_cost"), metadata=row.get("metadata") or {},
        )

    def record_codex_usage(
        self,
        *,
        run_id: str,
        policy_level: int,
        invocation_count: int,
        reasons: tuple[str, ...] = (),
        reported_usage: dict[str, Any] | None = None,
    ) -> CodexUsageRecord:
        if policy_level not in range(0, 5):
            raise ValueError("policy_level must be between 0 and 4")
        if invocation_count < 0:
            raise ValueError("invocation_count cannot be negative")
        rows = self._call(
            "POST",
            "factory_codex_usage",
            payload={
                "run_id": run_id,
                "policy_level": policy_level,
                "invocation_count": invocation_count,
                "reason": list(reasons),
                "reported_usage": reported_usage or {},
            },
            prefer="return=representation",
        )
        row = rows[0]
        return CodexUsageRecord(
            id=str(row["id"]), run_id=row["run_id"], policy_level=row["policy_level"],
            invocation_count=row["invocation_count"], reasons=tuple(row.get("reason") or []),
            reported_usage=row.get("reported_usage") or {},
        )
