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

 def test_project_page_does_not_infer_product_ready_from_local_delivery(self):
  text=PAGE.read_text()
  self.assertIn('id="product-readiness"',text)
  self.assertIn("Produto não pronto",text)
  self.assertIn("A Factory não infere prontidão a partir de CI, Preview, release ou ausência de issues",text)
  self.assertIn("verification_state",text)
  self.assertIn("coverage",text)

if __name__=="__main__":
 unittest.main()
