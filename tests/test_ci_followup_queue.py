import json
import unittest
from unittest.mock import patch

from ai_product_factory.ci_followup_queue import SupabaseCIFollowupQueue

class Response:
    def __init__(self,data): self.data=data
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self): return json.dumps(self.data).encode()

class Tests(unittest.TestCase):
    def test_empty_queue_returns_none(self):
        with patch("urllib.request.urlopen",return_value=Response([])):
            q=SupabaseCIFollowupQueue(url="https://x.supabase.co",secret_key="sb_secret_x")
            self.assertIsNone(q.next_pending())

    def test_maps_durable_ci_item(self):
        run=[{"id":"r","task_id":"t","branch_name":"factory/t","candidate_commit":"abc","metadata":{"github_issue":{"number":7},"human_gate_required":False}}]
        task=[{"project_id":"p"}]
        project=[{"project_key":"demo","repository":"owner/repo"}]
        usage=[{"metadata":{"pr":9,"head_sha":"abc"}}]
        with patch("urllib.request.urlopen",side_effect=[Response(run),Response(task),Response(project),Response(usage)]):
            q=SupabaseCIFollowupQueue(url="https://x.supabase.co",secret_key="sb_secret_x")
            item=q.next_pending()
        self.assertEqual(item.repository,"owner/repo")
        self.assertEqual(item.issue_number,7)
        self.assertEqual(item.pr_number,9)
        self.assertEqual(item.candidate_commit,"abc")

    def test_change_set_identity_is_preserved_for_drift_diagnostics(self):
        run=[{"id":"r","task_id":"t","branch_name":"factory/t","candidate_commit":"abc","metadata":{"source":"change-set","change_set_id":"change-123","github_issue":{"number":7}}}]
        task=[{"project_id":"p"}]
        project=[{"project_key":"crm","repository":"owner/crm"}]
        usage=[{"metadata":{"pr":9,"head_sha":"abc"}}]
        with patch("urllib.request.urlopen",side_effect=[Response(run),Response(task),Response(project),Response(usage)]):
            item=SupabaseCIFollowupQueue(url="https://x.supabase.co",secret_key="sb_secret_x").next_pending()
        self.assertEqual(item.change_set_id,"change-123")

    def test_operator_reconciled_dogfood_can_use_metadata_pr_number(self):
        run=[{"id":"r","task_id":"t","branch_name":"factory/t","candidate_commit":"abc","metadata":{"source":"operator_reconciled_dogfood","pr_number":16,"github_issue":{"number":15}}}]
        task=[{"project_id":"p"}]
        project=[{"project_key":"crm","repository":"owner/crm"}]
        usage=[]
        with patch("urllib.request.urlopen",side_effect=[Response(run),Response(task),Response(project),Response(usage)]):
            q=SupabaseCIFollowupQueue(url="https://x.supabase.co",secret_key="sb_secret_x")
            item=q.next_pending()
        self.assertEqual(item.pr_number,16)
        self.assertEqual(item.candidate_commit,"abc")
        self.assertEqual(item.issue_number,15)

    def test_operator_reconciled_dogfood_still_requires_pr_number(self):
        run=[{"id":"r","task_id":"t","branch_name":"factory/t","candidate_commit":"abc","metadata":{"source":"operator_reconciled_dogfood","github_issue":{"number":15}}}]
        task=[{"project_id":"p"}]
        project=[{"project_key":"crm","repository":"owner/crm"}]
        usage=[]
        with patch("urllib.request.urlopen",side_effect=[Response(run),Response(task),Response(project),Response(usage)]):
            q=SupabaseCIFollowupQueue(url="https://x.supabase.co",secret_key="sb_secret_x")
            with self.assertRaisesRegex(RuntimeError,"missing PR number"):
                q.next_pending()

    def test_reconciled_candidate_requires_exact_audited_receipt(self):
        run=[{"id":"r","task_id":"t","branch_name":"factory/t","candidate_commit":"new","metadata":{"source":"change-set","change_set_id":"cs","github_issue":{"number":7}}}]
        task=[{"project_id":"p"}]
        project=[{"project_key":"crm","repository":"owner/crm"}]
        original=[{"metadata":{"pr":9,"head_sha":"old"}}]
        receipt=[{"metadata":{"pr_number":"9","previous_commit":"old","candidate_commit":"new","change_set_id":"cs"}}]
        with patch("urllib.request.urlopen",side_effect=[Response(run),Response(task),Response(project),Response(original),Response(receipt)]):
            item=SupabaseCIFollowupQueue(url="https://x.supabase.co",secret_key="sb_secret_x").next_pending()
        self.assertEqual(item.candidate_commit,"new")
        self.assertEqual(item.pr_number,9)

    def test_reconciled_candidate_rejects_wrong_receipt(self):
        run=[{"id":"r","task_id":"t","branch_name":"factory/t","candidate_commit":"new","metadata":{"source":"change-set","change_set_id":"cs","github_issue":{"number":7}}}]
        task=[{"project_id":"p"}]
        project=[{"project_key":"crm","repository":"owner/crm"}]
        original=[{"metadata":{"pr":9,"head_sha":"old"}}]
        receipt=[{"metadata":{"pr_number":"8","previous_commit":"old","candidate_commit":"new","change_set_id":"cs"}}]
        with patch("urllib.request.urlopen",side_effect=[Response(run),Response(task),Response(project),Response(original),Response(receipt)]):
            with self.assertRaisesRegex(RuntimeError,"durable PR evidence"):
                SupabaseCIFollowupQueue(url="https://x.supabase.co",secret_key="sb_secret_x").next_pending()

    def test_pr_evidence_must_match_candidate(self):
        run=[{"id":"r","task_id":"t","branch_name":"factory/t","candidate_commit":"abc","metadata":{"github_issue":{"number":7}}}]
        task=[{"project_id":"p"}]
        project=[{"project_key":"demo","repository":"owner/repo"}]
        usage=[{"metadata":{"pr":9,"head_sha":"other"}}]
        with patch("urllib.request.urlopen",side_effect=[Response(run),Response(task),Response(project),Response(usage),Response([])]):
            q=SupabaseCIFollowupQueue(url="https://x.supabase.co",secret_key="sb_secret_x")
            with self.assertRaises(RuntimeError): q.next_pending()

    def test_prior_ci_dispatch_is_bound_to_run_sha_branch_and_workflow(self):
        q=SupabaseCIFollowupQueue(url="https://x.supabase.co",secret_key="sb_secret_x")
        receipt={"metadata":{"pr":9,"head_sha":"a"*40,"workflow":"validate.yml","ref":"factory/cs-a"}}
        with patch.object(q,"_get",return_value=[receipt]) as get:
            self.assertTrue(q.has_ci_dispatch_receipt(
                run_id="run-1",pr_number=9,candidate_commit="a"*40,
                branch="factory/cs-a",workflow="validate.yml",
            ))
        self.assertIn("operation=eq.dispatch_ci",get.call_args.args[0])
        self.assertIn("run_id=eq.run-1",get.call_args.args[0])
        with patch.object(q,"_get",return_value=[receipt]):
            self.assertFalse(q.has_ci_dispatch_receipt(
                run_id="run-1",pr_number=9,candidate_commit="b"*40,
                branch="factory/cs-a",workflow="validate.yml",
            ))

    def test_same_sha_receipt_identity_drift_is_blocked(self):
        q=SupabaseCIFollowupQueue(url="https://x.supabase.co",secret_key="sb_secret_x")
        for mutation in ({"pr":10},{"ref":"factory/other"},{"workflow":"other.yml"}):
            receipt={"metadata":{"pr":9,"head_sha":"a"*40,"workflow":"validate.yml",
                                 "ref":"factory/cs-a",**mutation}}
            with self.subTest(mutation=mutation),patch.object(q,"_get",return_value=[receipt]):
                with self.assertRaisesRegex(RuntimeError,"identity drift"):
                    q.has_ci_dispatch_receipt(
                        run_id="run-1",pr_number=9,candidate_commit="a"*40,
                        branch="factory/cs-a",workflow="validate.yml",
                    )

    def test_malformed_or_unbounded_receipts_are_rejected(self):
        q=SupabaseCIFollowupQueue(url="https://x.supabase.co",secret_key="sb_secret_x")
        for invalid in ([{}],["malformed"],[{"metadata":[]}],[{"metadata":{}}]*11):
            with self.subTest(invalid=str(invalid)[:50]),patch.object(q,"_get",return_value=invalid):
                with self.assertRaises(RuntimeError):
                    q.has_ci_dispatch_receipt(
                        run_id="run-1",pr_number=9,candidate_commit="a"*40,
                        branch="factory/cs-a",workflow="validate.yml",
                    )

    def test_invalid_branch_or_sha_is_rejected_before_io(self):
        q=SupabaseCIFollowupQueue(url="https://x.supabase.co",secret_key="sb_secret_x")
        for branch,sha in (("main","a"*40),("bad branch","a"*40),
                           ("factory/cs","short"),("factory/cs","A"*40)):
            with self.subTest(branch=branch,sha=sha),patch.object(q,"_get") as get:
                with self.assertRaises(ValueError):
                    q.has_ci_dispatch_receipt(
                        run_id="run-1",pr_number=9,candidate_commit=sha,
                        branch=branch,workflow="validate.yml",
                    )
                get.assert_not_called()


if __name__=="__main__": unittest.main()
