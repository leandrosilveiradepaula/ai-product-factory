import json
import unittest
from unittest.mock import patch

from ai_product_factory.release_followup_queue import SupabaseReleaseFollowupQueue


class Response:
    def __init__(self,data): self.data=data
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self): return json.dumps(self.data).encode()


class Tests(unittest.TestCase):
    def test_empty_queue_returns_none(self):
        with patch("urllib.request.urlopen",return_value=Response([])):
            q=SupabaseReleaseFollowupQueue(url="https://x.supabase.co",secret_key="sb_secret_x")
            self.assertIsNone(q.next_pending())

    def test_maps_verified_release_item(self):
        rows=[
            [{"id":"r","task_id":"t","branch_name":"factory/t","candidate_commit":"abc","metadata":{"github_issue":{"number":7}}}],
            [{"project_id":"p"}],
            [{"project_key":"demo","repository":"owner/repo"}],
            [],
            [{"metadata":{"pr":9,"head_sha":"abc","preview_url":"https://preview.example"}}],
        ]
        with patch("urllib.request.urlopen",side_effect=[Response(x) for x in rows]):
            item=SupabaseReleaseFollowupQueue(url="https://x.supabase.co",secret_key="sb_secret_x").next_pending()
        self.assertEqual(item.run_id,"r")
        self.assertEqual(item.pr_number,9)
        self.assertEqual(item.issue_number,7)
        self.assertEqual(item.candidate_commit,"abc")
        self.assertIsNone(item.merge_sha)

    def test_maps_released_console_report_without_issue_binding(self):
        rows=[
            [{"id":"r","task_id":"t","branch_name":"factory/t","candidate_commit":"abc","metadata":{"source":"factory_release_gate"}}],
            [{"project_id":"p"}],
            [{"project_key":"demo","repository":"owner/repo"}],
            [{"status":"released","candidate_commit":"abc","report":{"pr_number":9,"merge_sha":"merge123"}}],
        ]
        with patch("urllib.request.urlopen",side_effect=[Response(x) for x in rows]):
            item=SupabaseReleaseFollowupQueue(url="https://x.supabase.co",secret_key="sb_secret_x").next_pending()
        self.assertEqual(item.pr_number,9)
        self.assertIsNone(item.issue_number)
        self.assertEqual(item.merge_sha,"merge123")
        self.assertEqual(item.release_source,"console_report")

    def test_released_report_must_match_candidate(self):
        rows=[
            [{"id":"r","task_id":"t","branch_name":"factory/t","candidate_commit":"abc","metadata":{}}],
            [{"project_id":"p"}],
            [{"project_key":"demo","repository":"owner/repo"}],
            [{"status":"released","candidate_commit":"different","report":{"pr_number":9,"merge_sha":"merge123"}}],
        ]
        with patch("urllib.request.urlopen",side_effect=[Response(x) for x in rows]):
            with self.assertRaisesRegex(RuntimeError,"released report"):
                SupabaseReleaseFollowupQueue(url="https://x.supabase.co",secret_key="sb_secret_x").next_pending()

    def test_release_evidence_must_match_candidate(self):
        rows=[
            [{"id":"r","task_id":"t","branch_name":"factory/t","candidate_commit":"abc","metadata":{"github_issue":{"number":7}}}],
            [{"project_id":"p"}],
            [{"project_key":"demo","repository":"owner/repo"}],
            [],
            [{"metadata":{"pr":9,"head_sha":"different"}}],
        ]
        with patch("urllib.request.urlopen",side_effect=[Response(x) for x in rows]):
            with self.assertRaises(RuntimeError):
                SupabaseReleaseFollowupQueue(url="https://x.supabase.co",secret_key="sb_secret_x").next_pending()


if __name__=="__main__": unittest.main()
