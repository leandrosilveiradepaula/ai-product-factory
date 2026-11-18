"""Owner blocker visibility: a queued continuation must not disappear from UI."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
PROJECT=(ROOT/"apps/console/app/projects/[key]/page.tsx").read_text(encoding="utf-8")
CONTROL=(ROOT/"apps/console/lib/control-plane.ts").read_text(encoding="utf-8")
HOME=(ROOT/"apps/console/app/page.tsx").read_text(encoding="utf-8")
FINANCIAL=(ROOT/"apps/console/lib/owner-financial-blocker.ts").read_text(encoding="utf-8")
ATTENTION=(ROOT/"apps/console/app/api/human-attention/route.ts").read_text(encoding="utf-8")

class OperatorBlockerVisibilityTests(unittest.TestCase):
 def test_queued_and_created_runs_are_both_detected(self):
  self.assertIn('x.status==="created"||x.status==="queued"',CONTROL)
  self.assertIn('status:String(waiting.status)',CONTROL)
  self.assertIn('event_type=eq.product.worker_blocked',CONTROL)
  self.assertIn('created_at=gte.',CONTROL)
  self.assertNotIn('pendingRun={id:String(waiting.id),status:"created"',CONTROL)

 def test_owner_receives_real_budget_notice_and_a_single_cost_action(self):
  for page in (HOME,PROJECT):
   self.assertIn('getPrimaryCostPolicyView()',page)
   self.assertIn('ownerFinancialBlocker(',page)
   self.assertIn('financial.title',page)
   self.assertIn('financial.description',page)
   self.assertIn('financial.actionLabel',page)
  self.assertIn('role="alert" aria-label="Motivo da interrupção"',PROJECT)
  self.assertIn('role="status"',HOME)
  self.assertIn("ownerProgressDetails",PROJECT)
  self.assertIn('getProjectWorkObservation(',PROJECT)
  self.assertIn('workObservation.kind==="running"?"Desenvolvendo":"Aguardando execução"',PROJECT)

 def test_budget_blocker_requires_validated_run_and_live_cost_policy(self):
  for contract in ('budget_exhausted','blockedAt','pending.createdAt',
                   'policy.knownSpendUsd===null','policy.unknownPaidCostEvents>0',
                   'knownSpendUsd+reserveUsd<=budgetUsd',
                   '"Parado por limite financeiro"',
                   '"/configuration"',
                   'A tarefa já está na fila. Não é necessário reiniciar novamente.'):
   self.assertIn(contract,FINANCIAL)
  self.assertNotIn("15.00",FINANCIAL)
  self.assertNotIn("dark-channel-studio",FINANCIAL)

 def test_human_attention_api_remains_separate(self):
  self.assertIn("getHumanGates(100,true)",ATTENTION)
  self.assertIn('onlyPending?"&status=eq.pending":""',CONTROL)
  self.assertNotIn("update ",ATTENTION.lower())
