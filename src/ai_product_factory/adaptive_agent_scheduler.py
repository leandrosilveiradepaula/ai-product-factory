from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime,timezone
from decimal import Decimal

from .adaptive_concurrency import ConcurrencyPressure,decide_effective_concurrency
from .agent_scheduler import SupabaseAgentScheduler
from .supabase_operational_health import SupabaseOperationalHealthReader
from .supabase_server import resolve_supabase_server_config


_STATUS_RANK={"normal":0,"attention":1,"unknown":2,"critical":3,"blocked":4}


class SupabaseAdaptiveConcurrencyController:
    def __init__(self,*,url:str|None=None,secret_key:str|None=None,service_role_key:str|None=None)->None:
        cfg=resolve_supabase_server_config(url=url,secret_key=secret_key,service_role_key=service_role_key)
        self.url=cfg.url;self.headers=cfg.headers
        self.scheduler=SupabaseAgentScheduler(url=cfg.url,service_role_key=cfg.key)
        self.health=SupabaseOperationalHealthReader(url=cfg.url,service_role_key=cfg.key)

    def _get(self,path:str)->list[dict]:
        req=urllib.request.Request(f"{self.url}/rest/v1/{path}",headers=self.headers,method="GET")
        try:
            with urllib.request.urlopen(req,timeout=30) as response:raw=response.read().decode()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"control-plane read failed: {path} ({exc.code})") from exc
        return [] if not raw else json.loads(raw)

    def _rpc(self,name:str,payload:dict):
        req=urllib.request.Request(
            f"{self.url}/rest/v1/rpc/{name}",data=json.dumps(payload).encode(),
            headers={**self.headers,"Content-Type":"application/json"},method="POST",
        )
        try:
            with urllib.request.urlopen(req,timeout=30) as response:raw=response.read().decode()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"control-plane RPC failed: {name} ({exc.code})") from exc
        return None if not raw else json.loads(raw)

    @staticmethod
    def _worst_quota(rows:list[dict])->str:
        latest={}
        for row in rows:
            key=(str(row.get("provider") or ""),str(row.get("resource_key") or ""),str(row.get("metric_key") or ""))
            if key not in latest:
                latest[key]=str(row.get("status") or "unknown")
        if not latest:return "unknown"
        return max(latest.values(),key=lambda status:_STATUS_RANK.get(status,2))


    @classmethod
    def _execution_quota_status(cls, rows:list[dict])->str:
        """Only provider limits relevant to Direct/Codex execution gate the matrix.

        Vercel *deployments_daily* is a Preview/Release quota, not a condition
        for a GitHub Direct/Codex code-writing job. Other providers and other
        Vercel metrics retain their current conservative blocked semantics.
        If no applicable provider has a snapshot, quota is unknown and limits
        concurrency to one; it never authorizes a paid provider call.
        """
        applicable=[
            row for row in rows
            if not (
                str(row.get("provider") or "").strip().lower()=="vercel"
                and str(row.get("metric_key") or "").strip().lower()=="deployments_daily"
            )
        ]
        return cls._worst_quota(applicable)

    @classmethod
    def _preview_deployment_quota_status(cls, rows:list[dict])->str:
        return cls._worst_quota([
            row for row in rows
            if str(row.get("provider") or "").strip().lower()=="vercel"
            and str(row.get("metric_key") or "").strip().lower()=="deployments_daily"
        ])

    def _global_pressure(self)->dict:
        limits=self._get(
            "factory_resource_limit_snapshots?select=provider,resource_key,metric_key,status,observed_at"
            "&order=observed_at.desc&limit=100"
        )
        runs=self._get("factory_runs?select=status,created_at&order=created_at.desc&limit=100")
        evals=self._get("factory_evaluations?select=eval_type,status,created_at&order=created_at.desc&limit=100")
        health=self.health.read()

        repairable=[row for row in runs if str(row.get("status") or "") in {"needs_correction","failed","specialist_review_failed"}]
        repair_rate=(len(repairable)/len(runs)) if runs else 0.0

        ci_evals=[row for row in evals if str(row.get("eval_type") or "")=="github_ci"]
        ci_success=sum(1 for row in ci_evals if str(row.get("status") or "")=="success")
        first_pass=(ci_success/len(ci_evals)) if ci_evals else 1.0

        now=datetime.now(timezone.utc)
        ci_ages=[]
        for row in runs:
            if str(row.get("status") or "")!="ci_pending":continue
            raw=row.get("created_at")
            if not raw:continue
            created=datetime.fromisoformat(str(raw).replace("Z","+00:00"))
            ci_ages.append(max(0.0,(now-created).total_seconds()/60))
        return {
            "quota_status":self._execution_quota_status(limits),
            # Diagnostic only for specialist dispatch: Preview always keeps
            # its separate, authoritative Vercel rate-limit gate.
            "preview_deployment_quota_status":self._preview_deployment_quota_status(limits),
            "unknown_paid_cost":health.unknown_cost_events>0,
            "repair_rate":min(1.0,repair_rate),
            "first_pass_yield":min(1.0,max(0.0,first_pass)),
            "ci_queue_minutes":max(ci_ages,default=0.0),
            "known_cost":str(health.known_cost),
        }

    @staticmethod
    def _required_item(item:object)->dict:
        """Validate an assignment just committed by the route-safe scheduler.

        ``required`` is not an alternate queue or caller-controlled work list.
        It is a bounded receipt returned by ``factory_schedule_eligible_*`` in
        the same runner invocation.  Keeping its shape strict prevents a
        workflow matrix from being populated with an unclaimed run while still
        allowing a newly assigned run to survive an older global SQL window.
        """
        if not isinstance(item,dict):
            raise RuntimeError("required scheduler assignment must be an object")
        run_id=item.get("run_id")
        agent_key=item.get("agent_key")
        role=item.get("role")
        if any(not isinstance(value,str) or not value.strip()
               for value in (run_id,agent_key,role)):
            raise RuntimeError("required scheduler assignment is incomplete")
        return {"run_id":run_id,"agent_key":agent_key,"role":role}

    def work_matrix(self,limit:int=12,*,required:dict[str,list[dict]]|None=None)->dict:
        if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=32:
            raise ValueError("matrix limit must be between 1 and 32")
        required=required or {}
        if not isinstance(required,dict) or set(required)-{"direct","codex"}:
            raise ValueError("required matrix routes are invalid")
        required_rows={
            route:[self._required_item(item)
                   for item in list(required.get(route) or [])]
            for route in ("direct","codex")
        }
        if sum(len(rows) for rows in required_rows.values())>limit:
            raise ValueError("required matrix exceeds the bounded runner batch")

        # The ordinary read remains bounded to the requested batch.  When the
        # route-safe scheduler has just assigned work, read the maximum
        # supported window so the concurrency policy can consider older work
        # too, but place only the exact fresh receipts ahead of that window.
        raw=self.scheduler.work_matrix(32 if any(required_rows.values()) else limit)
        merged={}
        for route in ("direct","codex"):
            seen=set()
            rows=[]
            for item in required_rows[route]+list(raw.get(route) or []):
                if not isinstance(item,dict):
                    raise RuntimeError("scheduler matrix item must be an object")
                run_id=item.get("run_id")
                if not isinstance(run_id,str) or not run_id.strip():
                    raise RuntimeError("scheduler matrix item lacks run ID")
                if run_id in seen:
                    continue
                seen.add(run_id)
                rows.append(item)
            merged[route]=rows
        raw=merged
        all_items=list(raw.get("direct") or [])+list(raw.get("codex") or [])
        by_agent:dict[str,list[dict]]=defaultdict(list)
        for item in all_items:
            by_agent[str(item.get("agent_key") or "")].append(item)

        profiles={profile.agent_key:profile for profile in self.scheduler.profiles()}
        global_pressure=self._global_pressure()
        allowed:dict[str,int]={}
        decisions=[]

        for agent_key,items in sorted(by_agent.items()):
            profile=profiles.get(agent_key)
            if profile is None:
                allowed[agent_key]=0
                continue
            pressure=ConcurrencyPressure(
                runnable_work=len(items),
                quota_status=str(global_pressure["quota_status"]),
                unknown_paid_cost=bool(global_pressure["unknown_paid_cost"]),
                conflict_rate=0.0,
                repair_rate=float(global_pressure["repair_rate"]),
                first_pass_yield=float(global_pressure["first_pass_yield"]),
                ci_queue_minutes=float(global_pressure["ci_queue_minutes"]),
            )
            decision=decide_effective_concurrency(
                agent_key=agent_key,profile_ceiling=profile.max_concurrency,pressure=pressure
            )
            allowed[agent_key]=decision.effective_concurrency
            payload={
                "quota_status":pressure.quota_status,
                "preview_deployment_quota_status":global_pressure["preview_deployment_quota_status"],
                "unknown_paid_cost":pressure.unknown_paid_cost,
                "conflict_rate":pressure.conflict_rate,
                "repair_rate":pressure.repair_rate,
                "first_pass_yield":pressure.first_pass_yield,
                "ci_queue_minutes":pressure.ci_queue_minutes,
                "known_cost":global_pressure["known_cost"],
            }
            self._rpc("factory_record_agent_concurrency_decision",{
                "p_agent_key":agent_key,
                "p_effective_concurrency":decision.effective_concurrency,
                "p_profile_ceiling":decision.profile_ceiling,
                "p_runnable_work":pressure.runnable_work,
                "p_pressure":payload,
                "p_reasons":list(decision.reasons),
            })
            decisions.append({
                "agent_key":agent_key,
                "effective_concurrency":decision.effective_concurrency,
                "profile_ceiling":decision.profile_ceiling,
                "runnable_work":pressure.runnable_work,
                "reasons":list(decision.reasons),
            })

        used:dict[str,int]=defaultdict(int)
        filtered={"direct":[],"codex":[]}
        for route in ("direct","codex"):
            for item in raw.get(route) or []:
                if sum(len(rows) for rows in filtered.values())>=limit:
                    break
                key=str(item.get("agent_key") or "")
                if used[key]>=allowed.get(key,0):
                    continue
                filtered[route].append(item)
                used[key]+=1
        filtered["decisions"]=decisions
        return filtered
