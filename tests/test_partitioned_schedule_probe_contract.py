"""Offline regression: stale rows from one status must never hide another."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
PROBE=(ROOT/"src/ai_product_factory/schedule_probe.py").read_text()
WORKFLOW=(ROOT/".github/workflows/autonomous-runner.yml").read_text()

class StatusPartitionedProbeContractTests(unittest.TestCase):
    def test_no_multi_status_limit_for_active_queue(self):
        self.assertIn("def _status_partitioned_rows(",PROBE)
        self.assertIn("status=eq.{status}",PROBE)
        self.assertNotIn("&status=in.(created,queued,ci_pending,preview_ready,awaiting_release,awaiting_codex_manual)",PROBE)
        self.assertNotIn("&status=in.(queued,queued_execution)&limit=200",PROBE)

    def test_preview_audit_and_queue_can_be_detected_separately(self):
        self.assertIn('("created", "queued", "ci_pending", "preview_ready", "awaiting_release", "awaiting_codex_manual")',PROBE)
        self.assertIn('("queued", "queued_execution")',PROBE)
        self.assertIn('"run_status_partitions_at_limit": list(capped_run_statuses)',PROBE)
        self.assertIn('"task_status_partitions_at_limit": list(capped_task_statuses)',PROBE)
        self.assertIn("is_delivery_preview_run(run)",PROBE)
        self.assertIn("pending_change_set_work and bool(portfolio_candidates)",PROBE)

    def test_no_paid_or_production_release_side_effects(self):
        self.assertNotIn("schedule_next(",PROBE)
        self.assertNotIn("factory_schedule_eligible_direct_run",PROBE)
        self.assertNotIn("OPENAI_API_KEY",PROBE)
        self.assertNotIn("gh pr merge",WORKFLOW)

if __name__=="__main__":
    unittest.main()
