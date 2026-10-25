"""Fail-closed receipts for bounded repin-context recovery, no external effects."""
from __future__ import annotations

import io
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from ai_product_factory.ci_repair_candidate_recovery import resume_blocked_ci_repair_candidate


class CIRepairCandidateRecoveryTests(unittest.TestCase):
    def setUp(self):
        p = patch(
            "ai_product_factory.ci_repair_candidate_recovery.resolve_supabase_server_config",
            return_value=type("Config", (), {
                "url": "https://broker.example",
                "headers": {"apikey": "redacted"},
            })(),
        )
        p.start()
        self.addCleanup(p.stop)

    @staticmethod
    def valid(count=1, max_items=2):
        return {
            "status": "requeued" if count else "idle",
            "requeued": count, "max_items": max_items,
            "product_stage_replayed": False,
            "release_authorized": False, "paid_model_calls": 0,
        }

    def test_bounded_rpc_and_receipt(self):
        calls = []
        def post(url, body, headers):
            calls.append((url, body, headers))
            return 200, self.valid()
        result = resume_blocked_ci_repair_candidate(post=post)
        self.assertEqual(result["requeued"], 1)
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0][0].endswith(
            "/rpc/factory_resume_blocked_ci_repair_candidate_v1"))
        self.assertEqual(calls[0][1], {"p_max_items": 2})

    def test_empty_replay_is_noop(self):
        self.assertEqual(
            resume_blocked_ci_repair_candidate(
                max_items=2, post=lambda *_: (200, self.valid(0, 2))
            )["status"], "idle"
        )

    def test_boundaries_and_forged_receipts_rejected(self):
        for size in (0, 3, 4, -1, True, 2.5, "2"):
            with self.subTest(size=size), self.assertRaises(ValueError):
                resume_blocked_ci_repair_candidate(max_items=size)
        for receipt in (
            {"status":"requeued","requeued":0,"max_items":2,
             "product_stage_replayed":False,"release_authorized":False,
             "paid_model_calls":0},
            {**self.valid(), "requeued": 3},
            {**self.valid(), "requeued": True},
            {**self.valid(), "paid_model_calls": 1},
            {**self.valid(), "release_authorized": True},
            {**self.valid(), "product_stage_replayed": True},
        ):
            with self.subTest(receipt=receipt):
                if receipt.get("requeued") == 0 and receipt.get("status") == "idle":
                    continue
                with self.assertRaises(RuntimeError):
                    resume_blocked_ci_repair_candidate(post=lambda *_: (200, receipt))

    def test_missing_rpc_fails_closed_without_disabling_scheduler(self):
        def missing(*_):
            raise HTTPError("https://broker.example", 404, "missing",
                            None, io.BytesIO(b'{"code":"PGRST202"}'))
        response = resume_blocked_ci_repair_candidate(post=missing)
        self.assertEqual(response["status"], "blocked_migration_not_applied")
        self.assertEqual(response["requeued"], 0)

    def test_unrelated_404_is_not_missing_migration(self):
        def error(*_):
            raise HTTPError("https://broker.example", 404, "other",
                            None, io.BytesIO(b'{"code":"OTHER"}'))
        with self.assertRaisesRegex(RuntimeError, "HTTP 404"):
            resume_blocked_ci_repair_candidate(post=error)

    def test_source_and_migration_deny_paid_replay_production_and_public(self):
        root = Path(__file__).resolve().parents[1]
        migration = (root / "supabase/migrations/"
                     "20261025010500_resume_blocked_ci_repair_candidate.sql").read_text()
        workflow = (root / ".github/workflows/autonomous-runner.yml").read_text()
        for required in (
            "security invoker", "status='blocked'", "execution_generation",
            "rr.original_candidate_commit", "cs.integration_branch",
            "factory_change_set_work_units", "cs.release_run_id is null",
            "u.output_commit is null", "not exists", "skip locked",
            "factory_audit_events", "change_set.ci_repair_candidate_requeued",
            "rr.status='failed_gate'", "r.status='blocked'",
            "r.execution_route='direct'", "rr.attempt=1",
            "rr.original_candidate_commit", "rr.execution_generation",
            "rr.work_unit_id", "factory_ci_repair_requests",
            "'product_stage_replayed',false", "'release_authorized',false",
            "from public,anon,authenticated", "to service_role",
        ):
            self.assertIn(required, migration)
        self.assertNotIn("security definer", migration)
        self.assertNotIn("update public.factory_projects", migration)
        self.assertIn("python scripts/resume_blocked_ci_repair_candidate.py --max-items 2", workflow)


if __name__ == "__main__":
    unittest.main()
