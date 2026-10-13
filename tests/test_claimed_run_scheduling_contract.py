"""Offline contract for no-agent manual Codex and exact-run Direct scheduling."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
WF=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
PY=(ROOT/"src/ai_product_factory/runtime_cli.py").read_text()

class ClaimedRunSchedulingContractTests(unittest.TestCase):
 def test_manual_handoff_wake_is_independent_of_agent_matrix(self):
  dispatch=WF.split("\n  dispatch:\n",1)[1].split("\n  direct:\n",1)[0]
  self.assertIn('route.get("route")=="codex"',dispatch)
  self.assertIn("route.get(\"human_gate_required\") is False",dispatch)
  self.assertIn('out.write("codex_count="+str(len(codex)+handoffs)',dispatch)
  codex=WF.split("\n  codex:\n",1)[1].split("\n  codex-manual:\n",1)[0]
  self.assertIn("vars.FACTORY_CODEX_ENABLED == 'true'",codex)
  manual=WF.split("\n  codex-manual:\n",1)[1].split("\n  preview:\n",1)[0]
  self.assertIn("needs.dispatch.outputs.codex_count",manual)
  self.assertIn("FACTORY_CODEX_MANUAL_FALLBACK_ENABLED == 'true'",manual)

 def test_exact_claimed_run_is_passed_to_agent_scheduler(self):
  body=PY.split("def run_dispatch_once(",1)[1].split("\ndef main(",1)[0]
  self.assertIn('assignment=scheduler.schedule_eligible_direct(',body)
  self.assertIn("run_id=decision.run_id,project_key=project_key",body)
  self.assertNotIn("scheduler.schedule_next()",body)
  self.assertIn('decision.execution.route.value=="codex"',body)
  self.assertIn('if decision.execution.human_gate_required:',body)
  self.assertLess(body.index('if decision.execution.human_gate_required:'),body.index("scheduler.schedule_eligible_direct("))
  self.assertIn("atomic dispatcher did not return a durable run ID",body)

 def test_no_credential_or_production_merge_regression(self):
  dispatch=WF.split("\n  dispatch:\n",1)[1].split("\n  direct:\n",1)[0]
  self.assertNotIn("OPENAI_API_KEY:",dispatch)
  self.assertNotIn("CODEX_ACCESS_TOKEN:",dispatch)
  self.assertNotIn("gh pr merge",WF)
  self.assertNotIn("auto-merge: true",WF)

if __name__=="__main__":
 unittest.main()
