import unittest
from ai_product_factory.browser_evidence import BrowserEvidence
from ai_product_factory.browser_evidence_store import BrowserEvidenceRecorder
from ai_product_factory.deployment import DeploymentRequest,DeploymentResult
from ai_product_factory.evidence import EvidenceBundle
from ai_product_factory.preview_flow import PreviewDeferred,VerifiedPreviewCoordinator
from ai_product_factory.release_policy import ReleaseEnvironment

class Deploy:
 name="fake"
 def __init__(self,url="https://preview.example",status="success"):self.url=url;self.status=status
 def deploy(self,request):return DeploymentResult(self.name,request.environment,self.status,"dep-1",self.url)
class Browser:
 name="browser"
 def __init__(self,status="success",url="https://preview.example"):self.status=status;self.url=url
 def verify(self,url):return BrowserEvidence(self.status,self.url,("page_load","console_clean"))
class Store:
 def __init__(self):self.evals=[];self.audit=[]
 def record_evaluation(self,**kw):self.evals.append(kw)
 def record_audit_event(self,**kw):self.audit.append(kw)
def request(env=ReleaseEnvironment.PREVIEW):
 e=EvidenceBundle("abc","abc","success",metadata={"quality_gate_passed":True})
 return DeploymentRequest("p",env,"abc",e)
class Tests(unittest.TestCase):
 def test_verified_preview(self):
  s=Store();r=VerifiedPreviewCoordinator().execute(run_id="r1",request=request(),deployment_adapter=Deploy(),browser_adapter=Browser(),evidence_recorder=BrowserEvidenceRecorder(s))
  self.assertEqual(r.deployment.deployment_ref,"dep-1");self.assertEqual(s.evals[0]["status"],"success")
 def test_quota_block_is_deferred_before_browser(self):
  s=Store();browser=Browser()
  with self.assertRaises(PreviewDeferred) as ctx:
   VerifiedPreviewCoordinator().execute(run_id="r1",request=request(),deployment_adapter=Deploy(status="blocked_quota",url=None),browser_adapter=browser,evidence_recorder=BrowserEvidenceRecorder(s))
  self.assertEqual(ctx.exception.deployment.status,"blocked_quota")
  self.assertEqual(s.evals,[])

 def test_refuses_prod(self):
  with self.assertRaises(PermissionError):VerifiedPreviewCoordinator().execute(run_id="r1",request=request(ReleaseEnvironment.PROD),deployment_adapter=Deploy(),browser_adapter=Browser(),evidence_recorder=BrowserEvidenceRecorder(Store()))
 def test_failed_browser_is_persisted_and_rejected(self):
  s=Store()
  with self.assertRaises(ValueError):VerifiedPreviewCoordinator().execute(run_id="r1",request=request(),deployment_adapter=Deploy(),browser_adapter=Browser("failure"),evidence_recorder=BrowserEvidenceRecorder(s))
  self.assertEqual(s.evals[0]["status"],"failure")
 def test_mismatched_url_is_rejected(self):
  with self.assertRaises(ValueError):VerifiedPreviewCoordinator().execute(run_id="r1",request=request(),deployment_adapter=Deploy(),browser_adapter=Browser(url="https://other.example"),evidence_recorder=BrowserEvidenceRecorder(Store()))
if __name__=="__main__":unittest.main()
