import unittest
from ai_product_factory.autonomous_github import AutonomousGitHubLoop
from ai_product_factory.github_rest import GitHubIssue,GitHubPullRequest
from ai_product_factory.browser_evidence import BrowserEvidence
from ai_product_factory.deployment import DeploymentResult
from ai_product_factory.preview_flow import VerifiedPreviewResult
from ai_product_factory.release_policy import ReleaseEnvironment
class Store:
 def __init__(self):self.status=[];self.tools=[]
 def update_run_status(self,run_id,status,*,candidate_commit=None):self.status.append((run_id,status,candidate_commit))
 def record_tool_usage(self,**kw):self.tools.append(kw)
class GitHub:
 def get_issue(self,n):return GitHubIssue(n,"T","B",f"https://i/{n}")
 def create_branch(self,b,base_branch="main"):return "base"
 def commit_files(self,b,files,message):return "plan" if ".factory/plans/issue-7.md" in files else "impl"
 def create_pull_request(self,**kw):return GitHubPullRequest(9,"impl","https://p/9")
 def get_ci_state(self,n):
  from ai_product_factory.github_loop import CIState
  return CIState.SUCCESS
 def merge_pull_request(self,n):return "merge"
 def close_issue(self,n):pass
class Tests(unittest.TestCase):
 def test_delivery_store_contract_runs_full_green_path(self):
  s=Store();g=GitHub();loop=AutonomousGitHubLoop(g,s)
  session=loop.start_issue(issue_number=7,branch="factory/t",run_id="r",plan_markdown="# P")
  loop.commit_implementation(session,files={"a.py":"x\n"},message="feat: x")
  session=loop.open_pull_request(session,title="T",body="B")
  d=loop.evaluate(session,human_gate_required=False)
  self.assertEqual(d.action.value,"preview_ready");self.assertEqual(s.status[-1],("r","preview_ready",None));self.assertEqual([x["operation"] for x in s.tools],["issue_branch_plan","commit_implementation","create_pr","evaluate_ci"])
  preview=VerifiedPreviewResult(DeploymentResult("vercel",ReleaseEnvironment.PREVIEW,"success","dep","https://preview.example"),BrowserEvidence("success","https://preview.example",("page_load",)))
  loop.finalize_verified_preview(session,preview)
  self.assertEqual(s.status[-1],("r","merged","merge"));self.assertEqual([x["operation"] for x in s.tools][-2:],["merge_after_verified_preview","close_issue"])
if __name__=="__main__":unittest.main()
