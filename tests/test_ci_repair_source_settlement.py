"""No API calls in tests; the migration is exercised in disposable PG separately."""
from __future__ import annotations

import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from ai_product_factory.ci_repair_source_settlement import settle_terminal_ci_repair_sources


class TerminalRepairSettlementTests(unittest.TestCase):
    def setUp(self):
        self.cfg = patch(
            "ai_product_factory.ci_repair_source_settlement.resolve_supabase_server_config",
            return_value=type("Config", (), {"url": "https://broker.example",
                "headers": {"apikey": "masked"}})(),
        )
        self.cfg.start()
        self.addCleanup(self.cfg.stop)

    def test_bounded_service_role_rpc_accepts_only_exact_receipt(self):
        calls = []
        def post(url, payload, headers):
            calls.append((url, payload, headers))
            return 200, {"status": "settled", "settled": 1, "max_items": 3,
                         "paid_model_calls": 0, "release_authorized": False}
        result = settle_terminal_ci_repair_sources(post=post)
        self.assertEqual(result["settled"], 1)
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0][0].endswith(
            "/rpc/factory_settle_terminal_ci_repair_sources_v1"))
        self.assertEqual(calls[0][1], {"p_max_items": 3})
        self.assertEqual(calls[0][2]["apikey"], "masked")

    def test_empty_receipt_is_idempotent(self):
        receipt = settle_terminal_ci_repair_sources(
            max_items=2, post=lambda *_: (200, {
                "status": "idle", "settled": 0, "max_items": 2,
                "paid_model_calls": 0, "release_authorized": False,
            }))
        self.assertEqual(receipt["status"], "idle")

    def test_invalid_limits_and_receipts_fail_closed(self):
        for count in (0, 5, -1, True, 2.4, "3"):
            with self.subTest(count=count), self.assertRaises(ValueError):
                settle_terminal_ci_repair_sources(max_items=count, post=lambda *_: self.fail("called"))
        for receipt in (
            {"status": "settled", "settled": 0, "max_items": 3,
             "paid_model_calls": 0, "release_authorized": False},
            {"status": "settled", "settled": 4, "max_items": 3,
             "paid_model_calls": 0, "release_authorized": False},
            {"status": "settled", "settled": True, "max_items": 3,
             "paid_model_calls": 0, "release_authorized": False},
            {"status": "settled", "settled": 1, "max_items": 3,
             "paid_model_calls": 1, "release_authorized": False},
            {"status": "settled", "settled": 1, "max_items": 3,
             "paid_model_calls": 0, "release_authorized": True},
        ):
            with self.subTest(receipt=receipt), self.assertRaises(RuntimeError):
                settle_terminal_ci_repair_sources(post=lambda *_: (200, receipt))

    def test_unapplied_migration_does_not_mutate_or_claim_success(self):
        def missing(*_):
            raise HTTPError("https://broker.example", 404, "missing",
                            None, io.BytesIO(b'{"code":"PGRST202"}'))
        result = settle_terminal_ci_repair_sources(post=missing)
        self.assertEqual(result["status"], "blocked_migration_not_applied")
        self.assertEqual(result["settled"], 0)
        self.assertIs(result["release_authorized"], False)

    def test_unrelated_404_must_not_impersonate_missing_migration(self):
        def denied(*_):
            raise HTTPError("https://broker.example", 404, "hidden",
                            None, io.BytesIO(b'{"code":"OTHER"}'))
        with self.assertRaisesRegex(RuntimeError, "HTTP 404"):
            settle_terminal_ci_repair_sources(post=denied)

    def test_sql_guards_and_operator_gate_are_explicit(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / "supabase/migrations/"
                "20261024162500_settle_terminal_ci_repair_sources.sql").read_text()
        workflow = (root / ".github/workflows/autonomous-runner.yml").read_text()
        for required in (
            "security invoker", "repair.status = 'passed'", "cs.status = 'completed'",
            "release_run.status = 'integrated'", "source.status = 'repair_pending'",
            "control.generation = repair.execution_generation",
            "source.metadata->>'ci_repair_request_id' = repair.id::text",
            "source.candidate_commit = repair.original_candidate_commit",
            "cs.candidate_commit = repair.repaired_commit",
            "task.status = 'completed'", "source.lease_owner is null",
            "for update of", "skip locked",
            "ci.repair.source_terminal_settled",
            "from public, anon, authenticated", "to service_role",
            "'release_authorized', false", "'paid_model_calls', 0",
        ):
            self.assertIn(required, text)
        self.assertNotIn("security definer", text)
        self.assertNotIn("update public.factory_change_sets", text)
        self.assertNotIn("update public.factory_projects", text)
        self.assertIn("python scripts/settle_terminal_ci_repairs.py --max-items 3", workflow)
        self.assertNotIn("crm-infodive", workflow.split("Settle proven terminal CI repair")[1]
                         .split("- name: Reconcile up to three")[0])


if __name__ == "__main__":
    unittest.main()
