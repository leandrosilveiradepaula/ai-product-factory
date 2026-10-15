from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
CONTROL=ROOT/"apps"/"console"/"lib"/"control-plane.ts"
PAGE=ROOT/"apps"/"console"/"app"/"projects"/"[key]"/"page.tsx"

class ConsoleProductReadinessTests(unittest.TestCase):
 def test_control_plane_loads_latest_global_readiness(self):
  text=CONTROL.read_text()
  self.assertIn("eval_type=eq.product_readiness",text)
  self.assertIn("order=created_at.desc&limit=1",text)
  self.assertIn("assessedCommit",text)
  self.assertIn("verification_state",text)
  self.assertIn("coverage",text)

 def test_ready_requires_passed_status_and_exact_baseline(self):
  text=CONTROL.read_text()
  self.assertIn('result.ready===true&&result.status==="passed"',text)
  self.assertIn('assessedCommit===String(row.baseline_ref||"")',text)
  self.assertIn('ready:verifiedProductReadinessAssessment(row,result,assessedCommit)',text)
  self.assertIn('row.status==="passed"',text)
  self.assertIn('Array.isArray(result.blockers) && result.blockers.length===0',text)
  self.assertIn('/^[0-9a-f]{40}$/i.test(String(assessedCommit))',text)

 def test_all_six_domain_coverage_and_evidence_are_checked_fail_closed(self):
  text=CONTROL.read_text()
  for value in ('authn_authz','data_access_boundaries','secrets_dependencies',
   'health','traceability','recovery_alerting','unit_integration','critical_e2e',
   'regression_gates','surface_inventory','responsive','accessibility','states',
   'setup_configuration','operations','release_rollback','requirements_inventory',
   'mock_noop_demo_inventory','critical_journeys'):
   with self.subTest(value=value):self.assertIn(value,text)
  self.assertIn('verifiedProductReadinessDomains(result.domains)',text)
  self.assertIn('domain.status==="not_applicable"',text)
  self.assertIn('key==="product_experience"',text)
  self.assertIn('domain.reason.trim().length>0',text)
  self.assertIn('!domain.evidence.every(x=>typeof x==="string"&&x.trim().length>0)',text)
  self.assertIn('return required.every(k=>coverage.has(k))',text)

 def test_assessment_pass_never_claims_current_head_or_release(self):
  page=PAGE.read_text()
  self.assertIn('Auditoria aprovada',page)
  self.assertIn('Isso não comprova que o HEAD atual permanece igual nem libera produção',page)
  self.assertNotIn('label={p.productReadiness.ready?"Produto pronto"',page)

 def test_project_page_does_not_infer_product_ready_from_local_delivery(self):
  text=PAGE.read_text()
  self.assertIn('id="product-readiness"',text)
  self.assertIn("Produto não pronto",text)
  self.assertIn("A Factory não infere prontidão a partir de CI, Preview, release ou ausência de issues",text)
  self.assertIn("verification_state",text)
  self.assertIn("coverage",text)

if __name__=="__main__":
 unittest.main()
