from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass
from urllib.parse import quote

from .supabase_server import resolve_supabase_server_config


@dataclass(frozen=True)
class ImpactAnalysis:
    brain_snapshot_id:str|None
    confidence:str
    seed_nodes:tuple[str,...]
    impacted_nodes:tuple[dict,...]
    unknowns:tuple[str,...]
    summary:str

    def as_context(self)->dict:
        return {
            "confidence":self.confidence,
            "seed_nodes":list(self.seed_nodes),
            "impacted_nodes":list(self.impacted_nodes),
            "unknowns":list(self.unknowns),
            "summary":self.summary,
        }


def analyze_project_brain_impact(*,nodes:list[dict],edges:list[dict],task_key:str,max_depth:int=3)->ImpactAnalysis:
    if max_depth<1 or max_depth>6:raise ValueError("max_depth must be between 1 and 6")
    by_id={str(row["id"]):row for row in nodes if row.get("id")}
    by_key={str(row.get("node_key") or ""):row for row in nodes}
    seed_key=f"task:{task_key}"
    seed=by_key.get(seed_key)
    if seed is None:
        return ImpactAnalysis(None,"unknown",(),(),(f"task node not found: {seed_key}",),"No exact task node exists in the current Project Brain.")

    adjacency:dict[str,list[tuple[str,str,str]]]={}
    for edge in edges:
        source=str(edge.get("from_node_id") or "");target=str(edge.get("to_node_id") or "");relation=str(edge.get("relation") or "")
        if source not in by_id or target not in by_id:continue
        if relation=="contains":continue
        adjacency.setdefault(source,[]).append((target,relation,"out"))
        adjacency.setdefault(target,[]).append((source,relation,"in"))

    start=str(seed["id"])
    queue=deque([(start,0,"seed")])
    seen={start}
    impacted=[]
    while queue:
        current,distance,reason=queue.popleft()
        row=by_id[current]
        impacted.append({
            "node_key":str(row.get("node_key") or ""),
            "node_type":str(row.get("node_type") or ""),
            "name":str(row.get("name") or ""),
            "distance":distance,
            "reason":reason,
        })
        if distance>=max_depth:continue
        for nxt,relation,direction in adjacency.get(current,[]):
            if nxt in seen:continue
            next_row=by_id[nxt]
            if str(next_row.get("node_type") or "")=="project":continue
            seen.add(nxt)
            queue.append((nxt,distance+1,f"{direction}:{relation}"))

    direct_types={x["node_type"] for x in impacted if x["distance"]<=1}
    confidence="high" if {"scope","capability"} & direct_types else "medium"
    unknowns=[]
    if not any(x["node_type"]=="scope" for x in impacted):
        unknowns.append("no repository scope connected to task")
        confidence="medium"
    summary=f"{task_key}: {len(impacted)} Project Brain node(s) within depth {max_depth}; confidence={confidence}"
    snapshot_id=str(seed.get("snapshot_id") or "") or None
    return ImpactAnalysis(snapshot_id,confidence,(seed_key,),tuple(impacted),tuple(unknowns),summary)


class SupabaseImpactEngine:
    def __init__(self,*,url:str|None=None,secret_key:str|None=None,service_role_key:str|None=None)->None:
        cfg=resolve_supabase_server_config(url=url,secret_key=secret_key,service_role_key=service_role_key)
        self.url=cfg.url;self.headers=cfg.headers

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

    def analyze_and_record(self,*,project_key:str,task_key:str,task_id:str,run_id:str,change_set_id:str|None)->ImpactAnalysis:
        projects=self._get("factory_projects?select=id&project_key=eq."+quote(project_key)+"&is_active=eq.true&limit=1")
        if not projects:raise RuntimeError("active project not found for impact analysis")
        project_id=str(projects[0]["id"])
        snaps=self._get(
            "factory_project_brain_snapshots?select=id&project_id=eq."+quote(project_id)+
            "&status=eq.current&order=version.desc&limit=1"
        )
        if not snaps:
            analysis=ImpactAnalysis(None,"unknown",(),(),("Project Brain snapshot unavailable",),"Project Brain snapshot unavailable; impact is unknown.")
        else:
            snapshot_id=str(snaps[0]["id"])
            nodes=self._get(
                "factory_project_brain_nodes?select=id,snapshot_id,node_key,node_type,name,attributes"
                "&snapshot_id=eq."+quote(snapshot_id)+"&limit=1000"
            )
            edges=self._get(
                "factory_project_brain_edges?select=from_node_id,to_node_id,relation"
                "&snapshot_id=eq."+quote(snapshot_id)+"&limit=2000"
            )
            analysis=analyze_project_brain_impact(nodes=nodes,edges=edges,task_key=task_key)
            analysis=ImpactAnalysis(snapshot_id,analysis.confidence,analysis.seed_nodes,analysis.impacted_nodes,analysis.unknowns,analysis.summary)
        self._rpc("factory_record_impact_analysis",{
            "p_project_id":project_id,"p_brain_snapshot_id":analysis.brain_snapshot_id,
            "p_task_id":task_id,"p_run_id":run_id,"p_change_set_id":change_set_id,
            "p_confidence":analysis.confidence,"p_seed_nodes":list(analysis.seed_nodes),
            "p_impacted_nodes":list(analysis.impacted_nodes),"p_unknowns":list(analysis.unknowns),
            "p_summary":analysis.summary,
        })
        return analysis
