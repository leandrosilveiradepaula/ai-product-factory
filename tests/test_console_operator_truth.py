"""Owner feedback 18/11: useful facts and next actions, not lifecycle prose."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
S=(ROOT/"apps/console/lib/product-status.ts").read_text()
D=(ROOT/"apps/console/lib/product-diagnosis.ts").read_text()
B=(ROOT/"apps/console/lib/product-blocker.ts").read_text()
C=(ROOT/"apps/console/app/product-situation-card.tsx").read_text()
R=(ROOT/"apps/console/app/runs/[id]/page.tsx").read_text()
P=(ROOT/"apps/console/app/projects/[key]/page.tsx").read_text()
CSS=(ROOT/"apps/console/app/operator.css").read_text()
W=(ROOT/".github/workflows/console.yml").read_text()
class OperatorTruthTests(unittest.TestCase):
 def test_source_bound_and_no_customer_hardcode(self):
  for table in ("factory_project_databases","factory_requirements","factory_runs","factory_release_reports"):
   self.assertIn(table,S)
  self.assertIn("sourceIssue(manifest)",S)
  self.assertIn('cache:"no-store"',S)
  self.assertNotIn('dark-channel-studio',S)
  self.assertNotIn('dark-channel-studio',D)
  self.assertNotIn('dark-channel-studio',B)
  self.assertIn("explainRunBlocker(last.status,last.last_error)",S)
  self.assertNotIn("lastError:last?.last_error",S)
 def test_no_hidden_database_disconnect_or_fake_missing_db(self):
  self.assertIn('id="databases"',P)
  self.assertNotIn('{hasPendingDatabase?<section className="section" id="databases"',P)
  self.assertIn('não significa que o banco não exista',P)
  self.assertIn('Nenhum vínculo registrado (não significa ausência de banco)',D)
  self.assertIn('Banco no inventário da Factory',D)
  self.assertIn("state:\"verified\"|\"pending\"|\"not_recorded\"",S)
 def test_real_blocker_and_plan_visible_first(self):
  self.assertIn('PRÓXIMO TRABALHO',C)
  self.assertIn('O que falta resolver',C)
  self.assertIn('productWorkPlan',C)
  self.assertIn('productWorkStep',C)
  self.assertIn('productTruth',C)
  self.assertIn('productJourneyDisclosure',C)
  self.assertIn('productJourneyDisclosure',CSS)
  self.assertLess(C.index('className="productCompactDetails"'),C.index('className="productJourneyDisclosure"'))
  self.assertIn('runOutcomeHero',R)
  self.assertIn('explainRunBlocker(r.status,r.lastError)',R)
  self.assertLess(R.index('runOutcomeHero'),R.index('runTechnicalDisclosure'))
  self.assertIn('Voltar à situação do produto',R)
  self.assertIn('O produto funciona? O que falta para usar?',P)
 def test_exact_runtime_tests_wired(self):
  self.assertIn('test_console_product_diagnosis_runtime.cjs',W)
  self.assertIn('test_console_operator_truth.py',W)
  self.assertNotIn('method:"POST"',S)
if __name__=="__main__":unittest.main()
