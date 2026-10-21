import json
import unittest
from unittest.mock import patch

from ai_product_factory.project_release_reconciliation import SupabaseProjectReleaseReconciler

PID="11111111-1111-4111-8111-111111111111"
RUN="22222222-2222-4222-8222-222222222222"
SHA="b"*40
CANDIDATE="a"*40


def release_report():
    return {"project_id":PID,"run_id":RUN,"status":"released",
            "candidate_commit":CANDIDATE,
            "report":{"merge_sha":SHA,"released_by":"observed_manual_merge",
                      "product_readiness":{"status":"not_assessed","ready":False}}}


def receipt(idempotent=False):
    return {"project_id":PID,"run_id":RUN,"lifecycle_stage":"operations",
            "merge_sha":SHA,"product_ready":False,"pending_domains":6,
            "idempotent":idempotent,"snapshot_written":not idempotent,
            "audit_written":not idempotent,
            "change_set_status":"completed","change_set_updated":not idempotent}


class Response:
    def __init__(self,data):self.data=data
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self):return json.dumps(self.data).encode()


class Tests(unittest.TestCase):
    def test_reconciles_only_via_one_atomic_service_role_rpc(self):
        calls=[]
        def fake(req,timeout=30):
            calls.append((req.method,req.full_url,json.loads(req.data) if req.data else None))
            if req.method=="GET":return Response([release_report()])
            return Response(receipt())
        with patch("urllib.request.urlopen",side_effect=fake):
            out=SupabaseProjectReleaseReconciler(url="https://example.test",secret_key="sb_secret_t").reconcile(
                project_id=PID,run_id=RUN,merge_sha=SHA)
        self.assertFalse(out["idempotent"])
        self.assertEqual([x[0] for x in calls],["GET","POST"])
        self.assertIn("factory_release_reports?",calls[0][1])
        self.assertTrue(calls[1][1].endswith("/rpc/factory_reconcile_observed_release_v1"))
        self.assertEqual(calls[1][2]["p_release_report"],release_report()["report"])
        f=calls[1][2]["p_followup"]
        self.assertEqual(f["pending_domains"],["security","observability_operations",
                         "test_strategy","product_experience","documentation","functional_completeness"])
        self.assertFalse(f["ready"])
        self.assertTrue(f["report_verified"])

    def test_atomic_migration_capability_is_read_only_and_fail_closed(self):
        q=SupabaseProjectReleaseReconciler(url="https://example.test",secret_key="sb_secret_t")
        calls=[]
        def fake(req,timeout=30):
            calls.append((req.method,req.full_url,json.loads(req.data) if req.data else None))
            return Response([])
        with patch("urllib.request.urlopen",side_effect=fake):
            self.assertIsNone(q.require_atomic_capability())
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0][0],"POST")
        self.assertTrue(calls[0][1].endswith("/rpc/factory_pending_release_reconciliations_v1"))
        self.assertEqual(calls[0][2],{"p_after_event_id":0,"p_limit":1})
        with patch("urllib.request.urlopen",return_value=Response({})):
            with self.assertRaisesRegex(RuntimeError,"capability unavailable"):
                q.require_atomic_capability()

    def test_idempotent_receipt_and_invalid_input(self):
        with patch("urllib.request.urlopen",side_effect=[
            Response([release_report()]),Response(receipt(True))
        ]) as remote:
            out=SupabaseProjectReleaseReconciler(url="https://x.supabase.co",secret_key="x").reconcile(
                project_id=PID,run_id=RUN,merge_sha=SHA)
        self.assertTrue(out["idempotent"])
        self.assertEqual(remote.call_count,2)
        with patch("urllib.request.urlopen") as fail:
            q=SupabaseProjectReleaseReconciler(url="https://x.supabase.co",secret_key="x")
            for arg in ((PID,RUN,"malformed"),("cross-project",RUN,SHA),(PID,"bogus",SHA)):
                with self.assertRaises(ValueError):
                    q.reconcile(project_id=arg[0],run_id=arg[1],merge_sha=arg[2])
            fail.assert_not_called()

    def test_bad_or_ambiguous_release_does_not_mutate(self):
        for rows in ([],[release_report(),release_report()],
                     [{**release_report(),"status":"blocked"}],
                     [{**release_report(),"report":{"merge_sha":"f"*40}}]):
            calls=[]
            def remote(method,path,payload=None):
                calls.append((method,path,payload))
                return rows
            q=object.__new__(SupabaseProjectReleaseReconciler)
            q._request=remote
            with self.subTest(rows=rows),self.assertRaises(RuntimeError):
                q.reconcile(project_id=PID,run_id=RUN,merge_sha=SHA)
            self.assertEqual(len(calls),1)
            self.assertEqual(calls[0][0],"GET")

    def test_bounded_recovery_skips_failed_candidate_but_settles_another(self):
        other="33333333-3333-4333-8333-333333333333"
        requests=[]
        q=object.__new__(SupabaseProjectReleaseReconciler)
        def remote(method,path,payload=None):
            requests.append((method,path,payload))
            if path.endswith("factory_pending_release_reconciliations_v1"):
                return [
                    {"event_id":12,"project_id":PID,"run_id":RUN,"merge_sha":SHA},
                    {"event_id":14,"project_id":other,"run_id":RUN,"merge_sha":SHA},
                ]
            self.fail("unwanted network request")
        q._request=remote
        def reconcile(*,project_id,run_id,merge_sha):
            if project_id==PID:raise RuntimeError("exact released report unavailable")
            return {"idempotent":False}
        q.reconcile=reconcile
        q._defer_manual_review=lambda event_id:requests.append(("POST","deferred",event_id))
        out=q.settle_pending(max_items=2)
        self.assertEqual(out["scanned"],2)
        self.assertEqual(out["reconciled"],1)
        self.assertEqual(len(out["needs_review"]),1)
        self.assertTrue(out["truncated"])
        self.assertEqual(len(requests),2)
        self.assertEqual(requests[1],("POST","deferred",12))

    def test_transient_failure_never_parks_a_human_release(self):
        q=object.__new__(SupabaseProjectReleaseReconciler)
        q._request=lambda method,path,payload=None:[
          {"event_id":7,"project_id":PID,"run_id":RUN,"merge_sha":SHA}
        ]
        q.reconcile=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("release reconciliation Control Plane unavailable"))
        q._defer_manual_review=lambda event_id:self.fail("transient database failure cannot be parked")
        out=q.settle_pending(max_items=1)
        self.assertEqual(out["needs_review"][0]["reason"],"release_reconciliation_retryable")

    def test_out_of_order_keyset_refused(self):
        q=object.__new__(SupabaseProjectReleaseReconciler)
        q._request=lambda *_args,**_kwargs:[{"event_id":5,"project_id":PID,"run_id":RUN,"merge_sha":SHA},
                                             {"event_id":4,"project_id":PID,"run_id":RUN,"merge_sha":SHA}]
        q.reconcile=lambda **kw:{"idempotent":True}
        with self.assertRaisesRegex(RuntimeError,"keyset cursor"):
            q.settle_pending(max_items=4)


if __name__=="__main__":
    unittest.main()
