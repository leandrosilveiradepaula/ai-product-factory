"""Offline contracts for catch-up of a genuinely human-released legacy product."""
from __future__ import annotations

import json
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from ai_product_factory.project_release_reconciliation import (
    LegacyCapabilityUnavailable,
    ReleaseReconciliationRejected,
    SupabaseProjectReleaseReconciler,
)
from ai_product_factory.product_readiness import REQUIRED_DOMAINS

P="11111111-1111-4111-8111-111111111111"
Q="22222222-2222-4222-8222-222222222222"
R="33333333-3333-4333-8333-333333333333"
MERGE="b"*40
ORIG="a"*40
ROOT=Path(__file__).resolve().parents[1]
MIGRATION=(ROOT/"supabase/migrations/20261021135000_recover_latest_legacy_release_readiness.sql").read_text()
ADAPTER=(ROOT/"src/ai_product_factory/project_release_reconciliation.py").read_text()
RUNNER=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
RUNTIME=(ROOT/"src/ai_product_factory/runtime_cli.py").read_text()
POSTGRES=(ROOT/"scripts/verify_atomic_project_release_postgres.py").read_text()


def report():
    return {"project_id":P,"run_id":R,"status":"released",
        "candidate_commit":ORIG,
        "report":{"merge_sha":MERGE,"released_by":"observed_manual_merge",
                  "product_readiness":{"status":"not_assessed","ready":False}}}


def receipt(*,idempotent=False):
    return {"project_id":P,"run_id":R,"merge_sha":MERGE,
        "lifecycle_stage":"operations","product_ready":False,
        "idempotent":idempotent,"snapshot_written":not idempotent,
        "audit_written":False,"change_set_updated":False,
        "change_set_status":"completed","pending_domains":6,
        "legacy_backfill":True,"backfill_audit_written":not idempotent}


def new():
    return object.__new__(SupabaseProjectReleaseReconciler)


class LegacyReleaseReadinessTests(unittest.TestCase):
    def test_versioned_private_rpc_migration_is_only_schema_change(self):
        import re
        names=re.findall(r"CREATE OR REPLACE FUNCTION public\.(factory_[a-z0-9_]+)\(",MIGRATION)
        self.assertEqual(names,[
            "factory_pending_legacy_release_readiness_v1",
            "factory_reconcile_latest_legacy_release_v1",
            "factory_defer_legacy_release_readiness_v1",
        ])
        self.assertEqual(MIGRATION.count("$function$;"),3)
        self.assertTrue(MIGRATION.strip().endswith("COMMIT;"))
        for item in ("SECURITY DEFINER","CREATE POLICY","CREATE TABLE",
                     "DROP TABLE","TRUNCATE","merge_pull_request","OPENAI_API_KEY"):
            self.assertNotIn(item,MIGRATION)
        for sign in ("factory_pending_legacy_release_readiness_v1(uuid,integer)",
                     "factory_reconcile_latest_legacy_release_v1(uuid,uuid,text,jsonb,jsonb)",
                     "factory_defer_legacy_release_readiness_v1(uuid,uuid,text)"):
            self.assertIn("REVOKE ALL ON FUNCTION public."+sign,MIGRATION)
            self.assertIn("GRANT EXECUTE ON FUNCTION public."+sign,MIGRATION)
        self.assertEqual(MIGRATION.count("FROM PUBLIC,anon,authenticated;"),3)
        self.assertEqual(MIGRATION.count("TO service_role;"),3)
        for proof in ("r.status='merged'","rr.status='released'",
                      "release.human_merge_observed","release.legacy_readiness_backfilled",
                      "release.legacy_readiness_needs_review","last_release,run_id",
                      "last_release,merge_sha","r.candidate_commit",
                      "c.state='running'","c.generation>0","FOR SHARE",
                      "FOR UPDATE","newer.updated_at","original_human_merge_only",
                      "public.factory_reconcile_observed_release_v1",
                      "product_ready',false"):
            self.assertIn(proof,MIGRATION)
        self.assertIn("LEGACY_MIGRATION",POSTGRES)
        for case in ("real-pr-997-pattern","paused-readiness-recovery",
                     "invalid-legacy-readiness-candidate",
                     "stale-legacy-readiness-not-replayed",
                     "premature-human-merge-not-a-release"):
            self.assertIn(case,POSTGRES)

    def test_worker_wired_without_new_paid_paths_or_auto_merge(self):
        self.assertIn("def repair_legacy_readiness(",ADAPTER)
        self.assertIn("def run_legacy_release_readiness_repair(",RUNTIME)
        self.assertIn('"legacy-release-readiness-repair"',RUNTIME)
        self.assertIn("--mode legacy-release-readiness-repair --batch-items 4",RUNNER)
        self.assertIn("continue-on-error: true",RUNNER)
        self.assertNotIn("merge_pull_request(",MIGRATION)
        self.assertNotIn("OPENAI_API_KEY",MIGRATION)
        self.assertNotIn('"PATCH"',ADAPTER)

    def test_atomic_reconcile_is_selected_only_for_legacy_mode(self):
        calls=[]
        worker=new()
        def request(method,path,payload=None):
            calls.append((method,path,payload))
            if method=="GET":
                return [report()]
            return receipt()
        worker._request=request
        out=worker.reconcile(project_id=P,run_id=R,merge_sha=MERGE,legacy=True)
        self.assertFalse(out["idempotent"])
        self.assertEqual([x[0] for x in calls],["GET","POST"])
        self.assertEqual(calls[1][1],"rpc/factory_reconcile_latest_legacy_release_v1")
        self.assertEqual(calls[1][2]["p_release_report"],report()["report"])
        self.assertEqual(calls[1][2]["p_followup"]["pending_domains"],list(REQUIRED_DOMAINS))
        self.assertFalse(calls[1][2]["p_followup"]["ready"])
        self.assertTrue(calls[1][2]["p_followup"]["report_verified"])

        calls.clear()
        worker.reconcile(project_id=P,run_id=R,merge_sha=MERGE)
        self.assertEqual(calls[1][1],"rpc/factory_reconcile_observed_release_v1")

    def test_legacy_rpc_receipt_must_identify_atomic_repair(self):
        w=new()
        def bad(method,path,payload=None):
            if method=="GET":
                return [report()]
            return {k:v for k,v in receipt().items()
                    if k not in ("legacy_backfill","backfill_audit_written")}
        w._request=bad
        with self.assertRaisesRegex(RuntimeError,"legacy repair receipt"):
            w.reconcile(project_id=P,run_id=R,merge_sha=MERGE,legacy=True)

    def test_absent_optional_migration_is_explicitly_blocked(self):
        w=SupabaseProjectReleaseReconciler(url="https://example.test",secret_key="sb_secret_test")
        err=urllib.error.HTTPError("https://example.test",404,"function unavailable",{},None)
        with patch("urllib.request.urlopen",side_effect=err):
            self.assertEqual(w.repair_legacy_readiness()["status"],
                             "blocked_migration_not_applied")
        with patch("urllib.request.urlopen",side_effect=err):
            with self.assertRaises(LegacyCapabilityUnavailable):
                w._request("POST","rpc/factory_pending_legacy_release_readiness_v1",
                           {"p_after_project_id":None,"p_limit":16})

    def test_bounded_settlement_is_exact_and_does_not_replay_models(self):
        w=new()
        calls=[]
        def request(method,path,payload=None):
            calls.append((method,path,payload))
            if path.endswith("factory_pending_legacy_release_readiness_v1"):
                return [{"project_id":P,"run_id":R,"merge_sha":MERGE},
                        {"project_id":Q,"run_id":R,"merge_sha":MERGE}]
            self.fail("only read-only candidate selection is expected")
        w._request=request
        seen=[]
        w.reconcile=lambda **kw:(seen.append(kw) or receipt())
        got=w.repair_legacy_readiness(max_items=2)
        self.assertEqual(got["scanned"],2)
        self.assertEqual(got["repaired"],2)
        self.assertTrue(got["truncated"])
        self.assertEqual([x["project_id"] for x in seen],[P,Q])
        self.assertTrue(all(x["legacy"] for x in seen))
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0][2],
            {"p_after_project_id":None,"p_limit":16})

    def test_permanent_failure_is_parked_without_starving_another_project(self):
        w=new()
        calls=[]
        w._request=lambda method,path,payload=None:[
            {"project_id":P,"run_id":R,"merge_sha":MERGE},
            {"project_id":Q,"run_id":R,"merge_sha":MERGE}]
        def reconcile(**kw):
            if kw["project_id"]==P:
                raise ReleaseReconciliationRejected("human release reconciliation rejected")
            return receipt()
        w.reconcile=reconcile
        w._defer_legacy_review=lambda **kw:calls.append(kw)
        result=w.repair_legacy_readiness(max_items=2)
        self.assertEqual(result["repaired"],1)
        self.assertEqual(result["needs_review"],[{
            "project_id":P,"reason":"legacy_release_needs_review"}])
        self.assertEqual(calls,[{"project_id":P,"run_id":R,"merge_sha":MERGE}])

    def test_transient_failure_remains_retryable(self):
        w=new()
        w._request=lambda *a,**k:[{"project_id":P,"run_id":R,"merge_sha":MERGE}]
        w.reconcile=lambda **kw:(_ for _ in ()).throw(RuntimeError("release reconciliation Control Plane unavailable"))
        w._defer_legacy_review=lambda **kw:self.fail("transient failures must not be parked")
        result=w.repair_legacy_readiness(max_items=1)
        self.assertEqual(result["repaired"],0)
        self.assertEqual(result["needs_review"][0]["reason"],"legacy_release_retryable")

    def test_bad_cursor_or_scope_is_rejected_before_effect(self):
        w=new()
        w.reconcile=lambda **kw:self.fail("untrusted selector must not write")
        for rows in ([{"project_id":"bad","run_id":R,"merge_sha":MERGE}],
                     [{"project_id":P,"run_id":R,"merge_sha":"bad"}],
                     [{"project_id":Q,"run_id":R,"merge_sha":MERGE},
                      {"project_id":P,"run_id":R,"merge_sha":MERGE}],
                     "invalid"):
            w._request=lambda *a,**kw:rows
            with self.subTest(rows=rows),self.assertRaises(RuntimeError):
                w.repair_legacy_readiness(max_items=4)

    def test_strict_bounds_reject_bool_or_zero(self):
        w=new()
        w._request=lambda *a,**k:self.fail("invalid limits must not query")
        for invalid in (True,False,0,33,-1,"4"):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                w.repair_legacy_readiness(max_items=invalid)


if __name__=="__main__":
    unittest.main()
