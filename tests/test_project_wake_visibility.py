from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
CONTROL=(ROOT/"apps/console/lib/control-plane.ts").read_text()
PAGE=(ROOT/"apps/console/app/projects/[key]/page.tsx").read_text()

class Tests(unittest.TestCase):
 def test_pending_run_is_durable_not_claimed(self):
  self.assertIn("select=id,status,attempt_count,created_at,started_at",CONTROL)
  self.assertIn('x.status==="created"&&x.started_at==null',CONTROL)
  self.assertIn("pendingRun",CONTROL)
 def test_wake_and_probe_evidence_are_independent(self):
  self.assertIn("project.bootstrap.wake_attempted",CONTROL)
  self.assertIn("schedule_probe.observed",CONTROL)
  self.assertIn("schedule_probe.native_observed",CONTROL)
  self.assertIn("productQueueDetected",CONTROL)
  self.assertIn("Aguardando execução",PAGE)
  self.assertIn("não confirma que esta execução foi assumida",PAGE)
 def test_no_paid_or_merge_bypass(self):
  self.assertNotIn("FACTORY_PRIMARY_MODEL_ENABLED=true",PAGE)
  self.assertNotIn("merge_pull_request",PAGE)

if __name__=="__main__":unittest.main()
