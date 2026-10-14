"""Readable minimum sizes for critical Console text, including mobile UI."""
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
CSS=(ROOT/"apps/console/app/globals.css").read_text()
START="/* Readability pass (audit #713):"
RULES=CSS.split(START,1)[1] if START in CSS else ""

class ConsoleReadabilityContract(unittest.TestCase):
 def test_audit_overrides_follow_legacy_styles(self):
  self.assertTrue(RULES)
  self.assertGreater(CSS.index(START),CSS.index(".gatePendingFieldset"))

 def test_navigation_and_system_information_are_readable(self):
  for selector in (
   ".sidebar .navItem", ".sidebar .navGroupLabel", ".sidebar .brandBlock span",
   ".sidebar .envBadge", ".topbar .topbarTrail", ".main .tableHeader",
   ".main .gateTechnicalGrid span", ".main .gateHistoryMeta", ".main .runStage small",
   ".main .logPanel", ".main .planningDecisionSuggestion button",
  ):
   with self.subTest(selector=selector):
    self.assertIn(selector+"{",RULES)
  self.assertIn("min-height:42px",RULES)

 def test_mobile_readability_and_no_hiding(self):
  self.assertIn("@media(max-width:860px)",RULES)
  self.assertIn(".mobileNav>summary{min-height:44px;font-size:15px}",RULES)
  self.assertIn(".main .tableRow,.main .cardMeta,.main .timelineMeta,.main .compactRow{font-size:14px}",RULES)
  self.assertIn("overflow-wrap:anywhere",RULES)
  self.assertNotIn("display:none",RULES)
  self.assertNotIn("visibility:hidden",RULES)

if __name__=="__main__":unittest.main()
