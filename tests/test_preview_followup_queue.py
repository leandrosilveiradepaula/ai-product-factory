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
        rows.insert(1, [])  # Candidate has no recent quota block.
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
        rows.insert(1, [])
        with patch("urllib.request.urlopen",side_effect=[Response(x) for x in rows]):
            with self.assertRaises(RuntimeError):
                SupabasePreviewFollowupQueue(url="https://x.supabase.co",secret_key="sb_secret_x").next_pending()

    def test_blocked_oldest_and_manual_audit_do_not_starve_next_delivery(self):
        runs=[
            {"id":"old","task_id":"t0","branch_name":"factory/old","candidate_commit":"s0","metadata":{"github_issue":{"number":8}}},
            {"id":"audit","candidate_commit":"audit-sha","metadata":{"source":"dogfood_manual_audit"}},
            {"id":"new","task_id":"t1","branch_name":"factory/new","candidate_commit":"s1","metadata":{"github_issue":{"number":7}}},
        ]
        rows=[
            runs,
            [{"run_id":"old","metadata":{"candidate_commit":"s0"}}],
            [], [{"project_id":"p"}],
            [{"project_key":"demo","repository":"owner/repo","manifest":{}}],
            [{"metadata":{"pr":9,"head_sha":"s1"}}],
            [{"status":"success","baseline_ref":"s1","result":{"passed":True}}],
        ]
        with patch("urllib.request.urlopen",side_effect=[Response(x) for x in rows]):
            item=SupabasePreviewFollowupQueue(url="https://x.supabase.co",secret_key="sb_secret_x").next_pending()
        self.assertEqual(item.run_id,"new")

    def test_only_quota_blocked_and_audit_runs_are_not_eligible(self):
        rows=[
            [{"id":"old","candidate_commit":"sha","metadata":{"github_issue":{"number":7}}},
             {"id":"audit","metadata":{"source":"dogfood_manual_audit"}}],
            [{"run_id":"old","metadata":{"candidate_commit":"sha"}}],
        ]
        with patch("urllib.request.urlopen",side_effect=[Response(x) for x in rows]):
            self.assertIsNone(SupabasePreviewFollowupQueue(
                url="https://x.supabase.co",secret_key="sb_secret_x"
            ).next_pending())

    def test_different_sha_does_not_inherit_prior_quota_failure(self):
        rows=[
            [{"id":"r","task_id":"t","branch_name":"factory/t","candidate_commit":"new","metadata":{"github_issue":{"number":7}}}],
            [{"run_id":"r","metadata":{"candidate_commit":"old"}}],
            [{"project_id":"p"}],
            [{"project_key":"demo","repository":"owner/repo","manifest":{}}],
            [{"metadata":{"pr":9,"head_sha":"new"}}],
            [{"status":"success","baseline_ref":"new","result":{"passed":True}}],
        ]
        with patch("urllib.request.urlopen",side_effect=[Response(x) for x in rows]):
            item=SupabasePreviewFollowupQueue(url="https://x.supabase.co",secret_key="sb_secret_x").next_pending()
        self.assertEqual(item.candidate_commit,"new")


if __name__=="__main__": unittest.main()
