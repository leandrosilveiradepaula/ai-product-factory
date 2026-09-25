import unittest
from ai_product_factory.execution_worker import DirectExecutionItem,DirectExecutionWorker,ImplementationArtifact

class Loop:
 def __init__(self):self.calls=[]
 def start_issue(self,**kw):self.calls.append(("start",kw));return "session"
 def commit_implementation(self,session,**kw):self.calls.append(("commit",kw));return "sha"
 def open_pull_request(self,session,**kw):self.calls.append(("pr",kw));return "with-pr"
class Producer:
 def __init__(self,files=None):self.files={"app.py":"print('ok')\n"} if files is None else files
 def produce(self,item):return ImplementationArtifact("# Plan",self.files,"feat: task",item.title,f"Automated implementation for {item.task_id}")
def item(gate=False):return DirectExecutionItem("r","t","p","owner/repo",7,"Feature","Do it","factory/t",gate)
class Tests(unittest.TestCase):
 def test_direct_task_reaches_pr_boundary(self):
  loop=Loop();result=DirectExecutionWorker(loop=loop,producer=Producer()).execute(item())
  self.assertEqual(result,"with-pr");self.assertEqual([x[0] for x in loop.calls],["start","commit","pr"])
 def test_gate_stops_before_producer_or_github(self):
  loop=Loop()
  with self.assertRaises(PermissionError):DirectExecutionWorker(loop=loop,producer=Producer()).execute(item(True))
  self.assertEqual(loop.calls,[])
 def test_empty_patch_fails_before_github_mutation(self):
  loop=Loop()
  with self.assertRaises(ValueError):DirectExecutionWorker(loop=loop,producer=Producer({})).execute(item())
  self.assertEqual(loop.calls,[])
if __name__=="__main__":unittest.main()
