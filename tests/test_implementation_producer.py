import json,unittest
from ai_product_factory.execution_worker import DirectExecutionItem
from ai_product_factory.model_executor import ModelExecutor,ModelResult,ModelRole
from ai_product_factory.implementation_producer import ModelImplementationProducer
class Provider:
 def __init__(self,output):self.output=output;self.calls=0
 def execute(self,request):self.calls+=1;return ModelResult(ModelRole.PRIMARY,self.output,provider_ref="x")
def item():return DirectExecutionItem("r","t","p","owner/repo",7,"Feature","Do it","factory/t",False)
class Tests(unittest.TestCase):
 def test_structured_patch_uses_primary(self):
  data={"plan_markdown":"# Plan","files":[{"path":"app.py","content":"print('ok')\n"}],"commit_message":"feat: x","pr_title":"Feature","pr_body":"Implemented"}
  p=Provider(json.dumps(data));a=ModelImplementationProducer(ModelExecutor(primary=p)).produce(item())
  self.assertEqual(a.files["app.py"],"print('ok')\n");self.assertEqual(p.calls,1)
 def test_invalid_json_fails_closed(self):
  with self.assertRaises(ValueError):ModelImplementationProducer(ModelExecutor(primary=Provider("bad"))).produce(item())
 def test_empty_files_fail_closed(self):
  data={"plan_markdown":"x","files":[],"commit_message":"x","pr_title":"x","pr_body":"x"}
  with self.assertRaises(ValueError):ModelImplementationProducer(ModelExecutor(primary=Provider(json.dumps(data)))).produce(item())
 def test_codex_is_not_used(self):
  class Codex:
   def execute(self,request):raise AssertionError("Codex must not be called")
  data={"plan_markdown":"x","files":[{"path":"a","content":"b"}],"commit_message":"x","pr_title":"x","pr_body":"x"}
  ModelImplementationProducer(ModelExecutor(primary=Provider(json.dumps(data)),codex=Codex())).produce(item())

 def test_duplicate_structured_paths_fail_closed(self):
  data={"plan_markdown":"x","files":[{"path":"a","content":"one"},{"path":"a","content":"two"}],"commit_message":"x","pr_title":"x","pr_body":"x"}
  with self.assertRaises(ValueError):ModelImplementationProducer(ModelExecutor(primary=Provider(json.dumps(data)))).produce(item())
 def test_request_requires_strict_structured_schema(self):
  class CapturingProvider:
   def __init__(self):self.request=None
   def execute(self,request):
    self.request=request
    data={"plan_markdown":"x","files":[{"path":"a","content":"b"}],"commit_message":"x","pr_title":"x","pr_body":"x"}
    return ModelResult(ModelRole.PRIMARY,json.dumps(data),provider_ref="x")
  p=CapturingProvider();ModelImplementationProducer(ModelExecutor(primary=p)).produce(item())
  schema=p.request.output_schema
  self.assertEqual(schema["type"],"object")
  self.assertFalse(schema["additionalProperties"])
  self.assertEqual(schema["properties"]["files"]["type"],"array")
  self.assertFalse(schema["properties"]["files"]["items"]["additionalProperties"])
if __name__=="__main__":unittest.main()
