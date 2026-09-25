import json
from unittest.mock import patch
from ai_product_factory.runtime_worker import StageEvidence,WorkItem
from ai_product_factory.supabase_runtime_queue import SupabaseRuntimeQueue

class Response:
 def __init__(self,data):self.data=data
 def __enter__(self):return self
 def __exit__(self,*a):return False
 def read(self):return json.dumps(self.data).encode() if self.data is not None else b""

def test_claim_maps_rpc_payload_without_leaking_key():
 payload={"run_id":"r","task_id":"t","project_id":"p","project_key":"demo","stages":["discovery"],"context":{"x":1}}
 with patch("urllib.request.urlopen",return_value=Response(payload)) as call:
  q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret");item=q.claim_next("w")
 assert item.project_key=="demo";assert item.stages==("discovery",)
 req=call.call_args.args[0];assert req.full_url.endswith("/rest/v1/rpc/factory_claim_next_run");assert b"secret" not in req.data

def test_terminal_and_stage_rpcs():
 q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret");item=WorkItem("r","t","p","demo",(),{})
 with patch("urllib.request.urlopen",return_value=Response(None)) as call:
  q.record_stage(item,StageEvidence("discovery","completed",{"ok":True}));q.complete(item);q.fail(item,"x")
 assert call.call_count==4
