"""No-model Product Stage readiness and durable per-run audit regression tests."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock,patch

from ai_product_factory.product_worker_readiness import (
    primary_readiness_blocker, record_product_worker_readiness,
)

NOW = datetime(2026, 10, 15, 17, 0, tzinfo=timezone.utc)
RUN = "9fc6f1d2-2bd7-44b8-88ea-27db5a2d1695"
TASK = "642c83f7-6544-44cb-9325-7cedc1f5646a"
PROJECT = "70515123-ecbb-4f4b-a38f-75c54250af56"
READY = {
    "FACTORY_PRIMARY_MODEL_ENABLED": "true",
    "FACTORY_PRIMARY_AUTH_MODE": "api_key",
    "OPENAI_API_KEY": "NEVER_LOG_THIS_VALUE",
}
CANDIDATE = {"run_id": RUN, "task_id": TASK, "project_id": PROJECT}


class FakeAudit:
    def __init__(self, prior=None, pending=True):
        self.prior, self.pending = prior, pending
        self.events = []
        self.candidates = [CANDIDATE]
        self.reads = 0

    def pending_candidates(self):
        self.reads += 1
        return self.candidates

    def last_blocker(self, run_id):
        assert run_id == RUN
        return self.prior

    def still_pending(self, candidate):
        return self.pending

    def record(self, candidate, reason, workflow_id):
        self.events.append((candidate, reason, workflow_id))


class ProductWorkerReadinessTests(unittest.TestCase):
    def setUp(self):
        self.policy=SimpleNamespace(budget_usd=Decimal("10"),reserve_usd=Decimal("0.50"),version=1)
        self.policy_patch=patch(
            "ai_product_factory.product_worker_readiness.SupabasePrimaryCostPolicyReader",
            return_value=SimpleNamespace(read=lambda:self.policy),
        )
        self.policy_patch.start()
        self.addCleanup(self.policy_patch.stop)

    def test_flag_disabled_blocks_before_auth_or_cost_reader(self):
        reader = MagicMock()
        self.assertEqual(primary_readiness_blocker(
            {**READY, "FACTORY_PRIMARY_MODEL_ENABLED": "false"}, health_reader=reader
        ), "model_disabled")
        reader.read.assert_not_called()

    def test_missing_auth_or_partial_wif_blocks(self):
        self.assertEqual(primary_readiness_blocker(
            {**READY, "OPENAI_API_KEY": ""}
        ), "primary_auth_missing")
        self.assertEqual(primary_readiness_blocker({
            **READY, "FACTORY_PRIMARY_AUTH_MODE": "auto",
            "OPENAI_IDENTITY_PROVIDER_ID": "partial",
        }), "primary_auth_missing")

    def test_missing_invalid_or_unavailable_policy_blocks(self):
        with patch(
            "ai_product_factory.product_worker_readiness.SupabasePrimaryCostPolicyReader",
            return_value=SimpleNamespace(read=MagicMock(side_effect=RuntimeError("policy unavailable"))),
        ):
            self.assertEqual(primary_readiness_blocker(READY), "budget_not_configured")

    def test_unknown_cost_is_blocked(self):
        reader = MagicMock()
        reader.read.return_value = SimpleNamespace(
            known_cost=Decimal("1"), unknown_cost_events=1
        )
        self.assertEqual(primary_readiness_blocker(READY, health_reader=reader), "paid_cost_unknown")
        reader.read.assert_called_once_with(budget=Decimal("10"))

    def test_insufficient_reserve_is_blocked(self):
        reader = MagicMock()
        reader.read.return_value = SimpleNamespace(
            known_cost=Decimal("9.75"), unknown_cost_events=0
        )
        self.assertEqual(primary_readiness_blocker(READY, health_reader=reader), "budget_exhausted")

    def test_unavailable_ledger_is_not_reported_as_ready(self):
        reader = MagicMock()
        reader.read.side_effect = RuntimeError("provider failure")
        self.assertEqual(primary_readiness_blocker(READY, health_reader=reader), "cost_ledger_unavailable")

    def test_readiness_does_not_touch_audit_or_model(self):
        reader = MagicMock()
        reader.read.return_value = SimpleNamespace(
            known_cost=Decimal("3.3167792"), unknown_cost_events=0
        )
        audit = FakeAudit()
        result = record_product_worker_readiness(env=READY, health_reader=reader, audit=audit)
        self.assertEqual(result["status"], "ready")
        self.assertTrue(result["ready"])
        self.assertEqual(audit.reads, 0)
        self.assertFalse(audit.events)

    def test_disabled_writes_existing_run_identity_not_sensitive_config(self):
        audit = FakeAudit()
        env = {**READY, "FACTORY_PRIMARY_MODEL_ENABLED": "false", "GITHUB_RUN_ID": "1234567"}
        result = record_product_worker_readiness(env=env, audit=audit, now=NOW)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["recorded"], 1)
        self.assertEqual(audit.events, [(CANDIDATE, "model_disabled", "1234567")])
        self.assertNotIn(READY["OPENAI_API_KEY"], repr(result) + repr(audit.events))

    def test_repeated_reason_in_window_is_deduplicated(self):
        audit = FakeAudit(prior=("model_disabled", NOW - timedelta(minutes=5)))
        result = record_product_worker_readiness(
            env={**READY, "FACTORY_PRIMARY_MODEL_ENABLED": "false"}, audit=audit, now=NOW
        )
        self.assertEqual(result["deduplicated"], 1)
        self.assertFalse(audit.events)

    def test_changed_reason_writes_new_event(self):
        audit = FakeAudit(prior=("primary_auth_missing", NOW - timedelta(seconds=5)))
        result = record_product_worker_readiness(
            env={**READY, "FACTORY_PRIMARY_MODEL_ENABLED": "false"}, audit=audit, now=NOW
        )
        self.assertEqual(result["recorded"], 1)
        self.assertEqual(audit.events[0][1], "model_disabled")

    def test_claimed_run_never_receives_new_blocker(self):
        audit = FakeAudit(pending=False)
        result = record_product_worker_readiness(
            env={**READY, "FACTORY_PRIMARY_MODEL_ENABLED": "false"}, audit=audit, now=NOW
        )
        self.assertEqual(result["superseded"], 1)
        self.assertFalse(audit.events)

    def test_failed_audit_fails_closed(self):
        audit = FakeAudit()
        audit.record = MagicMock(side_effect=RuntimeError("Supabase down"))
        with self.assertRaisesRegex(RuntimeError, "Supabase down"):
            record_product_worker_readiness(
                env={**READY, "FACTORY_PRIMARY_MODEL_ENABLED": "false"},
                audit=audit, now=NOW,
            )

    def test_actions_step_must_precede_and_gate_paid_worker(self):
        root = Path(__file__).resolve().parents[1]
        flow = (root / ".github/workflows/autonomous-runner.yml").read_text()
        cli = (root / "src/ai_product_factory/runtime_cli.py").read_text()
        self.assertIn("--mode product-readiness-evidence", flow)
        self.assertIn("steps.product_readiness_evidence.outputs.ready == 'true'", flow)
        self.assertIn('elif args.mode=="product-readiness-evidence"', cli)
        self.assertNotIn("model.execute(", (
            root / "src/ai_product_factory/product_worker_readiness.py"
        ).read_text())

    def test_console_reads_exact_run_and_shows_portuguese_reason(self):
        root = Path(__file__).resolve().parents[1]
        code = (root / "apps/console/lib/control-plane.ts").read_text()
        page = (root / "apps/console/app/projects/[key]/page.tsx").read_text()
        self.assertIn("event_type=eq.product.worker_blocked", code)
        self.assertIn("run_id=eq.", code)
        self.assertIn("model_disabled", code)
        self.assertIn("Modelo principal desabilitado", page)
        self.assertIn("Bloqueio registrado para esta execução", page)


if __name__ == "__main__":
    unittest.main()
