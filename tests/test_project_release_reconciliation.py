import json
import unittest
from unittest.mock import patch

from ai_product_factory.project_release_reconciliation import SupabaseProjectReleaseReconciler


class Response:
    def __init__(self,data): self.data=data
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self): return json.dumps(self.data).encode()


class Tests(unittest.TestCase):
    def test_reconciles_stale_read_only_project_after_release(self):
        calls=[]
        project={
            "id":"p1",
            "lifecycle_stage":"discovery",
            "manifest":{
                "autonomy":"read_only_verification",
                "head_sha":"old",
                "current_task":"old verification",
                "reported_stage":"verification",
                "runtime_readiness":{"current_scope":"read_only_verification","preview":"verified"},
            },
        }
        def fake_urlopen(req,timeout=30):
            calls.append((req.method,req.full_url,req.data.decode() if req.data else None))
            if req.method=="GET":
                return Response([project])
            return Response([{"ok":True}])
        with patch("urllib.request.urlopen",side_effect=fake_urlopen):
            out=SupabaseProjectReleaseReconciler(url="https://example.test",secret_key="secret").reconcile(
                project_id="p1",run_id="r1",merge_sha="merge1"
            )
        self.assertEqual(out["lifecycle_stage"],"operation")
        patch_call=next(x for x in calls if x[0]=="PATCH")
        payload=json.loads(patch_call[2])
        self.assertEqual(payload["lifecycle_stage"],"operation")
        self.assertEqual(payload["manifest"]["head_sha"],"merge1")
        self.assertEqual(payload["manifest"]["reported_stage"],"operation")
        self.assertNotIn("autonomy",payload["manifest"])
        self.assertNotIn("current_task",payload["manifest"])
        self.assertNotIn("current_scope",payload["manifest"]["runtime_readiness"])
        self.assertEqual(payload["manifest"]["last_release"]["merge_sha"],"merge1")
        self.assertTrue(any("factory_project_state_snapshots" in x[1] for x in calls))
        self.assertTrue(any("factory_audit_events" in x[1] for x in calls))

    def test_is_idempotent_for_same_release(self):
        project={
            "id":"p1",
            "lifecycle_stage":"operation",
            "manifest":{
                "head_sha":"merge1",
                "reported_stage":"operation",
                "last_release":{"run_id":"r1","merge_sha":"merge1","source":"observed_human_merge"},
            },
        }
        calls=[]
        def fake_urlopen(req,timeout=30):
            calls.append(req.method)
            return Response([project])
        with patch("urllib.request.urlopen",side_effect=fake_urlopen):
            out=SupabaseProjectReleaseReconciler(url="https://example.test",secret_key="secret").reconcile(
                project_id="p1",run_id="r1",merge_sha="merge1"
            )
        self.assertTrue(out["idempotent"])
        self.assertEqual(calls,["GET"])


if __name__=="__main__": unittest.main()
