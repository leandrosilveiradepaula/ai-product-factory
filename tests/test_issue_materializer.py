import unittest
from dataclasses import replace
from ai_product_factory.execution_worker import DirectExecutionItem,DirectExecutionWorker,ImplementationArtifact
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
if __name__=="__main__":unittest.main()
