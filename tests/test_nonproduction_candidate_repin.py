import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from ai_product_factory.nonproduction_candidate_repin import verify_candidate

OLD="a"*40
NEW="b"*40
REPO="leandrosilveiradepaula/crm-infodive"
BRANCH="preview/hardening-release-candidate"


def github():
    g=MagicMock()
    g.repository=REPO
    g.get_branch_sha.return_value=NEW
    g.get_pull_request.return_value=SimpleNamespace(
        number=56,state="open",merged=False,head_sha=NEW,head_ref=BRANCH,
        head_repository=REPO,base_ref="main")
    g.compare_commits.return_value={"status":"ahead","ahead_by":4,"behind_by":0}
    g._call.return_value={"workflow_runs":[{
        "id":39189959689,"name":"CRM validation","head_sha":NEW,
        "head_branch":BRANCH,"status":"completed","conclusion":"success"
    }]}
    return g


def run(g):
    return verify_candidate(g,repository=REPO,branch=BRANCH,number=56,
                            old_sha=OLD,new_sha=NEW)


class CandidateRePinTests(unittest.TestCase):
    def test_verified_exact_sha(self):
        result=run(github())
        self.assertEqual(result["ci_sha"],NEW)
        self.assertEqual(result["ci_run_id"],39189959689)
        self.assertEqual(result["pr_number"],"56")
        self.assertEqual(result["ahead_by"],4)
        self.assertEqual(result["source"],"github_actions_exact_sha")

    def test_target_rejects_ref_or_pr_drift(self):
        for attr,value in (("state","closed"),("merged",True),
            ("head_sha","c"*40),("head_repository","attacker/repo"),
            ("base_ref","preview"),("number",57),("head_ref","main")):
            g=github()
            setattr(g.get_pull_request.return_value,attr,value)
            with self.subTest(attr=attr),self.assertRaises(PermissionError):
                run(g)
        g=github()
        g.get_branch_sha.return_value="c"*40
        with self.assertRaises(PermissionError):run(g)

    def test_comparison_requires_strict_fast_forward(self):
        for evidence in (
            {"status":"diverged","ahead_by":4,"behind_by":1},
            {"status":"identical","ahead_by":0,"behind_by":0},
            {"status":"behind","ahead_by":0,"behind_by":2},
            {"status":"ahead","ahead_by":True,"behind_by":0},
            {"status":"ahead","ahead_by":10001,"behind_by":0},
        ):
            g=github()
            g.compare_commits.return_value=evidence
            with self.subTest(evidence=evidence),self.assertRaises(PermissionError):
                run(g)

    def test_exact_required_ci_does_not_accept_vercel_only(self):
        for row in (
            {"id":55,"name":"Vercel","head_sha":NEW,"head_branch":BRANCH,
             "status":"completed","conclusion":"success"},
            {"id":55,"name":"CRM validation","head_sha":OLD,"head_branch":BRANCH,
             "status":"completed","conclusion":"success"},
            {"id":55,"name":"CRM validation","head_sha":NEW,"head_branch":BRANCH,
             "status":"completed","conclusion":"failure"},
            {"id":55,"name":"CRM validation","head_sha":NEW,"head_branch":BRANCH,
             "status":"in_progress","conclusion":None},
        ):
            g=github()
            g._call.return_value={"workflow_runs":[row]}
            with self.subTest(row=row),self.assertRaises(PermissionError):
                run(g)

    def test_repin_never_claims_paid_release_or_merge(self):
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        script=(root/"src/ai_product_factory/nonproduction_candidate_repin.py").read_text()
        sql=(root/"supabase/migrations/20261019031000_repin_nonproduction_target.sql").read_text()
        workflow=(root/".github/workflows/autonomous-runner.yml").read_text()
        for forbidden in ("OPENAI_API_KEY","merge_pull_request","mark_released","workflow_dispatch("):
            self.assertNotIn(forbidden,script)
        for required in ("for update","generation=generation+1",
                         "project.delivery_target.reconciled",
                         "factory_control_quiescent","from public,anon,authenticated",
                         "to service_role"):
            self.assertIn(required,sql)
        self.assertIn("--mode candidate-repin",workflow)

if __name__=="__main__":
    unittest.main()
