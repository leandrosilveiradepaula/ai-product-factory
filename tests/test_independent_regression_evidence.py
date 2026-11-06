import unittest
from ai_product_factory.independent_regression_evidence import REPOSITORY, POSTGRES_JOBS, RegressionEvidenceBlocked, verify_regression_gates

SHA="a"*40; ROOT="/repos/"+REPOSITORY
def environment(): return {"GITHUB_ACTIONS":"true","GITHUB_REPOSITORY":REPOSITORY,"GITHUB_EVENT_NAME":"workflow_run","GITHUB_REF":"refs/heads/main","GITHUB_WORKFLOW_REF":REPOSITORY+"/.github/workflows/autonomous-runner.yml@refs/heads/main","GITHUB_RUN_ID":"7"}
def event(): return {"workflow_run":{"id":6,"name":"validate","path":".github/workflows/validate.yml","event":"push","status":"completed","conclusion":"success","head_sha":SHA,"head_branch":"main","run_attempt":1,"repository":{"full_name":REPOSITORY}}}
def fixture():
 rules=[{"type":"deletion","parameters":{}},{"type":"non_fast_forward","parameters":{}},{"type":"pull_request","parameters":{"required_approving_review_count":0}},{"type":"required_status_checks","parameters":{"strict_required_status_checks_policy":True,"required_status_checks":[{"context":"test"},{"context":"factory-acceptance"}]}}]
 return {ROOT:{"default_branch":"main"},ROOT+"/git/ref/heads/main":{"object":{"sha":SHA}},ROOT+"/git/commits/"+SHA:{"tree":{"sha":"b"*40}},ROOT+"/actions/runs/7":{"id":7,"name":"Factory autonomous runner","path":".github/workflows/autonomous-runner.yml","event":"workflow_run","head_sha":SHA,"head_branch":"main","status":"in_progress","run_attempt":1},ROOT+"/rulesets?includes_parents=true":[{"id":8}],ROOT+"/rulesets/8":{"id":8,"enforcement":"active","conditions":{"ref_name":{"include":["~DEFAULT_BRANCH"]}},"bypass_actors":[],"current_user_can_bypass":"never","rules":rules},ROOT+"/actions/workflows/manual-project-control-postgres.yml/runs?event=pull_request&status=success&per_page=100":{"workflow_runs":[{"id":9,"name":"Manual project lifecycle PostgreSQL QA","event":"pull_request","status":"completed","conclusion":"success","head_sha":SHA}]},ROOT+"/actions/runs/9/jobs?per_page=100":{"jobs":[{"name":name,"run_id":9,"head_sha":SHA,"status":"completed","conclusion":"success"} for name in POSTGRES_JOBS]}}
class RegressionEvidenceTests(unittest.TestCase):
 def proof(self, values, payload=None): return verify_regression_gates(repository=REPOSITORY,assessed_commit=SHA,github_get=lambda path:values[path],environment=environment(),event_payload=event() if payload is None else payload)
 def test_full_effective_gates_pass(self): self.assertEqual(self.proof(fixture()).criterion,"regression_gates")
 def test_missing_postgres_or_scope_blocks(self):
  for mutation in ("postgres","scope","job"):
   values=fixture();rules=values[ROOT+"/rulesets/8"]["rules"]
   if mutation=="postgres": values[ROOT+"/actions/runs/9/jobs?per_page=100"]["jobs"].pop()
   elif mutation=="scope": values[ROOT+"/rulesets/8"]["conditions"]={"ref_name":{"include":["other"]}}
   else: values[ROOT+"/actions/runs/7"]["name"]="wrong"
   with self.subTest(mutation=mutation),self.assertRaises(RegressionEvidenceBlocked): self.proof(values)
 def test_invalid_upstream_event_blocks(self):
  for field,value in (("event","pull_request"),("head_sha","f"*40),("conclusion","failure"),("run_attempt",2)):
   payload=event(); payload["workflow_run"][field]=value
   with self.subTest(field=field),self.assertRaises(RegressionEvidenceBlocked): self.proof(fixture(),payload)
 def test_postgres_requires_matching_tree_not_only_a_sha(self):
  values=fixture(); qa="c"*40
  values[ROOT+"/actions/workflows/manual-project-control-postgres.yml/runs?event=pull_request&status=success&per_page=100"]["workflow_runs"][0]["head_sha"]=qa
  values[ROOT+"/git/commits/"+qa]={"tree":{"sha":"d"*40}}
  values[ROOT+"/actions/runs/9/jobs?per_page=100"]["jobs"]=[{**job,"head_sha":qa} for job in values[ROOT+"/actions/runs/9/jobs?per_page=100"]["jobs"]]
  with self.assertRaises(RegressionEvidenceBlocked): self.proof(values)
