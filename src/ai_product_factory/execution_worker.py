from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .autonomous_github import AutonomousGitHubLoop,GitHubWorkSession

@dataclass(frozen=True)
class DirectExecutionItem:
 run_id:str;task_id:str;project_key:str;repository:str;issue_number:int;title:str;description:str;branch:str;human_gate_required:bool=False

@dataclass(frozen=True)
class ImplementationArtifact:
 plan_markdown:str;files:dict[str,str];commit_message:str;pr_title:str;pr_body:str

class ImplementationProducer(Protocol):
 def produce(self,item:DirectExecutionItem)->ImplementationArtifact:...

class DirectExecutionWorker:
 """Runs one already-authorized Direct task through the GitHub delivery loop."""
 def __init__(self,*,loop:AutonomousGitHubLoop,producer:ImplementationProducer)->None:self.loop=loop;self.producer=producer
 def execute(self,item:DirectExecutionItem)->GitHubWorkSession:
  if item.human_gate_required:raise PermissionError("task requires human approval before implementation")
  artifact=self.producer.produce(item)
  if not artifact.files:raise ValueError("implementation producer returned no files")
  session=self.loop.start_issue(issue_number=item.issue_number,branch=item.branch,run_id=item.run_id,plan_markdown=artifact.plan_markdown)
  self.loop.commit_implementation(session,files=artifact.files,message=artifact.commit_message)
  return self.loop.open_pull_request(session,title=artifact.pr_title,body=artifact.pr_body)
