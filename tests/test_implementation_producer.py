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
  data={"plan_markdown":"# Plan","files":[{"path":"app.py","content":"print('ok')\n"}],"commit_message":"feat: x","pr_title":"Feature","pr_body":"Implemented","blocked_reason":""}
  p=Provider(json.dumps(data));a=ModelImplementationProducer(ModelExecutor(primary=p)).produce(item())
  self.assertEqual(a.files["app.py"],"print('ok')\n");self.assertEqual(p.calls,1)
 def test_invalid_json_fails_closed(self):
  with self.assertRaises(ValueError):ModelImplementationProducer(ModelExecutor(primary=Provider("bad"))).produce(item())
 def test_empty_files_fail_closed(self):
  data={"plan_markdown":"x","files":[],"commit_message":"x","pr_title":"x","pr_body":"x","blocked_reason":""}
  with self.assertRaises(ValueError):ModelImplementationProducer(ModelExecutor(primary=Provider(json.dumps(data)))).produce(item())
 def test_codex_is_not_used(self):
  class Codex:
   def execute(self,request):raise AssertionError("Codex must not be called")
  data={"plan_markdown":"x","files":[{"path":"a","content":"b"}],"commit_message":"x","pr_title":"x","pr_body":"x","blocked_reason":""}
  ModelImplementationProducer(ModelExecutor(primary=Provider(json.dumps(data)),codex=Codex())).produce(item())

 def test_duplicate_structured_paths_fail_closed(self):
  data={"plan_markdown":"x","files":[{"path":"a","content":"one"},{"path":"a","content":"two"}],"commit_message":"x","pr_title":"x","pr_body":"x","blocked_reason":""}
  with self.assertRaises(ValueError):ModelImplementationProducer(ModelExecutor(primary=Provider(json.dumps(data)))).produce(item())
 def test_request_requires_strict_structured_schema(self):
  class CapturingProvider:
   def __init__(self):self.request=None
   def execute(self,request):
    self.request=request
    data={"plan_markdown":"x","files":[{"path":"a","content":"b"}],"commit_message":"x","pr_title":"x","pr_body":"x","blocked_reason":""}
    return ModelResult(ModelRole.PRIMARY,json.dumps(data),provider_ref="x")
  p=CapturingProvider();ModelImplementationProducer(ModelExecutor(primary=p)).produce(item())
  schema=p.request.output_schema
  self.assertEqual(schema["type"],"object")
  self.assertFalse(schema["additionalProperties"])
  self.assertEqual(schema["properties"]["files"]["type"],"array")
  self.assertFalse(schema["properties"]["files"]["items"]["additionalProperties"])
 def test_explicit_repository_blocker_is_valid_output(self):
  data={"plan_markdown":"blocked by governance","files":[],"commit_message":"chore: blocked","pr_title":"Blocked","pr_body":"No changes","blocked_reason":"CURRENT_TASK does not authorize this remediation"}
  artifact=ModelImplementationProducer(ModelExecutor(primary=Provider(json.dumps(data)))).produce(item())
  self.assertEqual(artifact.files,{})
  self.assertIn("CURRENT_TASK",artifact.blocked_reason)

 def test_blocked_output_does_not_require_unused_commit_or_pr_text(self):
  data={"plan_markdown":"blocked by governance","files":[],"commit_message":"","pr_title":"","pr_body":"","blocked_reason":"Applicable governance still blocks this task"}
  artifact=ModelImplementationProducer(ModelExecutor(primary=Provider(json.dumps(data)))).produce(item())
  self.assertEqual(artifact.files,{})
  self.assertEqual(artifact.commit_message,"")
  self.assertIn("blocks",artifact.blocked_reason)

 def test_prompt_reconciles_newer_durable_human_decisions_without_widening_safety(self):
  class CapturingProvider:
   def __init__(self):self.request=None
   def execute(self,request):
    self.request=request
    return ModelResult(ModelRole.PRIMARY,json.dumps({"plan_markdown":"blocked","files":[],"commit_message":"","pr_title":"","pr_body":"","blocked_reason":"still blocked"}),provider_ref="x")
  p=CapturingProvider();ModelImplementationProducer(ModelExecutor(primary=p)).produce(item())
  self.assertIn("durable human_decisions",p.request.objective)
  self.assertIn("never broadens repository.write_scopes",p.request.objective)
  self.assertIn("AGENTS.md remains authoritative",p.request.objective)

class BoundedAnchorTests(unittest.TestCase):
 def setUp(self):
  from dataclasses import replace
  self.item=replace(item(),change_set_id="cs",context_packet={
   "repository":{"write_scopes":["app/server.js","app/new.js"]},
   "repository_snapshot":{"app/server.js":"first\nunique old\nlast\n"}})
 def artifact(self,files,**flags):
  data={"plan_markdown":"plan","files":files,"commit_message":"fix: x",
        "pr_title":"fix","pr_body":"details","blocked_reason":"","decision_needed":None}
  class P:
   def execute(self,request):
    assert "edits" in request.output_schema["properties"]["files"]["items"]["properties"]
    return ModelResult(ModelRole.PRIMARY,json.dumps(data),**flags)
  return ModelImplementationProducer(ModelExecutor(primary=P())).produce(self.item)
 def test_exact_anchor_materializes_complete_file_and_new_file(self):
  result=self.artifact([{"path":"app/server.js","content":"","edits":[{"anchor":"unique old","replacement":"new"}]},
                        {"path":"app/new.js","content":"new file","edits":[]}])
  self.assertEqual(result.files["app/server.js"],"first\nnew\nlast\n")
  self.assertEqual(result.files["app/new.js"],"new file")
 def test_ambiguous_or_overlapping_or_out_of_scope_or_truncated_rejected(self):
  for files,flags in (
    ([{"path":"app/server.js","content":"","edits":[{"anchor":"missing","replacement":"x"}]}],{}),
    ([{"path":"app/server.js","content":"","edits":[{"anchor":"unique old","replacement":"x"},
       {"anchor":"old","replacement":"y"}]}],{}),
    ([{"path":"app/other.js","content":"x","edits":[]}],{}),
    ([{"path":"app/server.js","content":"x","edits":[]}],{"output_truncated":True}),
    ([{"path":"app/server.js","content":"x","edits":[]}],{"output_limit_reached":True}),
  ):
   with self.subTest(files=files,flags=flags),self.assertRaises((ValueError,PermissionError)):
    self.artifact(files,**flags)

if __name__=="__main__":unittest.main()
