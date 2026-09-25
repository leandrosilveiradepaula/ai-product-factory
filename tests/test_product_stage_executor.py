import json
from ai_product_factory.model_executor import ModelExecutor,ModelResult,ModelRole
from ai_product_factory.product_stage_executor import ProductStageExecutor
from ai_product_factory.runtime_worker import WorkItem

class Provider:
 def __init__(self):self.requests=[]
 def execute(self,request):
  self.requests.append(request);stage=["discovery","specification","planning"][len(self.requests)-1]
  return ModelResult(ModelRole.PRIMARY,json.dumps({"stage":stage,"assumptions":[]}),provider_ref=f"ref-{stage}",usage={"input_tokens":10})

def item():return WorkItem("r","t","p","demo",("discovery","specification","planning"),{"summary":"build x"})

def test_product_stages_use_primary_and_chain_prior_evidence():
 p=Provider();h=ProductStageExecutor(ModelExecutor(primary=p));i=item()
 d=h.execute(i,"discovery");s=h.execute(i,"specification");h.execute(i,"planning")
 assert d["_evidence"]["provider_ref"]=="ref-discovery";assert s["stage"]=="specification";assert len(p.requests)==3
 assert '"discovery"' in p.requests[1].context

def test_invalid_json_fails_closed():
 class Bad:
  def execute(self,request):return ModelResult(ModelRole.PRIMARY,"not-json")
 h=ProductStageExecutor(ModelExecutor(primary=Bad()))
 try:h.execute(item(),"discovery")
 except ValueError as exc:assert "invalid JSON" in str(exc)
 else:raise AssertionError("expected ValueError")

def test_codex_is_not_used_for_bootstrap():
 primary=Provider()
 class Codex:
  def execute(self,request):raise AssertionError("Codex must not be called")
 h=ProductStageExecutor(ModelExecutor(primary=primary,codex=Codex()));h.execute(item(),"discovery");assert len(primary.requests)==1
