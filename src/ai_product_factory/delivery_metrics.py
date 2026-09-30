from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from urllib.parse import quote

from .cost_observability import requires_cost_estimate
from .supabase_server import resolve_supabase_server_config


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _seconds(start: str | None, end: str | None) -> float | None:
    a, b = _dt(start), _dt(end)
    if a is None or b is None:
        return None
    return max(0.0, (b - a).total_seconds())


@dataclass(frozen=True)
class DeliveryMetrics:
    source_run_id: str
    project_key: str
    route: str | None
    queue_wait_seconds: float | None
    delivery_seconds: float | None
    time_to_awaiting_release_seconds: float | None
    time_to_release_seconds: float | None
    stage_seconds: dict[str, float]
    planned_agents: int
    builder_agents: tuple[str, ...]
    specialist_agents: tuple[str, ...]
    actual_agent_count: int
    known_cost_usd: Decimal
    unknown_paid_cost_events: int
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    codex_invocations: int
    ci_observed: bool
    first_pass_ci: bool | None
    ci_repairs: int
    specialist_repairs: int
    total_repairs: int

    def as_json(self) -> dict:
        data = asdict(self)
        data["known_cost_usd"] = str(self.known_cost_usd)
        data["builder_agents"] = list(self.builder_agents)
        data["specialist_agents"] = list(self.specialist_agents)
        return data


def derive_delivery_metrics(
    *,
    source_run: dict,
    project_key: str,
    family_runs: list[dict],
    team_plan: dict | None,
    work_units: list[dict],
    specialist_jobs: list[dict],
    tool_usage: list[dict],
    codex_usage: list[dict],
    evaluations: list[dict],
    repair_jobs: list[dict],
    audit_events: list[dict],
    release_reports: list[dict],
) -> DeliveryMetrics:
    created_at = source_run.get("created_at")
    queue_wait = _seconds(created_at, source_run.get("started_at"))

    stage_started: dict[str, str] = {}
    stage_finished: dict[str, str] = {}
    awaiting_candidates: list[str] = []
    for event in sorted(audit_events, key=lambda x: str(x.get("created_at") or "")):
        event_type = str(event.get("event_type") or "")
        payload = event.get("payload") or {}
        at = str(event.get("created_at") or "")
        if event_type == "run.stage.recorded":
            stage = str(payload.get("stage") or "")
            status = str(payload.get("status") or "")
            if stage and status == "started" and stage not in stage_started:
                stage_started[stage] = at
            elif stage and status in {"completed", "failed"} and stage not in stage_finished:
                stage_finished[stage] = at
        if event_type == "run.status.updated" and str(payload.get("status") or "") == "awaiting_release" and at:
            awaiting_candidates.append(at)

    stage_seconds: dict[str, float] = {}
    for stage, started in stage_started.items():
        finished = stage_finished.get(stage)
        duration = _seconds(started, finished)
        if duration is not None:
            stage_seconds[stage] = duration

    for row in tool_usage:
        if str(row.get("operation") or "") in {
            "verified_preview_awaiting_human_merge",
            "preview_not_required_awaiting_human_merge",
        }:
            at = str(row.get("created_at") or "")
            if at:
                awaiting_candidates.append(at)

    for row in release_reports:
        if str(row.get("status") or "") in {"ready_for_human_release", "released"}:
            at = str(row.get("created_at") or "")
            if at:
                awaiting_candidates.append(at)

    awaiting_at = min(awaiting_candidates) if awaiting_candidates else None
    released_candidates = [
        str(row.get("updated_at") or "")
        for row in release_reports
        if str(row.get("status") or "") == "released" and row.get("updated_at")
    ]
    released_at = min(released_candidates) if released_candidates else None

    end_candidates = [
        str(row.get("finished_at") or "")
        for row in family_runs
        if row.get("finished_at")
    ]
    delivery_end = released_at or (max(end_candidates) if end_candidates else None)

    plan = (team_plan or {}).get("plan") or {}
    planned_agents = int(plan.get("profiles_selected") or 0)
    if planned_agents == 0 and isinstance(plan.get("selected_agents"), list):
        planned_agents = len(plan["selected_agents"])

    builder_agents = tuple(sorted({
        str(row.get("agent_key"))
        for row in work_units
        if row.get("agent_key")
    }))
    specialist_agents = tuple(sorted({
        str(row.get("role"))
        for row in specialist_jobs
        if row.get("role")
    }))
    actual_agent_count = len({f"builder:{x}" for x in builder_agents} | {f"specialist:{x}" for x in specialist_agents})

    known_cost = Decimal("0")
    unknown_paid = 0
    input_tokens = output_tokens = cached_tokens = 0
    ci_repairs = 0
    for row in tool_usage:
        family = str(row.get("tool_family") or "")
        cost = row.get("estimated_cost")
        if cost is None:
            if requires_cost_estimate(family):
                unknown_paid += 1
        else:
            known_cost += Decimal(str(cost))
        metadata = row.get("metadata") or {}
        input_tokens += int(metadata.get("input_tokens") or 0)
        output_tokens += int(metadata.get("output_tokens") or 0)
        cached_tokens += int(metadata.get("cached_input_tokens") or 0)
        if family == "ci_repair" and str(row.get("operation") or "") == "repair_attempt":
            ci_repairs += 1

    codex_invocations = sum(int(row.get("invocation_count") or 0) for row in codex_usage)
    ci_observed = any(str(row.get("eval_type") or "") == "quality_gate" for row in evaluations) or any(
        str(row.get("event_type") or "") == "quality_gate.passed" for row in audit_events
    ) or ci_repairs > 0
    specialist_repairs = len(repair_jobs)
    total_repairs = ci_repairs + specialist_repairs

    return DeliveryMetrics(
        source_run_id=str(source_run["id"]),
        project_key=project_key,
        route=source_run.get("execution_route"),
        queue_wait_seconds=queue_wait,
        delivery_seconds=_seconds(created_at, delivery_end),
        time_to_awaiting_release_seconds=_seconds(created_at, awaiting_at),
        time_to_release_seconds=_seconds(created_at, released_at),
        stage_seconds=stage_seconds,
        planned_agents=planned_agents,
        builder_agents=builder_agents,
        specialist_agents=specialist_agents,
        actual_agent_count=actual_agent_count,
        known_cost_usd=known_cost,
        unknown_paid_cost_events=unknown_paid,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached_tokens,
        codex_invocations=codex_invocations,
        ci_observed=ci_observed,
        first_pass_ci=(total_repairs == 0) if ci_observed else None,
        ci_repairs=ci_repairs,
        specialist_repairs=specialist_repairs,
        total_repairs=total_repairs,
    )


class SupabaseDeliveryMetricsReader:
    """Read-only aggregation over durable Control Plane evidence."""

    def __init__(self, *, url: str | None = None, secret_key: str | None = None, service_role_key: str | None = None) -> None:
        cfg = resolve_supabase_server_config(url=url, secret_key=secret_key, service_role_key=service_role_key)
        self.url = cfg.url
        self.headers = cfg.headers

    def _get(self, path: str) -> list[dict]:
        req = urllib.request.Request(f"{self.url}/rest/v1/{path}", headers=self.headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = response.read().decode()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"control-plane read failed: {path} ({exc.code})") from exc
        return [] if not raw else json.loads(raw)

    @staticmethod
    def _in(values: list[str]) -> str:
        return ",".join(values)

    def read(self, source_run_id: str) -> DeliveryMetrics:
        rid = quote(source_run_id)
        source_rows = self._get(
            "factory_runs?select=id,task_id,status,execution_route,created_at,started_at,finished_at"
            f"&id=eq.{rid}&limit=1"
        )
        if not source_rows:
            raise RuntimeError("source run not found")
        source = source_rows[0]
        task_rows = self._get(f"factory_tasks?select=project_id&id=eq.{quote(str(source['task_id']))}&limit=1")
        if not task_rows:
            raise RuntimeError("source run task not found")
        project_id = str(task_rows[0]["project_id"])
        projects = self._get(f"factory_projects?select=project_key&id=eq.{quote(project_id)}&limit=1")
        if not projects:
            raise RuntimeError("source run project not found")
        project_key = str(projects[0]["project_key"])

        team_rows = self._get(
            "factory_execution_team_plans?select=id,source_run_id,status,plan,created_at"
            f"&source_run_id=eq.{rid}&order=version.desc&limit=1"
        )
        team = team_rows[0] if team_rows else None
        change_set = None
        work_units: list[dict] = []
        repair_jobs: list[dict] = []
        if team:
            sets = self._get(
                "factory_change_sets?select=id,release_run_id,status,created_at,updated_at"
                f"&team_plan_id=eq.{quote(str(team['id']))}&order=created_at.desc&limit=1"
            )
            change_set = sets[0] if sets else None
        if change_set:
            cid = quote(str(change_set["id"]))
            work_units = self._get(
                "factory_change_set_work_units?select=id,agent_key,run_id,status,wave,created_at,updated_at"
                f"&change_set_id=eq.{cid}&order=created_at.asc"
            )
            repair_jobs = self._get(
                "factory_repair_jobs?select=id,source_run_id,source_role,cycle,status,created_at,updated_at"
                f"&change_set_id=eq.{cid}&order=created_at.asc"
            )

        run_ids = [source_run_id]
        run_ids.extend(str(row["run_id"]) for row in work_units if row.get("run_id"))
        if change_set and change_set.get("release_run_id"):
            run_ids.append(str(change_set["release_run_id"]))
        run_ids = list(dict.fromkeys(run_ids))
        in_runs = self._in(run_ids)

        family_runs = self._get(
            "factory_runs?select=id,status,execution_route,created_at,started_at,finished_at,attempt_count"
            f"&id=in.({in_runs})"
        )
        tool_usage = self._get(
            "factory_tool_usage?select=run_id,tool_family,operation,usage_units,estimated_cost,metadata,created_at"
            f"&run_id=in.({in_runs})"
        )
        codex_usage = self._get(
            "factory_codex_usage?select=run_id,invocation_count,reported_usage,created_at"
            f"&run_id=in.({in_runs})"
        )
        evaluations = self._get(
            "factory_evaluations?select=run_id,eval_type,status,score,result,created_at"
            f"&run_id=in.({in_runs})"
        )
        audit_events = self._get(
            "factory_audit_events?select=run_id,event_type,payload,created_at"
            f"&run_id=in.({in_runs})&order=created_at.asc"
        )
        specialist_jobs = self._get(
            "factory_specialist_lane_jobs?select=run_id,role,status,attempt_count,created_at,completed_at"
            f"&run_id=in.({in_runs})"
        )
        release_reports = self._get(
            "factory_release_reports?select=run_id,status,created_at,updated_at"
            f"&run_id=in.({in_runs})"
        )

        return derive_delivery_metrics(
            source_run=source,
            project_key=project_key,
            family_runs=family_runs,
            team_plan=team,
            work_units=work_units,
            specialist_jobs=specialist_jobs,
            tool_usage=tool_usage,
            codex_usage=codex_usage,
            evaluations=evaluations,
            repair_jobs=repair_jobs,
            audit_events=audit_events,
            release_reports=release_reports,
        )
