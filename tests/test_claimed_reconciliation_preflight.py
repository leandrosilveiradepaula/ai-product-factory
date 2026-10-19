"""Regression: a claimed reconciliation fails durably before stage execution."""
import unittest
from unittest.mock import Mock

from ai_product_factory.supabase_runtime_queue import SupabaseRuntimeQueue


CLAIM = {
    "run_id": "run-crm", "task_id": "task-crm", "project_id": "project-crm",
    "project_key": "crm-infodive",
    "stages": ["reconciliation", "gap_analysis", "planning"],
    "context": {"manifest": {"reconcile_first": True}},
    "execution_generation": 3,
}


class ClaimedReconciliationPreflightTests(unittest.TestCase):
    def make_queue(self, *, revoked=False, finish_error=False):
        queue = SupabaseRuntimeQueue(
            url="https://example.supabase.co", service_role_key="example"
        )
        calls = []

        def rpc(name, payload):
            calls.append((name, payload))
            if name == "factory_claim_next_run":
                return dict(CLAIM)
            if name == "factory_assert_claimed_run_epoch":
                if revoked:
                    raise RuntimeError("execution generation revoked")
                return None
            if name == "factory_finish_run":
                if finish_error:
                    raise RuntimeError("terminal RPC unavailable")
                return None
            raise AssertionError("unexpected RPC " + name)

        queue._rpc = rpc
        queue._reconciliation_context = lambda project, context: context
        return queue, calls

    def test_stale_sha_settles_claim_before_any_stage(self):
        queue, calls = self.make_queue()
        queue._live_candidate_context = Mock(side_effect=PermissionError(
            "candidate branch moved; reconcile exact SHA before writing"
        ))
        with self.assertRaisesRegex(PermissionError, "candidate branch moved"):
            queue.claim_next("worker")
        self.assertEqual([name for name, _ in calls], [
            "factory_claim_next_run", "factory_assert_claimed_run_epoch",
            "factory_finish_run",
        ])
        self.assertEqual(calls[1][1], {
            "p_project_id": "project-crm", "p_generation": 3,
            "p_run_id": "run-crm", "p_worker_id": "worker",
        })
        self.assertEqual(calls[2][1], {
            "p_run_id": "run-crm", "p_status": "failed",
            "p_error": "reconciliation_source_candidate_sha_drift",
        })
        queue._live_candidate_context.assert_called_once()

    def test_other_source_error_is_redacted_before_storage(self):
        queue, calls = self.make_queue()
        queue._live_candidate_context = Mock(
            side_effect=PermissionError("untrusted provider error: private-value")
        )
        with self.assertRaises(PermissionError):
            queue.claim_next("worker")
        self.assertEqual(calls[-1][1]["p_error"],
                         "reconciliation_context_preflight_failed")
        self.assertNotIn("private-value", repr(calls[-1][1]))

    def test_historical_context_error_stops_before_live_github(self):
        queue, calls = self.make_queue()
        queue._reconciliation_context = Mock(
            side_effect=RuntimeError("snapshot read unavailable")
        )
        queue._live_candidate_context = Mock()
        with self.assertRaisesRegex(RuntimeError, "snapshot read unavailable"):
            queue.claim_next("worker")
        queue._live_candidate_context.assert_not_called()
        self.assertEqual([name for name, _ in calls], [
            "factory_claim_next_run", "factory_assert_claimed_run_epoch",
            "factory_finish_run",
        ])
        self.assertEqual(calls[-1][1]["p_status"], "failed")

    def test_revoked_epoch_prevents_terminal_write(self):
        queue, calls = self.make_queue(revoked=True)
        queue._live_candidate_context = Mock(side_effect=PermissionError("ref moved"))
        with self.assertRaisesRegex(RuntimeError, "settlement was not confirmed"):
            queue.claim_next("worker")
        self.assertEqual([name for name, _ in calls], [
            "factory_claim_next_run", "factory_assert_claimed_run_epoch",
        ])

    def test_terminal_rpc_failure_does_not_look_successful(self):
        queue, calls = self.make_queue(finish_error=True)
        queue._live_candidate_context = Mock(side_effect=RuntimeError("source failure"))
        with self.assertRaisesRegex(RuntimeError, "settlement was not confirmed"):
            queue.claim_next("worker")
        self.assertEqual(calls[-1][0], "factory_finish_run")

    def test_unrelated_claim_does_not_trigger_preflight(self):
        queue, calls = self.make_queue()
        queue._rpc = lambda name, payload: (
            {**CLAIM, "project_key": "greenfield", "stages": ["planning"]}
            if name == "factory_claim_next_run" else self.fail("unexpected RPC")
        )
        queue._live_candidate_context = Mock()
        item = queue.claim_next("worker")
        self.assertEqual(item.stages, ("planning",))
        queue._live_candidate_context.assert_not_called()
        self.assertEqual(calls, [])

    def test_good_candidate_returns_to_worker_without_settlement(self):
        queue, calls = self.make_queue()
        queue._live_candidate_context = Mock(
            side_effect=lambda project, context: {**context, "verified": True}
        )
        item = queue.claim_next("worker")
        self.assertEqual(item.execution_generation, 3)
        self.assertTrue(item.context["verified"])
        self.assertEqual([name for name, _ in calls], ["factory_claim_next_run"])


if __name__ == "__main__":
    unittest.main()
