from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .autonomous_github import AutonomousGitHubLoop,GitHubWorkSession

@dataclass(frozen=True)
class DirectExecutionItem:
 run_id:str;task_id:str;project_key:str;repository:str;issue_number:int|None;title:str;description:str;branch:str;human_gate_required:bool=False
 change_set_id:str|None=None;work_unit_id:str|None=None;wave:int|None=None;impact_context:dict|None=None;base_commit:str|None=None
 context_packet:dict|None=None;write_scopes:tuple[str,...]=()

@dataclass(frozen=True)
class ImplementationArtifact:
 plan_markdown:str;files:dict[str,str];commit_message:str;pr_title:str;pr_body:str;blocked_reason:str|None=None;decision_needed:dict|None=None

class ImplementationBlocked(RuntimeError):
 pass

class ImplementationProducer(Protocol):
 def produce(self,item:DirectExecutionItem)->ImplementationArtifact:...

class IssueMaterializer(Protocol):
 def ensure_issue(self,item:DirectExecutionItem)->DirectExecutionItem:...

class DirectExecutionWorker:
 """Runs one already-authorized Direct task through the GitHub delivery loop."""
 def __init__(self,*,loop:AutonomousGitHubLoop,producer:ImplementationProducer,issue_materializer:IssueMaterializer|None=None)->None:self.loop=loop;self.producer=producer;self.issue_materializer=issue_materializer
 def execute(self,item:DirectExecutionItem)->GitHubWorkSession:
  if item.human_gate_required:raise PermissionError("task requires human approval before implementation")
  # Never spend on generation when the missing issue cannot be materialized.
  # But do not publish an issue until the artifact has passed its independent
  # blocked/decision checks. An unexecutable producer response is not a Start.
  if item.issue_number is None and self.issue_materializer is None:
   raise RuntimeError("GitHub issue is required before Direct execution")
  artifact=self.producer.produce(item)
  # The delivery boundary must not trust a producer implementation to enforce
  # its own blocked/decision contract. A blocked artifact never reaches GitHub
  # branch, commit, or PR actions, even if it also contains files.
  if not isinstance(artifact,ImplementationArtifact):
   raise ValueError("implementation producer returned invalid artifact")
  if artifact.blocked_reason is not None:
   raise ImplementationBlocked("implementation producer reported blocked work")
  if artifact.decision_needed is not None:
   raise ImplementationBlocked("implementation producer requires a human decision")
  if not isinstance(artifact.files,dict) or not artifact.files:
   raise ValueError("implementation producer returned no files")
  if any(not isinstance(path,str) or not path.strip()
         or not isinstance(content,str) for path,content in artifact.files.items()):
   raise ValueError("implementation producer returned malformed files")
  if item.issue_number is None:
   item=self.issue_materializer.ensure_issue(item)
   if not isinstance(item,DirectExecutionItem) or not isinstance(item.issue_number,int) or isinstance(item.issue_number,bool) or item.issue_number < 1:
    raise ValueError("issue materializer did not return a valid bound issue")
  session=self.loop.start_issue(issue_number=item.issue_number,branch=item.branch,run_id=item.run_id,plan_markdown=artifact.plan_markdown)
  self.loop.commit_implementation(session,files=artifact.files,message=artifact.commit_message)
  return self.loop.open_pull_request(session,title=artifact.pr_title,body=artifact.pr_body)
