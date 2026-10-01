from pathlib import Path
import json
import unittest

ROOT=Path(__file__).resolve().parents[1]
POLICY=ROOT/"config/factory.release-policy.v1.json"

class Tests(unittest.TestCase):
    def test_console_release_allowlist_includes_factory_and_crm(self):
        policy=json.loads(POLICY.read_text())
        production=policy["production"]
        self.assertFalse(production["auto_merge_allowed"])
        self.assertTrue(production["human_console_merge_allowed"])
        allowed=set(production["operator_allowed_repositories"])
        self.assertIn("leandrosilveiradepaula/ai-product-factory",allowed)
        self.assertIn("leandrosilveiradepaula/crm-infodive",allowed)

if __name__=="__main__":
    unittest.main()
