import unittest
from dataclasses import replace
from ai_product_factory.execution_worker import DirectExecutionItem,DirectExecutionWorker,ImplementationArtifact,ImplementationBlocked
from ai_product_factory.github_rest import GitHubIssue
from ai_product_factory.issue_materializer import GitHubIssueMaterializer

class GitHub:
 def __init__(self):self.calls=[]
 def create_issue(self,*,title,body):self.calls.append((title,body));return GitHubIssue(42,title,body,"https://example/issues/42")
class Binding:
 def __init__(self):self.calls=[]
 def bind_issue(self,*,run_id,issue):self.calls.append((run_id,issue.number))
class Loop:
 def __init__(self):self.calls=[]
 def start_issue(self,**kw):self.calls.append(("start",kw));return "session"
 def commit_implementation(self,session,**kw):self.calls.append(("commit",kw));return "sha"
 def open_pull_request(self,session,**kw):self.calls.append(("pr",kw));return "with-pr"
class Producer:
 def produce(self,item):return ImplementationArtifact("# Plan",{"a.py":"x\n"},"feat: x",item.title,"body")
def item(issue=None,gate=False):return DirectExecutionItem("r","t","p","owner/repo",issue,"Feature","Do it","factory/t",gate)

class Tests(unittest.TestCase):
 def test_materializes_and_binds(self):
  gh=GitHub();binding=Binding();out=GitHubIssueMaterializer(github=gh,binding=binding).ensure_issue(item())
  self.assertEqual(out.issue_number,42);self.assertEqual(binding.calls,[("r",42)])
 def test_worker_materializes_before_loop(self):
  gh=GitHub();binding=Binding();loop=Loop();mat=GitHubIssueMaterializer(github=gh,binding=binding)
  DirectExecutionWorker(loop=loop,producer=Producer(),issue_materializer=mat).execute(item())
  self.assertEqual(loop.calls[0][1]["issue_number"],42)
 def test_gate_stops_before_issue_creation(self):
  gh=GitHub();binding=Binding();loop=Loop();mat=GitHubIssueMaterializer(github=gh,binding=binding)
  with self.assertRaises(PermissionError):DirectExecutionWorker(loop=loop,producer=Producer(),issue_materializer=mat).execute(item(gate=True))
  self.assertEqual(gh.calls,[])
 def test_missing_materializer_fails_closed(self):
  with self.assertRaises(RuntimeError):DirectExecutionWorker(loop=Loop(),producer=Producer()).execute(item())
class ArtifactProducer:
 def __init__(self,artifact):self.artifact=artifact;self.calls=0
 def produce(self,item):self.calls+=1;return self.artifact

class DirectIssuePublicationBoundary(unittest.TestCase):
 def setup(self,artifact):
  github=GitHub();binding=Binding();loop=Loop()
  producer=ArtifactProducer(artifact)
  worker=DirectExecutionWorker(
   loop=loop,producer=producer,
   issue_materializer=GitHubIssueMaterializer(github=github,binding=binding),
  )
  return worker,github,binding,loop,producer

 def test_blocked_or_pending_decision_cannot_create_issue(self):
  for blocked,decision in (("blocked",None),("",None),(None,{"decision_kind":"material_requirement_change"})):
   with self.subTest(blocked=blocked,decision=decision):
    artifact=ImplementationArtifact("# Plan",{"app.py":"code"},"feat","PR","body",blocked,decision)
    worker,github,binding,loop,producer=self.setup(artifact)
    with self.assertRaises(ImplementationBlocked):worker.execute(item())
    self.assertEqual(producer.calls,1)
    self.assertEqual(github.calls,[])
    self.assertEqual(binding.calls,[])
    self.assertEqual(loop.calls,[])

 def test_empty_or_malformed_artifact_cannot_create_issue(self):
  for artifact in (
   ImplementationArtifact("# Plan",{},"feat","PR","body"),
   ImplementationArtifact("# Plan",{"app.py":None},"feat","PR","body"),
   None,
  ):
   with self.subTest(artifact=repr(artifact)):
    worker,github,binding,loop,producer=self.setup(artifact)
    with self.assertRaises(ValueError):worker.execute(item())
    self.assertEqual(github.calls,[])
    self.assertEqual(binding.calls,[])
    self.assertEqual(loop.calls,[])

 def test_actionable_artifact_materializes_and_binds_before_delivery(self):
  artifact=ImplementationArtifact("# Plan",{"app.py":"code"},"feat","PR","body")
  worker,github,binding,loop,producer=self.setup(artifact)
  self.assertEqual(worker.execute(item()),"with-pr")
  self.assertEqual(producer.calls,1)
  self.assertEqual(len(github.calls),1)
  self.assertEqual(binding.calls,[("r",42)])
  self.assertEqual([name for name,_ in loop.calls],["start","commit","pr"])
  self.assertEqual(loop.calls[0][1]["issue_number"],42)

 def test_missing_materializer_never_calls_producer(self):
  producer=ArtifactProducer(ImplementationArtifact("# Plan",{"app.py":"code"},"feat","PR","body"))
  with self.assertRaises(RuntimeError):
   DirectExecutionWorker(loop=Loop(),producer=producer).execute(item())
  self.assertEqual(producer.calls,0)

 class BadMaterializer:
  def ensure_issue(self,item):return item

 def test_unbound_issue_is_rejected_before_delivery(self):
  producer=ArtifactProducer(ImplementationArtifact("# Plan",{"app.py":"code"},"feat","PR","body"))
  loop=Loop()
  worker=DirectExecutionWorker(loop=loop,producer=producer,issue_materializer=self.BadMaterializer())
  with self.assertRaises(ValueError):worker.execute(item())
  self.assertEqual(loop.calls,[])

if __name__=="__main__":unittest.main()
