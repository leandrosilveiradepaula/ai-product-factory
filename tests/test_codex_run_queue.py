import json
import unittest
from unittest.mock import patch

from ai_product_factory.codex_run_queue import SupabaseCodexRunQueue


class Response:
    def __init__(self,data): self.data=data
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self):
        if self.data is None: return b""
        return json.dumps(self.data).encode()


class Tests(unittest.TestCase):
    def test_empty_queue_is_read_only(self):
        with patch("urllib.request.urlopen",return_value=Response([])) as call:
            item=SupabaseCodexRunQueue(url="https://x.supabase.co",secret_key="sb_secret_x").claim_next("w")
        self.assertIsNone(item)
        self.assertEqual(call.call_count,1)

    def test_claims_codex_run_and_maps_item(self):
        responses=[
            Response([{"id":"r","task_id":"t","metadata":{},"started_at":None,"attempt_count":0}]),
            Response([{"id":"t","project_id":"p","title":"Refactor","description":"Do it","status":"queued_execution"}]),
            Response([{"project_key":"demo","repository":"owner/repo"}]),
            Response([{"id":"r"}]),
            Response([{"id":"t"}]),
            Response(None),
        ]
        with patch("urllib.request.urlopen",side_effect=responses) as call:
            item=SupabaseCodexRunQueue(url="https://x.supabase.co",secret_key="sb_secret_x").claim_next("codex-w")
        self.assertEqual(item.run_id,"r")
        self.assertEqual(item.repository,"owner/repo")
        self.assertEqual(item.branch,"factory/task-t")
        self.assertEqual(call.call_count,6)

    def test_human_gated_codex_run_is_not_claimed(self):
        responses=[
            Response([{"id":"r","task_id":"t","metadata":{"human_gate_required":True},"started_at":None,"attempt_count":0}]),
            Response([{"id":"t","project_id":"p","title":"Risky","description":"x","status":"queued_execution"}]),
            Response([{"project_key":"demo","repository":"owner/repo"}]),
        ]
        with patch("urllib.request.urlopen",side_effect=responses) as call:
            item=SupabaseCodexRunQueue(url="https://x.supabase.co",secret_key="sb_secret_x").claim_next("w")
        self.assertIsNone(item)
        self.assertEqual(call.call_count,3)

    def test_lost_claim_race_returns_none(self):
        responses=[
            Response([{"id":"r","task_id":"t","metadata":{},"started_at":None,"attempt_count":0}]),
            Response([{"id":"t","project_id":"p","title":"Refactor","description":"x","status":"queued_execution"}]),
            Response([{"project_key":"demo","repository":"owner/repo"}]),
            Response([]),
        ]
        with patch("urllib.request.urlopen",side_effect=responses):
            item=SupabaseCodexRunQueue(url="https://x.supabase.co",secret_key="sb_secret_x").claim_next("w")
        self.assertIsNone(item)


if __name__=="__main__": unittest.main()
