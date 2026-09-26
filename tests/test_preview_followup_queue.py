import json
import unittest
from unittest.mock import patch

from ai_product_factory.preview_followup_queue import SupabasePreviewFollowupQueue


class Response:
    def __init__(self,data): self.data=data
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self): return json.dumps(self.data).encode()


class Tests(unittest.TestCase):
    def test_empty_queue_returns_none(self):
        with patch("urllib.request.urlopen",return_value=Response([])):
            q=SupabasePreviewFollowupQueue(url="https://x.supabase.co",secret_key="sb_secret_x")
            self.assertIsNone(q.next_pending())

    def test_maps_preview_ready_item_with_quality_gate(self):
        rows=[
            [{"id":"r","task_id":"t","branch_name":"factory/t","candidate_commit":"abc","metadata":{"github_issue":{"number":7}}}],
            [{"project_id":"p"}],
            [{"project_key":"demo","repository":"owner/repo","manifest":{"preview":{"provider":"vercel","team_id":"team","project_name":"web"}}}],
            [{"metadata":{"pr":9,"head_sha":"abc"}}],
            [{"status":"success","baseline_ref":"abc","result":{"passed":True}}],
        ]
        with patch("urllib.request.urlopen",side_effect=[Response(x) for x in rows]):
            item=SupabasePreviewFollowupQueue(url="https://x.supabase.co",secret_key="sb_secret_x").next_pending()
        self.assertEqual(item.run_id,"r")
        self.assertEqual(item.pr_number,9)
        self.assertEqual(item.manifest["preview"]["project_name"],"web")

    def test_quality_gate_must_match_candidate(self):
        rows=[
            [{"id":"r","task_id":"t","branch_name":"factory/t","candidate_commit":"abc","metadata":{"github_issue":{"number":7}}}],
            [{"project_id":"p"}],
            [{"project_key":"demo","repository":"owner/repo","manifest":{}}],
            [{"metadata":{"pr":9,"head_sha":"abc"}}],
            [{"status":"success","baseline_ref":"other","result":{"passed":True}}],
        ]
        with patch("urllib.request.urlopen",side_effect=[Response(x) for x in rows]):
            with self.assertRaises(RuntimeError):
                SupabasePreviewFollowupQueue(url="https://x.supabase.co",secret_key="sb_secret_x").next_pending()


if __name__=="__main__": unittest.main()
