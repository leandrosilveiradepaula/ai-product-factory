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


def test_recovery_rpc_is_bounded_and_service_secret_not_in_body():
 q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
 with patch("urllib.request.urlopen",return_value=Response({"requeued":1,"failed":0})) as call:
  out=q.recover_expired(3)
 assert out=={"requeued":1,"failed":0}
 req=call.call_args.args[0];assert req.full_url.endswith("/rest/v1/rpc/factory_recover_expired_runs");assert b"secret" not in req.data


def test_planning_stage_persists_execution_team_plan():
 q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
 item=WorkItem("r","t","p","demo",(),{})
 output={"tasks":[],"_team_plan":{"version":1,"status":"ready","profiles_selected":0,"planned_worker_peak":0,"blockers":[]}}
 with patch("urllib.request.urlopen",return_value=Response(None)) as call:
  q.record_stage(item,StageEvidence("planning","completed",output))
 urls=[x.args[0].full_url for x in call.call_args_list]
 assert urls[-1].endswith("/rest/v1/rpc/factory_record_execution_team_plan")
 assert call.call_count==3
