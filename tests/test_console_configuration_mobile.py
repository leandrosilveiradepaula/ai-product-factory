"""Configuration must not clip content to evade authenticated mobile evidence."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
PAGE=(ROOT/"apps/console/app/configuration/page.tsx").read_text()
CSS=(ROOT/"apps/console/app/globals.css").read_text()
CAPTURE=(ROOT/"scripts/capture_authenticated_console.mjs").read_text()

class ConfigurationMobileContractTests(unittest.TestCase):
    def test_layout_scopes_its_own_responsive_grid(self):
        self.assertIn('className="overviewGrid configOverviewGrid"',PAGE)
        self.assertIn(".configOverviewGrid{min-width:0;grid-template-columns:minmax(0,1.2fr) minmax(0,.8fr)}",CSS)
        self.assertIn(".configOverviewGrid{grid-template-columns:minmax(0,1fr)}",CSS)
        self.assertIn(".configOverviewGrid .cardTop{flex-wrap:wrap}",CSS)
        self.assertIn(".configOverviewGrid .configRows>div{grid-template-columns:minmax(0,1fr)}",CSS)
        self.assertIn(".configOverviewGrid .compactRow{grid-template-columns:minmax(0,1fr)}",CSS)
        self.assertIn(".configOverviewGrid .mono,",CSS)
        self.assertNotIn(".configOverviewGrid{overflow-x:hidden",CSS)
        self.assertNotIn("body{overflow-x:hidden",CSS)

    def test_visual_audit_still_fails_on_horizontal_overflow(self):
        self.assertIn('{name:"configuration-mobile",path:"/configuration"}',CAPTURE)
        self.assertIn("layout.scrollWidth > layout.innerWidth + 2",CAPTURE)
        self.assertIn("mobile horizontal overflow on",CAPTURE)
        self.assertIn("offenders=",CAPTURE)
        self.assertIn("getBoundingClientRect()",CAPTURE)
        self.assertNotIn("overflowX = 'hidden'",CAPTURE)

if __name__=="__main__":
    unittest.main()
