import unittest
from ai_product_factory.independent_regression_evidence import REPOSITORY, RegressionEvidenceBlocked, verify_regression_gates

SHA="a"*40; ROOT="/repos/"+REPOSITORY
def environment(): return {"GITHUB_ACTIONS":"true","GITHUB_REPOSITORY":REPOSITORY,"GITHUB_EVENT_NAME":"workflow_run","GITHUB_REF":"refs/heads/main","GITHUB_WORKFLOW_REF":REPOSITORY+"/.github/workflows/autonomous-runner.yml@refs/heads/main","GITHUB_RUN_ID":"7"}
def fixture():
 rules=[{"type":"deletion","parameters":{}},{"type":"non_fast_forward","parameters":{}},{"type":"pull_request","parameters":{"required_approving_review_count":1}},{"type":"required_status_checks","parameters":{"strict_required_status_checks_policy":True,"required_status_checks":[{"context":"test"},{"context":"factory-acceptance"},{"context":"PostgreSQL QA"}]}}]
 return {ROOT+"/git/ref/heads/main":{"object":{"sha":SHA}},ROOT+"/actions/runs/7":{"id":7,"name":"Factory autonomous runner","path":".github/workflows/autonomous-runner.yml","event":"workflow_run","head_sha":SHA,"head_branch":"main","status":"completed","conclusion":"success","run_attempt":1},ROOT+"/rulesets?includes_parents=true":[{"id":8}],ROOT+"/rulesets/8":{"id":8,"enforcement":"active","rules":rules}}
class RegressionEvidenceTests(unittest.TestCase):
 def proof(self, values): return verify_regression_gates(repository=REPOSITORY,assessed_commit=SHA,github_get=lambda path:values[path],environment=environment())
 def test_full_effective_gates_pass(self): self.assertEqual(self.proof(fixture()).criterion,"regression_gates")
 def test_missing_postgres_or_approval_blocks(self):
  for mutation in ("postgres","approval","job"):
   values=fixture();rules=values[ROOT+"/rulesets/8"]["rules"]
   if mutation=="postgres": rules[-1]["parameters"]["required_status_checks"].pop()
   elif mutation=="approval": rules[2]["parameters"]["required_approving_review_count"]=0
   else: values[ROOT+"/actions/runs/7"]["name"]="wrong"
   with self.subTest(mutation=mutation),self.assertRaises(RegressionEvidenceBlocked): self.proof(values)
