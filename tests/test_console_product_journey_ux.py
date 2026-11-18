"""UX contract: every product makes the real phase, next phase and next owner visible."""
from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
J=(R/"apps/console/lib/product-journey.ts").read_text(encoding="utf-8")
CARD=(R/"apps/console/app/product-situation-card.tsx").read_text(encoding="utf-8")
PROJECT=(R/"apps/console/app/projects/[key]/page.tsx").read_text(encoding="utf-8")
HOME=(R/"apps/console/app/page.tsx").read_text(encoding="utf-8")
PORTFOLIO=(R/"apps/console/app/projects/page.tsx").read_text(encoding="utf-8")
CSS=(R/"apps/console/app/operator.css").read_text(encoding="utf-8")
CI=(R/".github/workflows/console.yml").read_text(encoding="utf-8")
class ProductJourneyUXTest(unittest.TestCase):
 def test_phase_source_is_deterministic_and_declares_no_pass(self):
  self.assertIn("export const PRODUCT_PHASES=",J)
  for phase in ('Entender','Planejar','Construir','Testar','Publicar','Operar'):
   self.assertIn('label:"'+phase+'"',J)
  self.assertIn("lifecycle_stage",J)
  self.assertNotIn('method:"POST"',J)
  self.assertNotIn("getSupabaseServerConfig",J)
  self.assertNotIn("mergeReadyReleaseFromConsole",J)
 def test_path_always_precedes_technical_diagnostics(self):
  for token in ("Caminho do produto","ETAPA ATUAL","PRÓXIMA FASE","O que falta para avançar:","PRÓXIMO PASSO","Quem age:"):
   self.assertIn(token,CARD)
  self.assertLess(CARD.index('className="journeyPath"'),CARD.index('className="journeyEvidence"'))
  self.assertIn('className="productJourneyTrack"',CARD)
  self.assertIn('aria-current={step.mark==="atual"?"step":undefined}',CARD)
  self.assertIn("showOpen={false}",PROJECT)
  self.assertIn("ProductSituationCard",HOME)
  self.assertIn("ProductSituationCard",PORTFOLIO)
  self.assertIn('details className="projectStageDisclosure"',PROJECT)
  self.assertIn("projectAuxActions",PROJECT)
  self.assertIn("role=\\"group\\"",HOME)
  self.assertIn('details className="productOverviewTechnical"',HOME)
 def test_explicit_action_only_on_authoritative_human_gate(self):
  self.assertIn('item.state==="decision"',J)
  self.assertIn('humanRequired',J)
  self.assertIn('action("Você"',J)
  self.assertIn('state==="stopped"||item.state==="paused"',J)
  self.assertIn("phaseIndex<0",J)
  self.assertIn('unclosedTasks>0',J)
 def test_mobile_journey_readable_without_fake_percentage_or_drag(self):
  for css in (".productJourneyTrack",".journeyStep.atual",".journeyStep.proxima",".journeyPhaseOverview",".journeyAction",".journeyEvidence","@media(max-width:760px)"):
   self.assertIn(css,CSS)
  self.assertNotIn("width:"+str(0)+"%",J)
  self.assertNotIn("draggable",CARD)
  self.assertIn("test_console_product_journey_runtime.cjs",CI)
if __name__=="__main__":unittest.main()
