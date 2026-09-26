import unittest
from ai_product_factory.deployment import DeploymentRequest,DeploymentResult
from ai_product_factory.evidence import EvidenceBundle
from ai_product_factory.release_policy import ReleaseEnvironment
from ai_product_factory.supabase_deployment import DurablePreviewAdapter

class Store:
 def __init__(self):self.rows=[]
 def record(self,**kwargs):self.rows.append(kwargs)
class Provider:
 name="preview-provider"
 def deploy(self,request):return DeploymentResult(self.name,request.environment,"success","dep-1","https://preview.invalid")

class Tests(unittest.TestCase):
 def test_preview_records_real_result(self):
  store=Store();adapter=DurablePreviewAdapter(Provider(),store,run_id="run-1")
  evidence=EvidenceBundle("a","b","success",metadata={"quality_gate_passed":True})
  result=adapter.deploy(DeploymentRequest("p",ReleaseEnvironment.PREVIEW,"b",evidence))
  self.assertEqual(result.deployment_ref,"dep-1");self.assertEqual(store.rows[0]["run_id"],"run-1")
 def test_non_preview_fails_closed(self):
  adapter=DurablePreviewAdapter(Provider(),Store(),run_id="run-1")
  evidence=EvidenceBundle("a","b","success",metadata={"quality_gate_passed":True})
  with self.assertRaises(PermissionError):adapter.deploy(DeploymentRequest("p",ReleaseEnvironment.PROD,"b",evidence))
if __name__=="__main__":unittest.main()
