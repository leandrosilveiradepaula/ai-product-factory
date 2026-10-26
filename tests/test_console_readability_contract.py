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
    self.assertRegex(RULES,re.escape(selector)+r"(?=[,{])")
  self.assertIn("min-height:42px",RULES)

 def test_mobile_readability_and_no_hiding(self):
  self.assertIn("@media(max-width:860px)",RULES)
  self.assertIn(".mobileNav>summary{min-height:44px;font-size:15px}",RULES)
  self.assertIn(".main .tableRow,.main .cardMeta,.main .timelineMeta,.main .compactRow{font-size:14px}",RULES)
  self.assertIn("overflow-wrap:anywhere",RULES)
  self.assertNotIn("display:none",RULES)
  self.assertNotIn("visibility:hidden",RULES)

 def test_remaining_gate_labels_and_actions_not_microtext(self):
  self.assertIn("/* Second audit pass:",CSS)
  overrides=CSS.split("/* Second audit pass:",1)[1]
  self.assertIn(".main .primary,.main .secondary,.main .danger,.main .ghostButton{font-size:14px;min-height:42px}",overrides)
  self.assertIn(".main .mode button,.main .planningDecisionSuggestion button{font-size:14px;min-height:42px}",overrides)
  self.assertIn(".topbar .topbarWork{font-size:14px;min-height:42px",overrides)
  for selector in (
   ".main .lifecycleRail span", ".main .macroStage small",
   ".main .gateHistory>summary small", ".main .planningDecisionWhy span",
   ".main .planningDecisionAnswer small", ".main .resourceRow span",
   ".main .technicalStats span", ".main .jsonBlock",
   ".main .valueRow", ".main .screenGuide strong",
   ".main .configRows strong",
  ):
   with self.subTest(selector=selector):
    self.assertRegex(overrides,re.escape(selector)+r"(?=[,{])")
  self.assertIn("min-height:44px",overrides)
  self.assertNotIn("display:none",overrides)


class AuthenticatedAccessibilityGateTests(unittest.TestCase):
 def test_protected_live_capture_checks_all_routes_and_real_keyboard(self):
  capture=(ROOT/"scripts/capture_authenticated_console.mjs").read_text()
  self.assertIn("collectAccessibilitySnapshot",capture)
  self.assertIn("verifyAccessibilitySnapshot(metrics,route.name)",capture)
  self.assertIn('await page.keyboard.press("Tab")',capture)
  self.assertIn('await page.keyboard.press("Enter")',capture)
  self.assertIn("keyboard_skip_not_first",capture)
  self.assertIn("landedOnMain:true",capture)
  self.assertIn("accessibilityRoutes",capture)

 def test_console_ci_runs_accessibility_regressions(self):
  workflow=(ROOT/".github/workflows/console.yml").read_text()
  self.assertIn("node ../../scripts/test_console_accessibility_contract.mjs",workflow)

if __name__=="__main__":unittest.main()
