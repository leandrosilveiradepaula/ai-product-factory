"""UX reconciliation: real proof vs declared stage, role of each menu page."""
from pathlib import Path
import re
import unittest
R=Path(__file__).resolve().parents[1]
APP=R/"apps/console/app"
STATUS=(R/"apps/console/lib/product-status.ts").read_text(encoding="utf-8")
PROOF=(R/"apps/console/lib/product-evidence.ts").read_text(encoding="utf-8")
JOURNEY=(R/"apps/console/lib/product-journey.ts").read_text(encoding="utf-8")
CARD=(APP/"product-situation-card.tsx").read_text(encoding="utf-8")
RUN=(APP/"runs/[id]/page.tsx").read_text(encoding="utf-8")
NAV=(APP/"nav.tsx").read_text(encoding="utf-8")
SHELL=(APP/"shell.tsx").read_text(encoding="utf-8")
HOME=(APP/"page.tsx").read_text(encoding="utf-8")
PROJECTS=(APP/"projects/page.tsx").read_text(encoding="utf-8")
CI=(R/".github/workflows/console.yml").read_text(encoding="utf-8")
class TruthAndNavigationTests(unittest.TestCase):
 def test_all_project_types_resolve_by_source_not_name_or_hardcoded_customer(self):
  for table in ('factory_release_reports','factory_deployments','factory_product_readiness_certifications','factory_product_specs','factory_runs','factory_projects'):
   self.assertIn(table,STATUS)
  self.assertIn('isInternalRecord=manifest.qa_canary===true',STATUS)
  self.assertIn('asObject(report.product_readiness)',STATUS)
  self.assertIn('assessProductProof',STATUS)
  self.assertIn('cache:"no-store"',STATUS)
  self.assertIn("Inventário de produto excedeu o limite seguro",STATUS)
  self.assertNotIn('dark-channel-studio',STATUS)
  self.assertNotIn('dark-channel-studio',PROOF)
 def test_never_promote_merge_preview_or_lifecycle_stage_to_product_ready(self):
  self.assertIn('input.definitionReady===true&&matchingCert&&production',PROOF)
  self.assertIn('complete===false||ready===false',PROOF)
  self.assertNotIn('input.lifecycle_stage',PROOF)
  self.assertIn('phaseIndex===PRODUCT_PHASES.length-1&&item.proof?.productReady!==true',JOURNEY)
  self.assertIn('Comprovar entrega funcional',JOURNEY)
  self.assertIn('Não significa que as fases anteriores tenham sido concluídas',CARD)
  self.assertIn('Entrega completa não certificada',CARD)
  self.assertIn('compact=false',CARD)
  self.assertIn('compact/>',HOME)
  self.assertIn('compact/>',PROJECTS)
 def test_run_page_has_no_fake_completion_marks_when_blocked(self):
  self.assertIn('interrupted=["failed","blocked","failed_gate","dead_letter"]',RUN)
  self.assertIn('Execução interrompida; produto não concluído',RUN)
  self.assertNotIn('index<current?"runStage done"',RUN)
  self.assertNotIn('concluída":"aguardando"',RUN)
  self.assertIn('conclusão não comprovada',RUN)
 def test_every_visible_sidebar_destination_has_a_page_and_purpose(self):
  primary=NAV.split('const primaryItems=[',1)[1].split('];',1)[0]
  advanced=NAV.split('const advancedGroups=[',1)[1].split('];',1)[0]
  for href in re.findall(r'href:"([^"]+)"',primary+advanced):
   self.assertTrue(href.startswith('/'),href)
   dest=APP/(href.strip('/')+"/page.tsx" if href!="/" else "page.tsx")
   self.assertTrue(dest.is_file(),str(dest))
  self.assertEqual(len(re.findall(r'hint:"',primary+advanced)),14)
  self.assertIn('navItemHint',NAV)
  self.assertIn('PARA QUE SERVE ESTA PÁGINA',SHELL)
  self.assertIn('ÁREA TÉCNICA',SHELL)
 def test_technical_navigation_is_not_a_product_ready_claim(self):
  for page in ('deployments','evals','agents','queue'):
   src=(APP/page/"page.tsx").read_text(encoding='utf-8')
   self.assertNotIn('ambientes saudáveis',src)
   self.assertNotIn('quality gate limpo',src)
  self.assertIn('test_console_product_evidence_runtime.cjs',CI)
if __name__=="__main__":unittest.main()
