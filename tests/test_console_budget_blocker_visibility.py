"""Regression: blocked planning product run is visible without manual log hunting."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
PROJECT=(ROOT/"apps/console/app/projects/[key]/page.tsx").read_text()
CONTROL=(ROOT/"apps/console/lib/control-plane.ts").read_text()
ATTENTION=(ROOT/"apps/console/app/api/human-attention/route.ts").read_text()

class OperatorBlockerVisibilityTests(unittest.TestCase):
 def test_budget_exhausted_has_a_project_specific_next_action(self):
  self.assertIn("const observedBlocker=p.pendingRun&&p.wakeEvidence?.blockerCode",PROJECT)
  self.assertIn('observedBlocker==="budget_exhausted"?"Execução pausada: limite do modelo atingido"',PROJECT)
  self.assertIn('productWorkerBlockerMessage(observedBlocker)',PROJECT)
  self.assertIn('observedBlocker==="budget_exhausted"?"/usage":"/configuration"',PROJECT)
  self.assertIn('p.stage!=="discovery"&&observedBlocker',PROJECT)
  self.assertIn('A execução <code>{p.pendingRun.id.slice(0,8)}</code>',PROJECT)
  self.assertIn('role="status" aria-live="polite"',PROJECT)
  self.assertIn('href={"/runs/"+p.pendingRun.id}',PROJECT)
  self.assertIn('budget_exhausted:"Saldo do orçamento interno insuficiente',PROJECT)
  self.assertNotIn("FACTORY_MODEL_BUDGET_USD=",PROJECT)

 def test_pending_gate_filter_precedes_latest_100_limit(self):
  self.assertIn("getHumanGates(100,true)",ATTENTION)
  self.assertIn('onlyPending?"&status=eq.pending":""',CONTROL)
  self.assertIn("getGitHubAppStatus()",ATTENTION)
  self.assertIn("githubApp.configured?0:1",ATTENTION)
  self.assertIn('status:"unavailable"',ATTENTION)
  self.assertNotIn("update ",ATTENTION.lower())

if __name__=="__main__":
 unittest.main()
