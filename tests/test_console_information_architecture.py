"""User-first Console information architecture: mobile, gating and honesty contracts."""
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/"apps/console/app"
NAV=(APP/"nav.tsx").read_text(encoding="utf-8")
SHELL=(APP/"shell.tsx").read_text(encoding="utf-8")
HOME=(APP/"page.tsx").read_text(encoding="utf-8")
PROJECTS=(APP/"projects/page.tsx").read_text(encoding="utf-8")
PROJECT=(APP/"projects/[key]/page.tsx").read_text(encoding="utf-8")
CSS=(APP/"globals.css").read_text(encoding="utf-8")
BROWSER=(ROOT/"scripts/capture_authenticated_console.mjs").read_text(encoding="utf-8")
INTAKE=(APP/"projects/new/intake-form.tsx").read_text(encoding="utf-8")
NEW_PROJECT=(APP/"projects/new/page.tsx").read_text(encoding="utf-8")
REVIEW=(APP/"projects/new/review/page.tsx").read_text(encoding="utf-8")


class ConsoleInformationArchitectureTests(unittest.TestCase):
    def test_exactly_four_primary_destinations_all_advanced_routes_preserved(self):
        block=NAV.split("const primaryItems=[",1)[1].split("];",1)[0]
        self.assertEqual(re.findall(r'href:"([^"]+)"',block),["/","/projects","/deliveries","/gates"])
        advanced=NAV.split("const advancedGroups=[",1)[1].split("];",1)[0]
        for route in ("/runs","/queue","/agents","/orchestration","/evals",
                      "/deployments","/usage","/audit","/configuration","/admin/operators"):
            with self.subTest(route=route):
                self.assertIn('href:"'+route+'"',advanced)
        self.assertIn("<details key={pathname} className=\"navAdvanced\" open={advancedActive}>",NAV)
        self.assertIn('className="navAdvancedToggle"',NAV)
        self.assertIn('aria-current={isActive?"page":undefined}',NAV)
        self.assertIn('href==="/gates"&&count!==null&&count!==undefined&&count>0',NAV)

    def test_shell_keeps_decisions_visible_but_removes_global_duplicate_ctas(self):
        self.assertNotIn('className="topbarWork"',SHELL)
        self.assertNotIn('className="mobileNewProject"',SHELL)
        self.assertEqual(SHELL.count('<ConsoleNav attentionCount={attention?.count??null} onNavigate={rememberNavigation}/>'),2)
        self.assertIn('onNavigate?.(href)',NAV)
        self.assertIn('className="mobileNav" key={pathname}',SHELL)
        self.assertIn('<nav className="mobileQuickNav" aria-label="Navegação rápida">',SHELL)
        for route in ('href="/"','href="/projects"','href="/deliveries"','href="/gates"'):
            self.assertIn(route,SHELL)
        self.assertIn('attentionUnavailable',SHELL)
        self.assertIn('className="projectHumanAttention"',SHELL)
        self.assertIn('className={"routePurpose "+(context.advanced?',SHELL)
        self.assertNotIn('className={context.advanced?"screenGuide advanced":"screenGuide"}',SHELL)

    def test_home_shows_real_products_and_operator_intentions_first(self):
        for action in ("Criar um produto","Melhorar um produto","Acompanhar entregas"):
            self.assertIn(action,HOME)
        self.assertIn('getHumanGates(100,true)',HOME)
        self.assertIn('summarizeOperatorAttention(',HOME)
        self.assertIn('getProductSituations()',HOME)
        self.assertIn('className="operatorWelcome"',HOME)
        self.assertIn('className="productSituationList"',HOME)
        self.assertIn('className="operatorAttention requiresAction"',HOME)
        self.assertIn('details className="operatorDiagnostics"',HOME)
        self.assertIn('products.reduce((n,p)=>n+p.confirmedRunning,0)',HOME)
        self.assertLess(HOME.index('className="operatorWelcome"'),HOME.index('className="operatorDiagnostics"'))
        self.assertNotIn('incidents.map',HOME)
        self.assertNotIn('label="orquestrador online"',HOME)
        self.assertNotIn('getHumanGates(8)',HOME)

    def test_project_cards_show_stage_not_fabricated_percentages(self):
        self.assertIn('Veja entregas comprovadas',PROJECTS)
        self.assertIn('getProductSituations()',PROJECTS)
        self.assertIn('ProductSituationCard',PROJECTS)
        self.assertNotIn('macroProgress',PROJECTS)
        self.assertNotIn('Progresso pelas 5 macroetapas',PROJECTS)
        self.assertIn('href="/projects/new"',PROJECTS)

    def test_project_actions_are_conditional_and_all_security_surfaces_retained(self):
        self.assertIn('className="projectMoreActions"',PROJECT)
        self.assertIn('<summary>Mais opções</summary>',PROJECT)
        self.assertIn('humanActionNeeded',PROJECT)
        self.assertIn('variant={humanActionNeeded?"primary":"secondary"}',PROJECT)
        self.assertIn('className="readinessEvidence"',PROJECT)
        self.assertIn('className="projectTechnicalDetails projectIntegrations"',PROJECT)
        self.assertIn('open={integrationNeedsAttention}',PROJECT)
        for required in ('id="repository-setup"','id="product-readiness"',
                         'id="github-access"','id="preview-policy"','id="databases"',
                         'Reexecutar preflight','Conectar Supabase','Reconciliar projeto',
                         'Auditoria aprovada','Produto não pronto'):
            with self.subTest(required=required):
                self.assertIn(required,PROJECT)
        self.assertIn('Isso não comprova que o HEAD atual permanece igual nem libera produção',PROJECT)
        self.assertIn('A Factory não infere prontidão a partir de CI, Preview, release ou ausência de issues',PROJECT)

    def test_intake_shows_prompt_first_without_duplicate_users_field(self):
        self.assertIn('className="intakeSteps"',NEW_PROJECT)
        self.assertIn('className="intakeSteps"',REVIEW)
        self.assertNotIn('className="gettingStarted"',NEW_PROJECT)
        self.assertNotIn('className="gettingStarted"',REVIEW)
        self.assertIn('className="intakeOptional"',INTAKE)
        self.assertIn('open={hasAdditionalContext}',INTAKE)
        self.assertIn('className="intakeSubmit"',INTAKE)
        self.assertEqual(INTAKE.count('name="users"'),1)
        self.assertIn('name="summary" rows={6} required',INTAKE)
        self.assertIn('name="name" required',INTAKE)
        self.assertIn('name="attachments" type="file" multiple',INTAKE)
        self.assertIn("Revisar e iniciar Descoberta",INTAKE)
        self.assertIn("Revisar e importar projeto",INTAKE)

    def test_responsive_navigation_does_not_hide_body_overflow(self):
        for required in ('.mobileQuickNav{display: none}',
                         '.mobileQuickNav{display:grid',
                         '.mobileNavBody{position:absolute',
                         '.topbar:not(.hasAttention){display: none}',
                         '.topbar.hasAttention{display:flex',
                         '.projectMiniRail{display:flex;flex-wrap:wrap',
                         '.navAdvancedToggle', 'min-height:44px',
                         'env(safe-area-inset-bottom)',
                         'overflow-wrap:anywhere'):
            with self.subTest(required=required):
                self.assertIn(required,CSS)
        self.assertNotIn('body{overflow-x:hidden',CSS)
        self.assertNotIn('html{overflow-x:hidden',CSS)
        self.assertIn('mobile horizontal overflow on',BROWSER)
        self.assertIn('unexpected primary navigation',BROWSER)
        self.assertIn('mobile quick navigation is incomplete',BROWSER)
        self.assertIn('mobile full menu overflow',BROWSER)
        self.assertIn('overview-mobile-menu.png',BROWSER)


if __name__=="__main__":
    unittest.main()
