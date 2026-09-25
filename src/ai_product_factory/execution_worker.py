from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .autonomous_github import AutonomousGitHubLoop,GitHubWorkSession

@dataclass(frozen=True)
class DirectExecutionItem:
 run_id:str;task_id:str;project_key:str;repository:str;issue_number:int|None;title:str;description:str;branch:str;human_gate_required:bool=False

@dataclass(frozen=True)
class ImplementationArtifact:
 plan_markdown:str;files:dict[str,str];commit_message:str;pr_title:str;pr_body:str

class ImplementationProducer(Protocol):
 def produce(self,item:DirectExecutionItem)->ImplementationArtifact:...

class IssueMaterializer(Protocol):
 def ensure_issue(self,item:DirectExecutionItem)->DirectExecutionItem:...

class DirectExecutionWorker:
 """Runs one already-authorized Direct task through the GitHub delivery loop."""
 def __init__(self,*,loop:AutonomousGitHubLoop,producer:ImplementationProducer,issue_materializer:IssueMaterializer|None=None)->None:self.loop=loop;self.producer=producer;self.issue_materializer=issue_materializer
 def execute(self,item:DirectExecutionItem)->GitHubWorkSession:
  if item.human_gate_required:raise PermissionError("task requires human approval before implementation")
  if item.issue_number is None:
   if self.issue_materializer is None:raise RuntimeError("GitHub issue is required before Direct execution")
   item=self.issue_materializer.ensure_issue(item)
  artifact=self.producer.produce(item)
  if not artifact.files:raise ValueError("implementation producer returned no files")
  session=self.loop.start_issue(issue_number=item.issue_number,branch=item.branch,run_id=item.run_id,plan_markdown=artifact.plan_markdown)
  self.loop.commit_implementation(session,files=artifact.files,message=artifact.commit_message)
  return self.loop.open_pull_request(session,title=artifact.pr_title,body=artifact.pr_body)
