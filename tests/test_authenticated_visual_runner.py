"""Regression: visual evidence must launch pinned browser without the
ubuntu-latest drift that broke the real #1109 post-merge capture.

Contracts are source/read-only. A future *real* authenticated capture with a
new, authorized workflow run remains necessary; CI never fakes an operator.
"""
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
WORKFLOW=(ROOT/".github/workflows/authenticated-visual-evidence.yml").read_text()
SMOKE=(ROOT/"scripts/verify_auth_visual_browser_runtime.mjs").read_text()

class AuthenticatedVisualRunnerContract(unittest.TestCase):
 def test_runner_is_proven_ubuntu_2404_not_moving_latest(self):
  self.assertIn("runs-on: ubuntu-24.04",WORKFLOW)
  self.assertNotIn("runs-on: ubuntu-latest",WORKFLOW)
  self.assertIn('. /etc/os-release',WORKFLOW)
  self.assertIn('"${VERSION_ID:-}" != "24.04"',WORKFLOW)
  self.assertIn('"${ID:-}" != "ubuntu"',WORKFLOW)

 def test_playwright_is_still_pinned_and_browser_smoked_before_provision(self):
  self.assertIn("npm install --no-save --no-package-lock playwright@1.63.0",WORKFLOW)
  self.assertIn("npx playwright install --with-deps chromium",WORKFLOW)
  self.assertIn("node scripts/verify_auth_visual_browser_runtime.mjs",WORKFLOW)
  self.assertLess(WORKFLOW.index("Install pinned Playwright browser"),
                  WORKFLOW.index("Verify pinned Chromium launches offline"))
  self.assertLess(WORKFLOW.index("Verify pinned Chromium launches offline"),
                  WORKFLOW.index("Mint provisioning GitHub OIDC token"))
  self.assertLess(WORKFLOW.index("Verify pinned Chromium launches offline"),
                  WORKFLOW.index("Provision ephemeral visual operator"))
  self.assertIn("chromium.launch({headless:true})",SMOKE)
  self.assertIn("data:text/html",SMOKE)
  self.assertIn("await browser.close()",SMOKE)
  self.assertNotIn("https://",SMOKE)
  self.assertNotIn("FACTORY_VISUAL_EMAIL",SMOKE)
  self.assertNotIn("FACTORY_VISUAL_PASSWORD",SMOKE)

 def test_no_workflow_only_autoprovision_or_bypassed_cleanup(self):
  trigger=WORKFLOW.split("\npermissions:",1)[0]
  self.assertIn('      - "apps/console/**"',trigger)
  self.assertNotIn('      - ".github/workflows/authenticated-visual-evidence.yml"',trigger)
  self.assertIn("if: always()",WORKFLOW)
  self.assertIn("Finalize registry and remove ephemeral operator",WORKFLOW)
  self.assertIn('No ephemeral operator was provisioned.',WORKFLOW)
  self.assertIn('GITHUB_RUN_ATTEMPT:-0',WORKFLOW)
  self.assertIn('FACTORY_VISUAL_TARGET_COMMIT',WORKFLOW)

if __name__=="__main__":
 unittest.main()
