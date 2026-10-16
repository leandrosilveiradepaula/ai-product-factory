"""Human attention affordances must not silently hide actionable approvals."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
API=(ROOT/"apps/console/app/api/human-attention/route.ts").read_text()
SHELL=(ROOT/"apps/console/app/shell.tsx").read_text()
NAV=(ROOT/"apps/console/app/nav.tsx").read_text()
CSS=(ROOT/"apps/console/app/globals.css").read_text()

class HumanAttentionNotificationTests(unittest.TestCase):
 def test_authenticated_live_snapshot_is_read_only_and_fails_closed(self):
  self.assertIn("await requireConsoleOperator()",API)
  self.assertIn('g.status==="pending"&&g.actionable',API)
  self.assertIn("getGitHubAppInstallActions()",API)
  self.assertIn('"Cache-Control":"no-store"',API)
  self.assertIn('{status:"unavailable"}',API)
  self.assertIn("status:503",API)
  for unsafe in ("POST(","PATCH(","DELETE(","resolveHumanGate(","mergeReadyReleaseFromConsole("):
   self.assertNotIn(unsafe,API)

 def test_navigation_shows_actionable_count_including_mobile(self):
  self.assertIn("attentionCount",NAV)
  self.assertIn('href==="/gates"&&count!==null&&count!==undefined&&count>0',NAV)
  self.assertIn('primaryItems.map(item=><NavLink',NAV)
  self.assertIn('className="mobileQuickNav"',SHELL)
  self.assertIn('attention&&attention.count>0?',SHELL)
  self.assertIn("humanAttentionCount",NAV)
  self.assertIn('<ConsoleNav attentionCount={attention?.count??null}/>',SHELL)
  self.assertIn('className="mobileNav"',SHELL)
  self.assertIn("topbarAttention",SHELL)

 def test_project_specific_link_and_truthful_refresh(self):
  self.assertIn("attention.projects.includes",SHELL)
  self.assertIn('href="/gates"',SHELL)
  self.assertIn("Decisão humana pendente neste projeto",SHELL)
  self.assertIn('fetch("/api/human-attention",{cache:"no-store"})',SHELL)
  self.assertIn('document.visibilityState==="visible"',SHELL)
  self.assertIn('window.addEventListener("focus"',SHELL)
  self.assertIn("attentionUnavailable",SHELL)
  self.assertNotIn('setAttention({count:0',SHELL)
  self.assertIn(".projectHumanAttention",CSS)
  self.assertIn(".topbarAttention:focus-visible",CSS)

if __name__=="__main__":
 unittest.main()
