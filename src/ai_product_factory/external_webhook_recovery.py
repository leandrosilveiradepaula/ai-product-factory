"""Bounded, service-role-only reconciliation of previously authenticated wake intents.

A completed authoritative queue probe may mark an eligible wake as observed
by the current Factory runner. This is NOT a GitHub redelivery, worker claim,
task execution, release, or proof of an HTTP 204.
"""
from __future__ import annotations
import json
import os
import re
import urllib.request
from .supabase_server import resolve_supabase_server_config

EXPECTED_URL="https://fjplmxfcshhbmzgvyqlm.supabase.co"

def reconcile_external_wakes(*, workflow_run_id:int, ci_work:bool, preview_work:bool,
                             release_work:bool, max_items:int=4)->dict:
    if not isinstance(workflow_run_id,int) or workflow_run_id<=0:
        raise ValueError("trusted workflow run id required")
    if any(type(x) is not bool for x in (ci_work,preview_work,release_work)):
        raise ValueError("authoritative lane booleans required")
    if type(max_items) is not int or not 1<=max_items<=8:
        raise ValueError("invalid bounded recovery batch")
    cfg=resolve_supabase_server_config()
    if cfg.url!=EXPECTED_URL:
        raise RuntimeError("unexpected Control Plane origin")
    body=json.dumps({"p_runner_run_id":workflow_run_id,"p_ci_work":ci_work,
        "p_preview_work":preview_work,"p_release_work":release_work,
        "p_max_items":max_items}).encode()
    req=urllib.request.Request(cfg.url+
       "/rest/v1/rpc/factory_reconcile_external_webhook_wakes_v1",
       data=body,headers={**cfg.headers,"Content-Type":"application/json"},
       method="POST")
    with urllib.request.urlopen(req,timeout=20) as response:
        payload=json.load(response)
    if not isinstance(payload,dict) or payload.get("status")!="ok":
        raise RuntimeError("invalid recovery receipt")
    fields=("inspected","runner_observed","suppressed","exhausted","deferred")
    if any(type(payload.get(k)) is not int or not 0<=payload[k]<=8 for k in fields):
        raise RuntimeError("invalid recovery counters")
    if sum(payload[k] for k in fields if k!="inspected")!=payload["inspected"]:
        raise RuntimeError("inconsistent recovery counters")
    return payload
