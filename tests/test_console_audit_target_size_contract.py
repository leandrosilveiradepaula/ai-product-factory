"""Regression for real WCAG 2.2 AA target-size failure on /audit desktop.

The protected browser workflow remains the final authority. This source test
only ensures that the two real route-specific links keep full-size targets
and that axe's WCAG 2.2 AA rule is not bypassed.
"""
import re
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class AuditTargetSizeContractTests(unittest.TestCase):
    def test_actual_audit_row_links_receive_scoped_hit_target(self):
        page=(ROOT/"apps/console/app/audit/page.tsx").read_text()
        css=(ROOT/"apps/console/app/globals.css").read_text()
        self.assertIn('className="table auditTable"',page)
        self.assertIn('<Link href={"/projects/"+x.projectKey}',page)
        self.assertIn('<Link href={"/runs/"+x.runId}',page)
        rule=re.search(r"\.main \.auditTable \.tableRow a\[href\]\s*\{([^}]*)\}",css)
        self.assertIsNotNone(rule)
        declarations=dict((k.strip(),v.strip()) for k,v in
                          (part.split(":",1) for part in rule.group(1).split(";") if ":" in part))
        for dimension in ("min-width","min-height"):
            self.assertGreaterEqual(int(declarations[dimension].removesuffix("px")),24)
        self.assertIn(declarations.get("display"),("inline-flex","flex"))
        self.assertEqual(declarations.get("box-sizing"),"border-box")
        self.assertNotIn("visibility",declarations)
        self.assertNotIn("overflow",declarations)

    def test_real_wcag22_target_rule_is_not_exempted(self):
        audit=(ROOT/"scripts/console_wcag_audit.mjs").read_text()
        browser=(ROOT/"scripts/capture_authenticated_console.mjs").read_text()
        self.assertIn('"wcag22aa"',audit)
        self.assertIn("wcag_violations:",audit)
        self.assertIn("sanitizeAxeScan({results,route,viewport})",browser)
        self.assertNotRegex(audit,r"disableRules\s*\(\s*\[?['\"]target-size")

if __name__=="__main__":
    unittest.main()
