"""Bounded read-only admission diagnosis. Observations never authorize claims."""
from __future__ import annotations

import json
import re
import urllib.request
from decimal import Decimal
from urllib.parse import quote

from .project_execution_control import ProjectExecutionState
from .primary_cost_config import SupabasePrimaryCostPolicyReader
from .supabase_operational_health import SupabaseOperationalHealthReader, KNOWN_RUN_STATUSES
from .preview_eligibility import is_delivery_preview_run
from .supabase_server import resolve_supabase_server_config
from .post_release_readiness import observe_manifest_release
from .admission_terminal_lineage import terminal_root_lineage

KEY = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,99}$")
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
RUNNING = frozenset({"running", "implementing", "planning", "routing", "preparing_codex_manual"})
WAITING = {"ci_pending": "ci", "awaiting_ci": "ci", "preview_ready": "preview",
           "specialist_review_pending": "review", "awaiting_release": "release",
           "awaiting_gate": "human_gate", "awaiting_human": "human_gate",
           "awaiting_codex_manual": "manual_codex", "review_ready": "review",
           "repair_pending": "repair"}
TERMINAL = frozenset({"completed", "integrated", "merged", "cancelled", "failed", "blocked"})
PRODUCT = frozenset({"created", "queued"})
MAX_ROWS = 100


def _one(rows: object, label: str, *, optional: bool = False) -> dict | None:
    if not isinstance(rows, list) or len(rows) > 1 or any(not isinstance(x, dict) for x in rows):
        raise RuntimeError("inconsistent " + label)
    if not rows:
        if optional:
            return None
        raise RuntimeError("missing " + label)
    return rows[0]


def _many(rows: object, label: str) -> list[dict]:
    if not isinstance(rows, list) or len(rows) >= MAX_ROWS or any(not isinstance(x, dict) for x in rows):
        raise RuntimeError("incomplete or inconsistent " + label)
    return rows


def _id(value: object) -> str:
    if not isinstance(value, str) or not UUID.fullmatch(value):
        raise RuntimeError("invalid Control Plane identity")
    return value.lower()


def classify(*, project: dict, control: dict, commands: list[dict],
             tasks: list[dict], runs: list[dict], run_id: str | None,
             cost: dict, planned: list[dict], portfolio: list[dict],
             readiness: dict | None = None,
             terminal_lineage: dict | None = None,
             historical_repairs: set[str] | None = None) -> dict:
    """Pure classification; absence of a claim is not proof of scheduler health."""
    pid = _id(project.get("id"))
    if not isinstance(project.get("project_key"), str) or not project["project_key"]:
        raise RuntimeError("invalid project key")
    if _id(control.get("project_id")) != pid or control.get("state") not in ProjectExecutionState._value2member_map_:
        raise RuntimeError("inconsistent project execution control")
    state = control["state"]
    if project.get("is_active") is not True and state == "running":
        raise RuntimeError("inactive project has running control")
    task_ids = set()
    for task in tasks:
        tid = _id(task.get("id"))
        if tid in task_ids or _id(task.get("project_id")) != pid:
            raise RuntimeError("cross-project or duplicate task")
        task_ids.add(tid)
    seen = set()
    for run in runs:
        rid = _id(run.get("id"))
        if rid in seen or _id(run.get("task_id")) not in task_ids:
            raise RuntimeError("cross-project, orphan or duplicate run")
        if run.get("status") not in KNOWN_RUN_STATUSES:
            raise RuntimeError("unknown run status")
        if run.get("metadata") is not None and not isinstance(run["metadata"],dict):
            raise RuntimeError("malformed run metadata")
        seen.add(rid)
    for command in commands:
        if _id(command.get("project_id")) != pid or command.get("command") not in {"start","resume","restart","pause","stop"}:
            raise RuntimeError("inconsistent control command")
    if any(not isinstance(x, dict) or x.get("project_id") != pid for x in portfolio):
        raise RuntimeError("inconsistent portfolio eligibility")
    if any(not isinstance(x, dict) or x.get("project_key") != project.get("project_key") for x in planned):
        raise RuntimeError("inconsistent planned work")
    if run_id and run_id.lower() not in seen:
        raise RuntimeError("run not found within project")
    if not isinstance(cost, dict) or cost.get("state") not in {"available","blocked","unknown"}:
        raise RuntimeError("invalid cost observation")
    if terminal_lineage is not None and (
        not run_id or not isinstance(terminal_lineage,dict)
        or terminal_lineage.get("status") not in {"blocked","waiting"}
        or terminal_lineage.get("next_step") not in {
            "review_obsolete_change_set_evidence","review_blocked_change_set",
            "review_terminal_change_set","inspect_change_set_eligibility",
            "verify_release_boundary","review_new_human_continuation",
        }
        or not isinstance(terminal_lineage.get("reason_code"),str)
        or not terminal_lineage["reason_code"].startswith("root_change_set_")
        or not isinstance(terminal_lineage.get("evidence"),dict)
        or terminal_lineage["evidence"].get("delivery_verified") is not False
    ):
        raise RuntimeError("invalid exact terminal lineage evidence")
    historical_repairs = historical_repairs or set()
    if not historical_repairs.issubset(seen) or any(
        r["status"] != "repair_pending" for r in runs if r["id"] in historical_repairs
    ):
        raise RuntimeError("invalid historical repair evidence")
    # A run receipt is an exact run/task identity, not a workflow heartbeat.
    receipt = next((r for r in runs if run_id and r["id"].lower() == run_id.lower()),None)
    if terminal_lineage is not None:
        exact_task=next((t for t in tasks if receipt and t["id"].lower()==receipt["task_id"].lower()),None)
        if (receipt is None or receipt.get("status") not in TERMINAL
            or exact_task is None or exact_task.get("parent_task_id") is not None):
            raise RuntimeError("terminal lineage not bound to a terminal root")
    def delivery_wait(r: dict) -> bool:
        return r.get("status") in WAITING and (
            r.get("status") != "preview_ready" or is_delivery_preview_run(r)
        )
    def credible_running(r: dict) -> bool:
        return r.get("status") in RUNNING and isinstance(r.get("started_at"),str) and bool(r["started_at"].strip())
    if state != "running":
        status,reason,next_step = "blocked","project_"+state,"operator_control"
    elif run_id:
        selected = receipt
        assert selected is not None
        selected_task = next(t for t in tasks if t["id"].lower() == selected["task_id"].lower())
        s = selected.get("status")
        if s in RUNNING:
            if credible_running(selected):
                status,reason,next_step = "in_progress","run_"+s,"worker_or_recovery"
            else:
                status,reason,next_step = "blocked","running_without_claim_receipt","inspect_run_claim"
        elif s == "preview_ready" and not is_delivery_preview_run(selected):
            status,reason,next_step = "waiting","historical_preview_audit_only","no_new_action"
        elif s == "repair_pending" and selected["id"] in historical_repairs:
            status,reason,next_step = "waiting","historical_terminal_repair","no_new_action"
        elif s in WAITING:
            status,reason,next_step = "waiting","run_"+s,WAITING[s]
        elif s in TERMINAL:
            status,reason,next_step = "blocked" if s in {"failed","blocked"} else "waiting","run_"+s,"review_terminal_run" if s in {"failed","blocked"} else "no_new_action"
            # Product Stage completion alone never proves that a descendant
            # Change Set reached CI, Preview, or human release.
            if terminal_lineage is not None:
                status=terminal_lineage["status"]
                reason=terminal_lineage["reason_code"]
                next_step=terminal_lineage["next_step"]
        elif s in PRODUCT:
            if selected_task.get("status") == "queued_execution" and selected.get("execution_route") in {"direct","codex"}:
                status,reason,next_step = "waiting","routed_execution_not_yet_claimed","agent_scheduler"
            elif selected_task.get("status") != "queued":
                status,reason,next_step = "blocked","run_not_product_eligible","inspect_task_state"
            else:
                status,reason,next_step = "eligible","product_stage_queued","product_stage"
        else:
            raise RuntimeError("unknown run status")
    elif any(r.get("status") in RUNNING for r in runs):
        receipt = next(r for r in runs if r.get("status") in RUNNING)
        if credible_running(receipt):
            status,reason,next_step = "in_progress","running_work_observed","worker_or_recovery"
        else:
            status,reason,next_step = "blocked","running_without_claim_receipt","inspect_run_claim"
    elif any(delivery_wait(r) and r["id"] not in historical_repairs for r in runs):
        receipt = next(r for r in runs if delivery_wait(r) and r["id"] not in historical_repairs)
        status,reason,next_step = "waiting","run_"+receipt["status"],WAITING[receipt["status"]]
    elif any(r.get("status") in PRODUCT and any(t["id"] == r["task_id"] and t.get("status") == "queued" for t in tasks) for r in runs):
        receipt = next(r for r in runs if r.get("status") in PRODUCT and any(t["id"] == r["task_id"] and t.get("status") == "queued" for t in tasks))
        status,reason,next_step = "eligible","product_stage_queued","product_stage"
    elif any(r.get("status") == "queued" and r.get("execution_route") in {"direct","codex"} and any(t["id"] == r["task_id"] and t.get("status") == "queued_execution" for t in tasks) for r in runs):
        receipt = next(r for r in runs if r.get("status") == "queued" and r.get("execution_route") in {"direct","codex"} and any(t["id"] == r["task_id"] and t.get("status") == "queued_execution" for t in tasks))
        status,reason,next_step = "waiting","routed_execution_not_yet_claimed","agent_scheduler"
    elif planned and portfolio:
        status,reason,next_step = "eligible","planned_work_admitted","dispatch"
    elif planned:
        status,reason,next_step = "blocked","portfolio_not_eligible","inspect_portfolio_constraints"
    elif any(c["command"] == "start" for c in commands) and not runs:
        status,reason,next_step = "blocked","start_without_bootstrap","inspect_bootstrap"
    elif not commands and not runs:
        status,reason,next_step = "waiting","no_start_or_bootstrap","operator_start"
    else:
        status,reason,next_step = "waiting","no_current_eligible_work","review_project_backlog"
    # Empty scheduler queue and an unassessed released product are different
    # findings. Never manufacture work, restart historical runs, or imply
    # global readiness from release completion.
    if (not run_id and status == "waiting"
            and reason in {"no_current_eligible_work", "no_start_or_bootstrap"}
            and project.get("lifecycle_stage") == "operations"
            and isinstance(readiness, dict) and readiness.get("ready") is False):
        reason = "idle_with_unassessed_global_product_readiness"
        next_step = "global_product_readiness_audit"
    if status == "eligible" and next_step in {"product_stage","dispatch"} and cost["state"] != "available":
        status,reason,next_step = "blocked",cost.get("reason") or "cost_unverified","review_cost_policy_and_ledger"
    task_by_id = {t["id"].lower(): t for t in tasks}
    run_evidence = None
    if receipt is not None:
        run_evidence = {"run_id":_id(receipt["id"]),"task_id":_id(receipt["task_id"]),
                        "run_status":receipt["status"],
                        "task_status":task_by_id[_id(receipt["task_id"])].get("status")}
    extra_evidence=({"terminal_change_set":terminal_lineage["evidence"]}
                    if terminal_lineage is not None else {})
    return {"project_key":project["project_key"],"project_id":pid,"run_id":run_id,
            "project_state":state,"status":status,"reason_code":reason,"next_step":next_step,
            "eligibility_scope":"database_observation_not_claim_authorization",
            "evidence":{"control":{"state":state,"version":control.get("version"),
                                   "generation":control.get("generation")},
                        "run":run_evidence,"command_count":len(commands),
                        "task_count":len(tasks),"run_count":len(runs),
                        "planned_admitted_count":len(planned),"portfolio_eligible":bool(portfolio),
                        "cost":cost,
                        "product_readiness":readiness,**extra_evidence},"read_only":True}


class SupabaseAdmissionReader:
    def __init__(self, *, url: str | None = None, secret_key: str | None = None,
                 service_role_key: str | None = None, get=None, policy_reader=None, health_reader=None):
        if get is None:
            cfg = resolve_supabase_server_config(url=url,secret_key=secret_key,service_role_key=service_role_key)
            self.url,self.headers = cfg.url,cfg.headers
        self.get_override=get
        self.policy_reader=policy_reader
        self.health_reader=health_reader

    def _get(self, path: str) -> list[dict]:
        if self.get_override is not None:
            return self.get_override(path)
        req=urllib.request.Request(self.url+"/rest/v1/"+path,headers=self.headers,method="GET")
        with urllib.request.urlopen(req,timeout=20) as resp:
            return json.loads(resp.read().decode())

    def _rpc_read(self, name: str, payload: dict):
        # These specific existing RPCs only select; no claim, dispatch or audit writes.
        if self.get_override is not None:
            return self.get_override("rpc/"+name+" "+json.dumps(payload,sort_keys=True))
        req=urllib.request.Request(self.url+"/rest/v1/rpc/"+name,
            data=json.dumps(payload).encode(),headers={**self.headers,"Content-Type":"application/json"},method="POST")
        with urllib.request.urlopen(req,timeout=20) as resp:
            return json.loads(resp.read().decode())

    def _cost(self) -> dict:
        try:
            policy=(self.policy_reader or SupabasePrimaryCostPolicyReader()).read()
            health=(self.health_reader or SupabaseOperationalHealthReader()).read(budget=policy.budget_usd)
            known=Decimal(str(health.known_cost))
            if not known.is_finite() or known < 0 or health.unknown_cost_events < 0:
                raise ValueError("invalid ledger")
            if health.unknown_cost_events:
                return {"state":"blocked","reason":"paid_cost_unknown"}
            if known+policy.reserve_usd>policy.budget_usd:
                return {"state":"blocked","reason":"budget_exhausted"}
            return {"state":"available","reason":"within_budget"}
        except Exception:
            return {"state":"unknown","reason":"cost_policy_or_ledger_unavailable"}

    def read(self, *, project_key: str, run_id: str | None = None) -> dict:
        if not isinstance(project_key,str) or not KEY.fullmatch(project_key):
            raise ValueError("invalid --project-key")
        if run_id is not None and (not isinstance(run_id,str) or not UUID.fullmatch(run_id)):
            raise ValueError("invalid --run-id")
        project=_one(self._get("factory_projects?select=id,project_key,is_active,lifecycle_stage,manifest&project_key=eq."+quote(project_key)+"&limit=2"),"project")
        if project.get("project_key") != project_key:
            raise RuntimeError("project identity mismatch")
        pid=_id(project.get("id"))
        control=_one(self._get("factory_project_execution_controls?select=project_id,state,version,generation&project_id=eq."+pid+"&limit=2"),"control")
        commands=_many(self._get("factory_project_execution_commands?select=project_id,command&project_id=eq."+pid+"&order=created_at.desc&limit=101"),"commands")
        tasks=_many(self._get("factory_tasks?select=id,project_id,parent_task_id,status&project_id=eq."+pid+"&order=created_at.desc&limit=101"),"tasks")
        if tasks:
            tids=",".join(_id(t.get("id")) for t in tasks)
            runs=_many(self._get("factory_runs?select=id,task_id,status,metadata,execution_route,started_at,lease_owner,lease_expires_at&task_id=in.("+tids+")&order=created_at.desc&limit=101"),"runs")
        else:
            runs=[]
        # A completed root/Change Set with no leases is historical evidence,
        # not a runnable repair. Verify the exact lineage before excluding it.
        historical_repairs=set()
        pending=[r for r in runs if r["status"]=="repair_pending"]
        if pending:
            candidate_ids=set()
            for r in pending:
                metadata=r.get("metadata") or {}
                cs_id=metadata.get("change_set_id")
                if isinstance(cs_id,str) and UUID.fullmatch(cs_id):
                    candidate_ids.add(cs_id.lower())
            if candidate_ids:
                rows=_many(self._get("factory_change_sets?select=id,project_id,root_task_id,status,lease_owner,lease_expires_at&id=in.("+",".join(sorted(candidate_ids))+")&limit=101"),"repair Change Sets")
                by_id={_id(cs["id"]):cs for cs in rows}
                if len(by_id)!=len(rows):
                    raise RuntimeError("duplicate repair Change Set")
                task_by_id={t["id"]:t for t in tasks}
                for r in pending:
                    cs_id=(r.get("metadata") or {}).get("change_set_id")
                    cs=by_id.get(cs_id.lower()) if isinstance(cs_id,str) else None
                    task=task_by_id.get(r["task_id"])
                    if (cs and task and cs.get("project_id")==pid
                        and cs.get("root_task_id")==task["id"]
                        and cs.get("status")=="completed"
                        and task.get("status")=="completed"
                        and task.get("parent_task_id") is None
                        and not cs.get("lease_owner") and cs.get("lease_expires_at") is None
                        and not r.get("lease_owner") and r.get("lease_expires_at") is None):
                        historical_repairs.add(r["id"])
        # Exact-root Change Set inventory: only for a terminal run whose task
        # has no parent. Stale Change Sets may not be assigned to another root.
        terminal_lineage=None
        if run_id:
            selected_run=next((r for r in runs if r.get("id")==run_id),None)
            selected_task=next((t for t in tasks if selected_run and
                 t.get("id")==selected_run.get("task_id")),None)
            if (selected_run and selected_task
                and selected_task.get("parent_task_id") is None
                and selected_run.get("status") in TERMINAL):
                root_id=_id(selected_task["id"])
                sets=_many(self._get(
                    "factory_change_sets?select=id,project_id,root_task_id,"
                    "status,release_run_id,created_at"
                    "&project_id=eq."+pid+"&root_task_id=eq."+root_id
                    +"&order=created_at.desc&limit=31"
                ),"exact root Change Sets")
                if len(sets)>30:
                    raise RuntimeError("too many exact-root Change Sets")
                units=[]
                if sets:
                    cs_ids=",".join(_id(x["id"]) for x in sets)
                    units=_many(self._get(
                        "factory_change_set_work_units?select=id,change_set_id,"
                        "status,output_commit&change_set_id=in.("+cs_ids+")"
                        "&limit=31"
                    ),"exact root Work Units")
                    if len(units)>30:
                        raise RuntimeError("too many exact-root Work Units")
                terminal_lineage=terminal_root_lineage(
                    project_id=pid,root_task_id=root_id,
                    root_run=selected_run,
                    current_generation=control.get("generation"),
                    change_sets=sets,work_units=units,
                )
        # Existing atomic-dispatch read contract, not task counts.
        planned=self._rpc_read("factory_peek_planned_work",{"p_project_key":project_key,"p_limit":100})
        portfolio=self._rpc_read("factory_portfolio_candidates",{"p_limit":100})
        if not isinstance(portfolio,list) or len(portfolio)>100:
            raise RuntimeError("inconsistent portfolio response")
        readiness = observe_manifest_release(
            get=self._get,project_id=pid,manifest=project.get("manifest")
        )
        return classify(project=project,control=control,commands=commands,tasks=tasks,
            runs=runs,run_id=run_id,cost=self._cost(),
            planned=_many(planned,"planned candidates"),
            portfolio=[p for p in portfolio if isinstance(p,dict) and p.get("project_id")==pid],
            readiness=readiness,terminal_lineage=terminal_lineage,
            historical_repairs=historical_repairs)
