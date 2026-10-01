import json
import unittest
from unittest.mock import patch

from ai_product_factory.change_set_store import SupabaseChangeSetStore


class Response:
    def __init__(self,data): self.data=data
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self): return json.dumps(self.data).encode()


class Tests(unittest.TestCase):
    def test_finalize_released_run_ignores_non_change_set_release(self):
        with patch("urllib.request.urlopen",return_value=Response([])):
            store=SupabaseChangeSetStore(url="https://x.supabase.co",secret_key="sb_secret_x")
            out=store.finalize_released_run("run-1","merge-1")
        self.assertEqual(out,{"matched":False,"status":"not_change_set"})

    def test_finalize_released_run_transitions_ci_pending_to_completed(self):
        rows=[
            [{"id":"cs-1","status":"ci_pending","release_run_id":"run-1","metadata":{"existing":True}}],
            [{"id":"cs-1","status":"completed"}],
        ]
        with patch("urllib.request.urlopen",side_effect=[Response(rows[0]),Response(rows[1])]) as calls:
            store=SupabaseChangeSetStore(url="https://x.supabase.co",secret_key="sb_secret_x")
            out=store.finalize_released_run("run-1","merge-1")
        self.assertEqual(out["status"],"completed")
        self.assertFalse(out["idempotent"])
        request=calls.call_args_list[1].args[0]
        self.assertEqual(request.method,"PATCH")
        payload=json.loads(request.data.decode())
        self.assertEqual(payload["status"],"completed")
        self.assertTrue(payload["metadata"]["existing"])
        self.assertEqual(payload["metadata"]["release"]["run_id"],"run-1")
        self.assertEqual(payload["metadata"]["release"]["merge_sha"],"merge-1")

    def test_finalize_released_run_is_idempotent_when_already_completed(self):
        with patch("urllib.request.urlopen",return_value=Response([
            {"id":"cs-1","status":"completed","release_run_id":"run-1","metadata":{}}
        ])) as calls:
            store=SupabaseChangeSetStore(url="https://x.supabase.co",secret_key="sb_secret_x")
            out=store.finalize_released_run("run-1","merge-1")
        self.assertTrue(out["idempotent"])
        self.assertEqual(calls.call_count,1)

    def test_finalize_released_run_fails_closed_for_incompatible_status(self):
        with patch("urllib.request.urlopen",return_value=Response([
            {"id":"cs-1","status":"blocked","release_run_id":"run-1","metadata":{}}
        ])):
            store=SupabaseChangeSetStore(url="https://x.supabase.co",secret_key="sb_secret_x")
            with self.assertRaisesRegex(RuntimeError,"incompatible status"):
                store.finalize_released_run("run-1","merge-1")


if __name__=="__main__":
    unittest.main()
