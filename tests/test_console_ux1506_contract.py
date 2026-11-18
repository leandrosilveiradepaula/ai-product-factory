"""Owner UX #1506: no fake readiness, optional gates or hidden operating controls."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/"apps/console/app"
PROJECT=(APP/"projects/[key]/page.tsx").read_text(encoding="utf-8")
ATTENTION=(APP/"api/human-attention/route.ts").read_text(encoding="utf-8")
GATES=(APP/"gates/page.tsx").read_text(encoding="utf-8")
SHELL=(APP/"shell.tsx").read_text(encoding="utf-8")
NAV=(APP/"nav.tsx").read_text(encoding="utf-8")
LOGIN=(APP/"login/page.tsx").read_text(encoding="utf-8")
STYLE=(APP/"globals.css").read_text(encoding="utf-8")
THEME=(APP/"theme.css").read_text(encoding="utf-8")
CI=(ROOT/".github/workflows/console.yml").read_text(encoding="utf-8")
RUNTIME=(ROOT/"scripts/test_console_ux1506_runtime.cjs").read_text(encoding="utf-8")

class OperatorFirstConsoleTests(unittest.TestCase):
 def test_next_action_comes_before_controls_and_historical_readiness(self):
  self.assertLess(PROJECT.index('className="projectOrientation"'),
                  PROJECT.index('id="project-control"'))
  self.assertLess(PROJECT.index('id="latest-request"'),
                  PROJECT.index('id="product-readiness"'))
  self.assertLess(PROJECT.index('className="projectOrientation"'),
                  PROJECT.index('id="latest-request"'))
  self.assertLess(PROJECT.index('if(stage==="operations"&&activeTasks>0'),
                  PROJECT.index('if(stage==="operations"&&readiness.ready'))
  self.assertLess(PROJECT.index('if(stage==="operations"&&readiness.ready'),
                  PROJECT.index('if(stage==="operations")return'))
  self.assertIn('nextAction(p.stage,hasPendingDatabase,activeTasks.length,p.productReadiness)',PROJECT)
  self.assertIn('Permissão de execução',PROJECT)
  self.assertIn('Habilitado para receber trabalho',PROJECT)
  self.assertIn('não significa que exista um worker executando agora',PROJECT)

 def test_historical_certification_cannot_authorize_current_release(self):
  self.assertIn('Aprovada no SHA avaliado',PROJECT)
  self.assertIn('não certifica commits posteriores',PROJECT)
  self.assertIn('não autoriza merge ou release de produção',PROJECT)
  self.assertIn('className="readinessDomainDisclosure" open={!p.productReadiness.ready}',PROJECT)
  self.assertIn('className="readinessEvidence"',PROJECT)
  self.assertIn('className="readinessDomainChecklist" role="list"',PROJECT)
  self.assertIn('Esta consulta não inicia tarefas nem modelos',PROJECT)

 def test_queued_worker_exposes_real_evidence_and_recovery(self):
  self.assertIn('className="projectPendingDiagnostics"',PROJECT)
  self.assertIn('p.wakeEvidence?.workerObservedAt',PROJECT)
  self.assertIn('p.pendingRun.attemptCount',PROJECT)
  self.assertIn('action="/api/projects/wake-recovery"',PROJECT)
  self.assertIn('executionControl.state==="running"?<ActionLink',PROJECT)
  self.assertIn('["running","pause","Pausar"]',PROJECT)
  self.assertIn('["running","stop","Parar"]',PROJECT)

 def test_optional_app_is_not_a_release_gate(self):
  self.assertIn('const count=pending.length+(githubApp.configured?installActions.length:0)',ATTENTION)
  self.assertNotIn('count=pending.length+installActions.length+(githubApp.configured?0:1)',ATTENTION)
  self.assertIn('pendingHumanGateCount:pending.length',ATTENTION)
  self.assertIn('const pendingCount=pending.length+installActions.length',GATES)
  self.assertIn('className="gateOptionalSetup"',GATES)
  self.assertIn('Configuração opcional',GATES)
  self.assertIn('ação pendente',SHELL)
  self.assertIn('label:"Ações humanas"',NAV)
  self.assertIn('pending.map(g=><article',GATES)
  self.assertIn('g.status==="pending"&&g.actionable',GATES)
  self.assertIn('applyPendingMigrationFromConsole',GATES)
  self.assertIn('mergeReadyReleaseFromConsole',GATES)

 def test_visual_hierarchy_preserves_accessibility_and_touch_targets(self):
  block=STYLE.split("/* UX/UI #1506 — operator-first clarity",1)[1]
  for selector in (".main .subtitle",".sidebar .navItem",
                   ".projectOrientation .nextActionCard",
                   ".projectLifecyclePanel .macroLifecycle",
                   ".projectControlActions",".projectPendingDiagnostics",
                   ".readinessDomainDisclosure",".gateOptionalSetup"):
   with self.subTest(selector=selector):
    self.assertIn(selector,block)
  for token in ("min-height:44px","font-size:15px",
                "@media(max-width:560px)",
                "grid-template-columns:repeat(2,minmax(0,1fr))"):
   self.assertIn(token,block)
  for hide in ("display:none","visibility:hidden","overflow-x:hidden"):
   self.assertNotIn(hide,block)
  self.assertIn("--space-page-x:24px",THEME)
  self.assertIn("--radius-lg:12px",THEME)

 def test_real_login_title_matches_visible_action_without_weakening_preview_guard(self):
  self.assertIn('export const metadata={title:"Entrar na Factory — AI Product Factory"}',LOGIN)
  self.assertIn('title="Entrar na Factory"',LOGIN)
  verifier=(ROOT/"scripts/verify_preview.mjs").read_text(encoding="utf-8")
  self.assertIn("preview_application_heading_or_title_unverified",verifier)
  self.assertIn("containsExpectedText(normalizeVisibleText(observed.title",verifier)

 def test_real_policy_has_offline_runtime_regression_in_pinned_console_ci(self):
  self.assertIn("node ../../scripts/test_console_ux1506_runtime.cjs",CI)
  self.assertIn("ts.transpileModule",RUNTIME)
  self.assertIn("nextAction(",RUNTIME)
  self.assertIn("human-attention/route.ts",RUNTIME)
  self.assertNotIn("fetch(",RUNTIME)
  self.assertNotIn("https://",RUNTIME)

if __name__=="__main__": unittest.main()
