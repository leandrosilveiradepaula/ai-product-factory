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
            "quota_status":self._worst_quota(limits),
            "unknown_paid_cost":health.unknown_cost_events>0,
            "repair_rate":min(1.0,repair_rate),
            "first_pass_yield":min(1.0,max(0.0,first_pass)),
            "ci_queue_minutes":max(ci_ages,default=0.0),
            "known_cost":str(health.known_cost),
        }

    def work_matrix(self,limit:int=12)->dict:
        raw=self.scheduler.work_matrix(limit)
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
                key=str(item.get("agent_key") or "")
                if used[key]>=allowed.get(key,0):
                    continue
                filtered[route].append(item)
                used[key]+=1
        filtered["decisions"]=decisions
        return filtered
