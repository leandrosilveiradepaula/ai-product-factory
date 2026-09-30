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
  packet=getattr(item,"context_packet",None)
  if getattr(item,"change_set_id",None) and not isinstance(packet,dict):
   raise RuntimeError("Change Set implementation requires a durable context packet")
  context=packet if isinstance(packet,dict) else {"project_key":item.project_key,"repository":item.repository,"title":item.title,"description":item.description,"impact":getattr(item,"impact_context",None)}
  schema={
   "type":"object",
   "properties":{
    "plan_markdown":{"type":"string"},
    "files":{
     "type":"array",
     "items":{
      "type":"object",
      "properties":{"path":{"type":"string"},"content":{"type":"string"}},
      "required":["path","content"],
      "additionalProperties":False,
     },
    },
    "commit_message":{"type":"string"},
    "pr_title":{"type":"string"},
    "pr_body":{"type":"string"},
   },
   "required":["plan_markdown","files","commit_message","pr_title","pr_body"],
   "additionalProperties":False,
  }
  request=ModelRequest(task_id=item.task_id,objective=objective,context=json.dumps(context,ensure_ascii=False),run_id=item.run_id,constraints=("Do not include secrets or .env files.","Do not use absolute paths or .. paths.","Return complete file contents, not diffs.","Write only inside repository.write_scopes from the context packet.","Keep the change narrowly scoped to the task.","Treat repository.reference_files as authoritative repository evidence. Do not invent repository paths, architecture, tables, workflows, or APIs that conflict with those files.","If required repository evidence is absent, fail conservatively rather than fabricating it."),output_schema=schema)
  result=self.executor.execute(ExecutionRoute.DIRECT,request)
  try:data=json.loads(result.output)
  except json.JSONDecodeError as exc:raise ValueError("implementation producer returned invalid JSON") from exc
  if not isinstance(data,dict):raise ValueError("implementation output must be a JSON object")
  raw_files=data.get("files")
  if not isinstance(raw_files,list) or not raw_files:raise ValueError("implementation output requires non-empty files")
  files={}
  for entry in raw_files:
   if not isinstance(entry,dict):raise ValueError("implementation files must be structured entries")
   path=entry.get("path");content=entry.get("content")
   if not isinstance(path,str) or not path.strip() or not isinstance(content,str):
    raise ValueError("implementation files require path and content")
   if path in files:raise ValueError("implementation output contains duplicate file path")
   files[path]=content
  required=("plan_markdown","commit_message","pr_title","pr_body")
  if any(not isinstance(data.get(k),str) or not data[k].strip() for k in required):raise ValueError("implementation output is missing required text fields")
  return ImplementationArtifact(data["plan_markdown"],files,data["commit_message"],data["pr_title"],data["pr_body"])
