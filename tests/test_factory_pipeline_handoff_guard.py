"""Fail-closed regressions for deterministic handoff after a partial Actions failure.

No external API, paid model, GitHub side effect or real database mutation.
"""
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from ai_product_factory.schedule_probe import SupabaseScheduleProbe

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/autonomous-runner.yml").read_text()
SQL = (ROOT / "supabase/migrations/20261019193000_guard_stale_change_set_integration.sql").read_text()
CLI = (ROOT / "src/ai_product_factory/runtime_cli.py").read_text()


def condition(name):
    section = WORKFLOW.split("\n  " + name + ":\n", 1)[1]
    return section.split("\n    if: ", 1)[1].split("\n", 1)[0]


class HandoffTests(unittest.TestCase):
    def test_completed_work_unit_must_progress_even_if_direct_or_codex_job_failed(self):
        c = condition("change-set-integration")
        for route in ("direct", "codex"):
            self.assertIn("needs." + route + ".result == 'failure'", c)
            self.assertIn("needs." + route + ".result == 'success'", c)
            self.assertNotIn("needs." + route + ".result != 'failure'", c)
        self.assertIn("always()", c)
        self.assertIn("needs.schedule-probe.result == 'success'", c)
        self.assertEqual(c.count("("), c.count(")"))

    def test_ci_and_dispatch_do_not_drop_committed_followup_after_failed_jobs(self):
        ci = condition("ci-followup")
        dispatch = condition("dispatch")
        self.assertIn("needs.change-set-integration.result == 'failure'", ci)
        self.assertIn("needs.schedule-probe.outputs.ci_work == 'true'", ci)
        self.assertNotIn("needs.change-set-integration.result != 'failure'", ci)
        self.assertIn("needs.product-stage.result == 'failure'", dispatch)
        self.assertIn("needs.schedule-probe.outputs.dispatch_work == 'true'", dispatch)
        self.assertNotIn("needs.product-stage.result != 'failure'", dispatch)
        for c in (ci, dispatch):
            self.assertEqual(c.count("("), c.count(")"))
            self.assertIn("needs.schedule-probe.result == 'success'", c)

    def test_github_handoff_preserves_durable_claims_and_no_model_call(self):
        self.assertIn("store.require_epoch_mutation_ready()", CLI)
        self.assertIn("item=store.claim_integration(worker_id)", CLI)
        self.assertIn('if item is None:return {"claimed":False,"status":"empty"}', CLI)
        for marker in ("--mode change-set-integration --batch-items 3", "--mode ci"):
            self.assertIn(marker, WORKFLOW)
        self.assertNotIn("gh pr merge", WORKFLOW)

    def test_exact_source_pins_and_completed_waves_are_checked_in_both_sql_paths(self):
        signal, claim = SQL.split(
            "CREATE OR REPLACE FUNCTION public.factory_claim_change_set_integration", 1
        )
        self.assertIn("'stale_integration_change_sets'", signal)
        for src, alias in ((signal, "cs"), (claim, "s")):
            with self.subTest(alias=alias):
                for check in (
                    "p.is_active=true",
                    "p.project_kind<>'existing'",
                    "p.manifest->'delivery_target'->>'sha'=" + alias + ".source_commit",
                    "p.manifest->'delivery_target'->>'branch' like 'preview/%'",
                    "p.manifest->'delivery_target'->>'repository'=p.repository",
                    "u.status<>'completed'",
                    alias + ".attempt_count<3",
                ):
                    self.assertIn(check, src)
        self.assertIn("c.state='running'", signal)
        self.assertIn("c.state='running'", claim)
        self.assertEqual(SQL.lower().count("create or replace function"), 2)
        self.assertEqual(SQL.lower().count("grant execute on function"), 2)
        self.assertIn("security invoker", SQL.lower())
        self.assertNotIn("update public.factory_change_sets", SQL.lower())
        self.assertNotIn("delete from public.factory_change_sets", SQL.lower())


class ProbeEvidenceTests(unittest.TestCase):
    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return json.dumps(self.payload).encode()

    def probe(self):
        p = SupabaseScheduleProbe.__new__(SupabaseScheduleProbe)
        p.url = "https://example.invalid"
        p.headers = {"apikey": "placeholder"}
        return p

    def payload(self):
        return {name: False for name in (
            "product_work", "routed_execution_work", "codex_manual_work",
            "integration_work", "ci_work", "release_work",
            "specialist_security_work", "specialist_qa_work",
            "specialist_operations_work"
        )}

    def test_stale_status_is_not_runnable_work(self):
        p = self.probe()
        payload = {**self.payload(), "stale_integration_change_sets": 2}
        with patch("ai_product_factory.schedule_probe.urllib.request.urlopen",
                   return_value=self.FakeResponse(payload)):
            signals = p._execution_signals()
        self.assertEqual(signals["stale_integration_change_sets"], 2)
        with (
            patch.object(p, "_status_partitioned_rows", return_value=([], ())),
            patch.object(p, "_execution_signals", return_value=signals),
            patch.object(p, "_get", return_value=[]),
            patch.object(p, "_get_optional", return_value=[]),
            patch.object(p, "_portfolio_dispatch_candidates", return_value=[]),
            patch.object(p, "_record_telemetry", return_value=True),
        ):
            result = p.probe()
        self.assertFalse(result["work_detected"])
        self.assertEqual(result["queue_diagnostics"]["stale_integration_change_sets"], 2)

    def test_old_rpc_status_is_unknown_and_invalid_counts_fail_closed(self):
        p = self.probe()
        with patch("ai_product_factory.schedule_probe.urllib.request.urlopen",
                   return_value=self.FakeResponse(self.payload())):
            self.assertIsNone(p._execution_signals()["stale_integration_change_sets"])
        for bad in (-1, True, "2", 0.25, []):
            with self.subTest(bad=bad):
                with patch("ai_product_factory.schedule_probe.urllib.request.urlopen",
                           return_value=self.FakeResponse({
                               **self.payload(), "stale_integration_change_sets": bad,
                           })):
                    with self.assertRaisesRegex(RuntimeError, "invalid stale Change Set diagnostic"):
                        p._execution_signals()


if __name__ == "__main__":
    unittest.main()
