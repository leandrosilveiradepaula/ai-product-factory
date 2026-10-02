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

    def test_pr_evidence_must_match_candidate(self):
        run=[{"id":"r","task_id":"t","branch_name":"factory/t","candidate_commit":"abc","metadata":{"github_issue":{"number":7}}}]
        task=[{"project_id":"p"}]
        project=[{"project_key":"demo","repository":"owner/repo"}]
        usage=[{"metadata":{"pr":9,"head_sha":"other"}}]
        with patch("urllib.request.urlopen",side_effect=[Response(run),Response(task),Response(project),Response(usage)]):
            q=SupabaseCIFollowupQueue(url="https://x.supabase.co",secret_key="sb_secret_x")
            with self.assertRaises(RuntimeError): q.next_pending()

if __name__=="__main__": unittest.main()
