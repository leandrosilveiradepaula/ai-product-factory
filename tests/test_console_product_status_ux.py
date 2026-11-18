"""Owner UX rejection: product status must reflect actual worker and control state."""
from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
SERVER=(R/"apps/console/lib/product-status.ts").read_text(encoding="utf-8")
CARD=(R/"apps/console/app/product-situation-card.tsx").read_text(encoding="utf-8")
HOME=(R/"apps/console/app/page.tsx").read_text(encoding="utf-8")
PROJECT=(R/"apps/console/app/projects/[key]/page.tsx").read_text(encoding="utf-8")
CI=(R/".github/workflows/console.yml").read_text(encoding="utf-8")
class ProductStatusUXTests(unittest.TestCase):
 def test_real_readonly_sources_and_fail_closed_inventory(self):
  for table in ('"factory_projects"','"factory_project_execution_controls"','"factory_tasks"','"factory_runs"'):
   self.assertIn(table,SERVER)
  self.assertIn("getHumanGates(100,true)",SERVER)
  self.assertIn("requireConsoleOperator()",SERVER)
  self.assertIn('cache:"no-store"',SERVER)
  self.assertIn("Inventário de produto excedeu o limite seguro",SERVER)
  self.assertNotIn('method:"POST"',SERVER)
 def test_stage_is_not_worker_and_status_has_evidence(self):
  self.assertIn("lease_expires_at",SERVER)
  self.assertIn('typeof r.started_at==="string"',SERVER)
  self.assertIn("confirmedRunning",SERVER)
  self.assertIn("latestRun",SERVER)
  self.assertIn("lastRequest",SERVER)
  self.assertIn("humanDecisions",SERVER)
  self.assertIn("Projeto parado",SERVER)
  self.assertIn("Sem execução ativa confirmada",SERVER)
 def test_owner_views_show_real_product_story(self):
  for field in ("O QUE ESTÁ ACONTECENDO","ÚLTIMA SOLICITAÇÃO","ÚLTIMA TENTATIVA","PRÓXIMO TRABALHO"):
   self.assertIn(field,CARD)
  self.assertIn("ProductSituationCard",HOME)
  self.assertIn("getProductSituations",HOME)
  self.assertIn("getProductSituations",PROJECT)
  self.assertIn("test_console_product_status_runtime.cjs",CI)
if __name__=="__main__":unittest.main()
