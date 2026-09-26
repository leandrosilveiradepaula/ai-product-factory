from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import quote

from .supabase_server import resolve_supabase_server_config


class SupabaseCodexUsageStore:
    """Updates the Codex invocation ledger created during routing."""

    def __init__(self,*,url:str|None=None,secret_key:str|None=None,service_role_key:str|None=None)->None:
        cfg=resolve_supabase_server_config(url=url,secret_key=secret_key,service_role_key=service_role_key)
        self.url=cfg.url
        self.headers=cfg.headers

    def _request(self,method:str,path:str,payload=None):
        headers={**self.headers,"Content-Type":"application/json"}
        if method=="PATCH": headers["Prefer"]="return=representation"
        data=None if payload is None else json.dumps(payload).encode()
        req=urllib.request.Request(f"{self.url}/rest/v1/{path}",data=data,headers=headers,method=method)
        try:
            with urllib.request.urlopen(req,timeout=30) as response: raw=response.read().decode()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Codex usage ledger request failed ({exc.code})") from exc
        return [] if not raw else json.loads(raw)

    def require_entry(self,run_id:str)->dict:
        rows=self._request("GET",f"factory_codex_usage?select=id,invocation_count,reported_usage&run_id=eq.{quote(run_id)}&order=created_at.desc&limit=1")
        if not rows:
            raise RuntimeError("Codex run has no routing usage ledger entry")
        return rows[0]

    def record_invocation(self,run_id:str,*,status:str,trace_events:int,error:str|None=None)->None:
        row=self.require_entry(run_id)
        usage=dict(row.get("reported_usage") or {})
        usage.update({
            "last_status":status,
            "trace_events":int(trace_events),
            "last_error":None if error is None else error[:2000],
            "recorded_at":datetime.now(timezone.utc).isoformat(),
            "cost_usd":None,
        })
        rows=self._request(
            "PATCH",
            f"factory_codex_usage?id=eq.{quote(str(row['id']))}",
            {"invocation_count":int(row.get("invocation_count") or 0)+1,"reported_usage":usage},
        )
        if not rows:
            raise RuntimeError("Codex usage ledger update was not persisted")
