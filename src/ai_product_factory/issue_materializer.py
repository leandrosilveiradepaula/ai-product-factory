from __future__ import annotations
from dataclasses import replace
from typing import Protocol
from .execution_worker import DirectExecutionItem
from .github_rest import GitHubIssue,GitHubRestAdapter

class IssueBindingStore(Protocol):
 def bind_issue(self,*,run_id:str,issue:GitHubIssue)->None:...

class GitHubIssueMaterializer:
 def __init__(self,*,github:GitHubRestAdapter,binding:IssueBindingStore)->None:self.github=github;self.binding=binding
 def ensure_issue(self,item:DirectExecutionItem)->DirectExecutionItem:
  if item.issue_number is not None:return item
  body=f"Factory task: {item.task_id}\n\nProject: {item.project_key}\n\n{item.description}\n\nCreated automatically by AI Product Factory."
  issue=self.github.create_issue(title=item.title,body=body)
  self.binding.bind_issue(run_id=item.run_id,issue=issue)
  return replace(item,issue_number=issue.number)
