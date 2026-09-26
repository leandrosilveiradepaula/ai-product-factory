import unittest
from ai_product_factory.browser_evidence import BrowserEvidence,require_browser_evidence
class Tests(unittest.TestCase):
 def test_success_is_accepted(self):self.assertEqual(require_browser_evidence(BrowserEvidence("success","https://preview.example",("page_load",))).status,"success")
 def test_failure_is_rejected(self):
  with self.assertRaises(ValueError):require_browser_evidence(BrowserEvidence("failure","https://preview.example"))
 def test_invalid_url_is_rejected(self):
  with self.assertRaises(ValueError):require_browser_evidence(BrowserEvidence("success","javascript:alert(1)"))
if __name__=="__main__":unittest.main()
