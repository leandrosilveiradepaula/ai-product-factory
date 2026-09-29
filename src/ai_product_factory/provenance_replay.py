from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .supabase_server import resolve_supabase_server_config
import urllib.error
import urllib.request


PROVENANCE_SCHEMA_VERSION=1
TEAM_PLANNER_VERSION="1"
ROUTER_POLICY_VERSION="v2"
ADAPTIVE_CONCURRENCY_VERSION="1"
RELEASE_POLICY_VERSION="v1"


def canonical_hash(value:Any)->str:
    raw=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def build_run_provenance(*,run_id:str,project_key:str,route:str,agent_key:str|None,
                         context_packet:dict|None,team_plan:dict|None,
                         project_manifest:dict|None,candidate_commit:str|None=None)->dict:
    snapshot={
        "schema_version":PROVENANCE_SCHEMA_VERSION,
        "run_id":run_id,
        "project_key":project_key,
        "execution":{
            "route":route,
            "agent_key":agent_key,
            "candidate_commit":candidate_commit,
        },
        "versions":{
            "team_planner":TEAM_PLANNER_VERSION,
            "router_policy":ROUTER_POLICY_VERSION,
            "adaptive_concurrency":ADAPTIVE_CONCURRENCY_VERSION,
            "release_policy":RELEASE_POLICY_VERSION,
        },
        "context_packet_hash":(context_packet or {}).get("sha256"),
        "team_plan_version":(team_plan or {}).get("version"),
        "project_manifest_hash":canonical_hash(project_manifest or {}),
    }
    snapshot["snapshot_hash"]=canonical_hash(snapshot)
    return snapshot


@dataclass(frozen=True)
class ReplayRequest:
    replay_id:str
    source_run_id:str
    mode:str
    status:str
    effect:str
    model_calls_allowed:bool
    snapshot_hash:str


class SupabaseProvenanceStore:
    def __init__(self,*,url:str|None=None,secret_key:str|None=None,service_role_key:str|None=None)->None:
        cfg=resolve_supabase_server_config(url=url,secret_key=secret_key,service_role_key=service_role_key)
        self.url=cfg.url;self.headers=cfg.headers

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

    def record(self,*,run_id:str,snapshot:dict)->dict:
        expected=canonical_hash({k:v for k,v in snapshot.items() if k!="snapshot_hash"})
        if snapshot.get("snapshot_hash")!=expected:
            raise ValueError("provenance snapshot hash mismatch")
        return self._rpc("factory_record_run_provenance",{
            "p_run_id":run_id,"p_snapshot_hash":expected,"p_snapshot":snapshot,
        }) or {}

    def create_replay(self,source_run_id:str,mode:str="offline")->ReplayRequest:
        data=self._rpc("factory_create_replay_request",{"p_source_run_id":source_run_id,"p_mode":mode})
        if not isinstance(data,dict):raise RuntimeError("replay request returned no data")
        return ReplayRequest(
            replay_id=str(data["replay_id"]),source_run_id=str(data["source_run_id"]),
            mode=str(data["mode"]),status=str(data["status"]),effect=str(data["effect"]),
            model_calls_allowed=bool(data["model_calls_allowed"]),snapshot_hash=str(data["snapshot_hash"]),
        )

    def record_shadow(self,*,source_run_id:str,replay_id:str,component:str,component_version:str,
                      input_value:dict,decision:dict,observed_outcome:dict|None=None)->dict:
        return self._rpc("factory_record_shadow_decision",{
            "p_source_run_id":source_run_id,"p_replay_id":replay_id,
            "p_component":component,"p_component_version":component_version,
            "p_input_hash":canonical_hash(input_value),"p_decision":decision,
            "p_observed_outcome":observed_outcome or {},
        }) or {}

    def propose(self,*,source_run_id:str|None,proposal_key:str,evidence:dict,proposed_change:dict)->dict:
        return self._rpc("factory_propose_improvement",{
            "p_source_run_id":source_run_id,"p_proposal_key":proposal_key,
            "p_evidence":evidence,"p_proposed_change":proposed_change,
        }) or {}
