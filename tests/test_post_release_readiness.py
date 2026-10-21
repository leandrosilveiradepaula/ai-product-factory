"""Offline regressions for post-release global-product-readiness handoff."""
from __future__ import annotations

import unittest
from copy import deepcopy

from ai_product_factory.admission_diagnostics import classify
from ai_product_factory.post_release_readiness import (
    observe_manifest_release,summarize_released_product,validated_manifest_followup,
)
from ai_product_factory.product_readiness import REQUIRED_DOMAINS
from ai_product_factory.project_release_reconciliation import SupabaseProjectReleaseReconciler
from ai_product_factory.supabase_runtime_queue import SupabaseRuntimeQueue

P="11111111-1111-4111-8111-111111111111"
R="22222222-2222-4222-8222-222222222222"
C="a"*40
M="b"*40


def report(readiness=None):
    return {"project_id":P,"run_id":R,"status":"released","candidate_commit":C,
            "report":{"merge_sha":M,"product_complete":False,
                      "product_readiness":readiness or {"ready":False,"status":"not_assessed"},
                      "private_user_prompt":"Never output the source report."}}


def manifest(followup=None):
    return {"last_release":{"run_id":R,"merge_sha":M,"source":"observed_human_merge"},
            **({"product_readiness_followup":followup} if followup else {})}


class PostReleaseReadinessTests(unittest.TestCase):
    def test_real_not_assessed_report_keeps_all_six_evidence_obligations(self):
        out=summarize_released_product(project_id=P,run_id=R,merge_sha=M,report_rows=[report()])
        self.assertEqual(out["status"],"not_assessed")
        self.assertTrue(out["report_verified"])
        self.assertFalse(out["ready"])
        self.assertEqual(out["reason_code"],"global_readiness_not_assessed")
        self.assertEqual(out["pending_domains"],list(REQUIRED_DOMAINS))
        self.assertNotIn("private_user_prompt",str(out))
        self.assertEqual(validated_manifest_followup(manifest(out)),out)

    def test_passing_candidate_never_grants_current_product_ready(self):
        raw={"ready":True,"status":"passed","domains":{
            x:{"status":"passed"} for x in REQUIRED_DOMAINS
        }}
        out=summarize_released_product(project_id=P,run_id=R,merge_sha=M,report_rows=[report(raw)])
        self.assertEqual(out["status"],"candidate_only")
        self.assertFalse(out["ready"])
        self.assertEqual(out["reason_code"],"candidate_assessment_not_current_head")
        self.assertEqual(out["candidate_assessed_domains"],list(REQUIRED_DOMAINS))
        self.assertEqual(out["pending_domains"],list(REQUIRED_DOMAINS))

    def test_missing_failed_and_unknown_readiness_fail_closed(self):
        for rows,expected in [
            (None,"release_report_unavailable_or_ambiguous"),
            ([],"release_report_unavailable_or_ambiguous"),
            ([report(),report()],"release_report_unavailable_or_ambiguous"),
            ([{**report(),"run_id":P}],"release_report_identity_unverified"),
            ([{**report(),"project_id":R}],"release_report_identity_unverified"),
            ([{**report(),"status":"ready_for_human_release"}],"release_report_identity_unverified"),
            ([{**report(),"candidate_commit":"broken"}],"release_report_provenance_unverified"),
            ([{**report(),"report":{"merge_sha":"other"}}],"release_report_provenance_unverified"),
        ]:
            with self.subTest(reason=expected):
                out=summarize_released_product(project_id=P,run_id=R,merge_sha=M,report_rows=rows)
                self.assertFalse(out["ready"])
                self.assertFalse(out["report_verified"])
                self.assertEqual(out["reason_code"],expected)
        failed=summarize_released_product(project_id=P,run_id=R,merge_sha=M,
            report_rows=[report({"ready":False,"status":"not_ready"})])
        self.assertEqual(failed["status"],"not_ready")

    def test_manifest_tampering_fails_validation_without_leaking(self):
        correct=summarize_released_product(project_id=P,run_id=R,merge_sha=M,report_rows=[report()])
        tests=[
            {"last_release":{"run_id":P,"merge_sha":M},"product_readiness_followup":correct},
            {"last_release":{"run_id":R,"merge_sha":"tampered"},"product_readiness_followup":correct},
        ]
        for key,val in (
            ("ready",True),("status","passed"),
            ("scope","candidate_only"),("pending_domains",[]),
            ("reason_code","overwrite_auth"),("next_step","execute_paid_model"),
            ("candidate_assessed_domains",["not_a_domain"]),
        ):
            out=deepcopy(correct)
            out[key]=val
            tests.append(manifest(out))
        for data in tests:
            with self.subTest(case=data):
                self.assertIsNone(validated_manifest_followup(data))

    def test_legacy_release_observed_by_bounded_exact_project_and_run(self):
        paths=[]
        def getter(path):
            paths.append(path)
            return [report()]
        summary=observe_manifest_release(get=getter,project_id=P,manifest=manifest())
        self.assertEqual(summary["status"],"not_assessed")
        self.assertEqual(len(paths),1)
        self.assertIn("project_id=eq."+P,paths[0])
        self.assertIn("run_id=eq."+R,paths[0])
        self.assertIn("limit=2",paths[0])
        restored=manifest(summary)
        self.assertEqual(observe_manifest_release(get=lambda _:self.fail("unexpected DB read"),
                              project_id=P,manifest=restored),summary)

    def test_untrusted_input_does_not_create_cross_project_read(self):
        for m in (
            None,
            {"last_release":{"run_id":"x;DROP TABLE","merge_sha":M}},
            {"last_release":{"run_id":R,"merge_sha":"not_sha"}},
        ):
            self.assertIsNone(observe_manifest_release(get=lambda _:self.fail("must not read"),
                          project_id=P,manifest=m))
        self.assertIsNone(observe_manifest_release(get=lambda _:self.fail("must not read"),
                          project_id="unsafe/key",manifest=manifest()))
        unknown=observe_manifest_release(
            get=lambda path: (_ for _ in ()).throw(RuntimeError("secret-key-in-error")),
            project_id=P,manifest=manifest())
        self.assertEqual(unknown["status"],"unknown")
        self.assertNotIn("secret-key-in-error",str(unknown))

    def test_release_reconciler_passes_six_nonexecutable_audit_gaps_to_atomic_rpc(self):
        observed=[]
        def rpc(method,path,payload=None):
            observed.append((method,path,payload))
            if method=="GET":
                return [report()]
            return {"project_id":P,"run_id":R,"merge_sha":M,
                    "lifecycle_stage":"operations","product_ready":False,
                    "idempotent":False,"snapshot_written":True,
                    "audit_written":True,"pending_domains":6}
        rec=object.__new__(SupabaseProjectReleaseReconciler)
        rec._request=rpc
        out=rec.reconcile(project_id=P,run_id=R,merge_sha=M)
        self.assertEqual(out["lifecycle_stage"],"operations")
        self.assertEqual([x[0] for x in observed],["GET","POST"])
        self.assertEqual(observed[1][1],"rpc/factory_reconcile_observed_release_v1")
        followup=observed[1][2]["p_followup"]
        self.assertEqual(followup["status"],"not_assessed")
        self.assertFalse(followup["ready"])
        self.assertEqual(followup["pending_domains"],list(REQUIRED_DOMAINS))
        self.assertFalse(any(method=="PATCH" for method,_,_ in observed))

    def test_release_report_read_failure_does_not_promote_product(self):
        observed=[]
        def rpc(method,path,payload=None):
            observed.append((method,path,payload))
            raise RuntimeError("release read unavailable")
        rec=object.__new__(SupabaseProjectReleaseReconciler)
        rec._request=rpc
        with self.assertRaisesRegex(RuntimeError,"release read unavailable"):
            rec.reconcile(project_id=P,run_id=R,merge_sha=M)
        self.assertEqual(len(observed),1)
        self.assertEqual(observed[0][0],"GET")

    def test_followup_injected_into_next_authorized_reconciliation_only(self):
        queue=object.__new__(SupabaseRuntimeQueue)
        inspected=[]
        def getter(path):
            inspected.append(path)
            if path.startswith("factory_release_reports?"):
                return [report()]
            return []
        queue._get=getter
        source={"manifest":manifest(),
            "state_snapshot":{"summary":"Release reconciled","evidence":[{"type":"human_release"}]}}
        out=queue._reconciliation_context(P,source)
        evidence=out["current_state_facts"]["global_product_readiness"]
        self.assertEqual(evidence["status"],"not_assessed")
        self.assertFalse(evidence["ready"])
        self.assertIn("factory_release_reports?",str(inspected))
        self.assertNotIn("private_user_prompt",str(out))

    def test_admission_idle_reports_global_audit_not_fake_worker(self):
        readiness=summarize_released_product(project_id=P,run_id=R,merge_sha=M,report_rows=[report()])
        base=dict(project={"id":P,"project_key":"demo","is_active":True,
                           "lifecycle_stage":"operations"},
            control={"project_id":P,"state":"running","version":1,"generation":1},
            commands=[],tasks=[],runs=[],run_id=None,
            cost={"state":"available","reason":"within_budget"},
            planned=[],portfolio=[],readiness=readiness)
        out=classify(**base)
        self.assertEqual(out["reason_code"],"idle_with_unassessed_global_product_readiness")
        self.assertEqual(out["next_step"],"global_product_readiness_audit")
        self.assertEqual(out["status"],"waiting")
        self.assertFalse(out["evidence"]["product_readiness"]["ready"])
        no_release=classify(**{**base,"readiness":None})
        self.assertEqual(no_release["reason_code"],"no_start_or_bootstrap")
        paused=classify(**{**base,"control":{"project_id":P,"state":"paused"}})
        self.assertEqual(paused["reason_code"],"project_paused")

if __name__=="__main__":
    unittest.main()
