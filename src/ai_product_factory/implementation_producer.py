from __future__ import annotations
import json
from .execution_worker import DirectExecutionItem,ImplementationArtifact
from .model_executor import ModelExecutor,ModelRequest
from .models import ExecutionRoute

class ModelImplementationProducer:
 """Produces a bounded structured patch through the primary model route only."""
 def __init__(self,executor:ModelExecutor)->None:self.executor=executor
 def produce(self,item:DirectExecutionItem)->ImplementationArtifact:
  objective=("Implement the task as a minimal repository patch. Return JSON only with "
             "plan_markdown, files (object path->full text), commit_message, pr_title, pr_body.")
  request=ModelRequest(task_id=item.task_id,objective=objective,context=json.dumps({"project_key":item.project_key,"repository":item.repository,"title":item.title,"description":item.description},ensure_ascii=False),constraints=("Do not include secrets or .env files.","Do not use absolute paths or .. paths.","Return complete file contents, not diffs.","Keep the change narrowly scoped to the task."))
  result=self.executor.execute(ExecutionRoute.DIRECT,request)
  try:data=json.loads(result.output)
  except json.JSONDecodeError as exc:raise ValueError("implementation producer returned invalid JSON") from exc
  if not isinstance(data,dict):raise ValueError("implementation output must be a JSON object")
  files=data.get("files")
  if not isinstance(files,dict) or not files:raise ValueError("implementation output requires non-empty files")
  if not all(isinstance(k,str) and isinstance(v,str) for k,v in files.items()):raise ValueError("implementation files must map paths to text")
  required=("plan_markdown","commit_message","pr_title","pr_body")
  if any(not isinstance(data.get(k),str) or not data[k].strip() for k in required):raise ValueError("implementation output is missing required text fields")
  return ImplementationArtifact(data["plan_markdown"],files,data["commit_message"],data["pr_title"],data["pr_body"])
