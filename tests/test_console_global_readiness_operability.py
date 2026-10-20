"""Whole-product Console operability without client-specific shortcuts."""
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/"apps/console/app"
PROJECT=(APP/"projects/[key]/page.tsx").read_text()
SHELL=(APP/"shell.tsx").read_text()
CSS=(APP/"globals.css").read_text()
THEME=(APP/"theme.css").read_text()
BROWSER=(ROOT/"scripts/capture_authenticated_console.mjs").read_text()

DOMAINS=(
    "security","observability_operations","test_strategy",
    "product_experience","documentation","functional_completeness"
)

class ConsoleGlobalReadinessOperabilityTests(unittest.TestCase):
    def test_operations_directs_to_global_audit_not_false_completion(self):
        self.assertIn('if(stage==="operations")return {title:"Verificar a prontidão global do produto"',PROJECT)
        self.assertIn('href:"#product-readiness"',PROJECT)
        self.assertIn("release concluído não certifica o sistema inteiro",PROJECT)
        self.assertNotIn('title:"Nenhuma ação necessária agora",body:"O projeto já está em operação',PROJECT)
        self.assertIn('id="product-readiness"',PROJECT)
        self.assertIn("Esta consulta não inicia tarefas nem modelos.",PROJECT)

    def test_six_domains_are_visible_even_without_evaluation_and_no_fake_pass(self):
        block=PROJECT.split("const productAuditDomains=[",1)[1].split("] as const;",1)[0]
        self.assertEqual(re.findall(r'key:"([a-z_]+)"',block),list(DOMAINS))
        self.assertIn('className="readinessDomainChecklist" role="list"',PROJECT)
        self.assertIn('className="readinessDomain" role="listitem"',PROJECT)
        self.assertIn('p.productReadiness.ready?"Avaliado no SHA registrado":"Comprovação pendente"',PROJECT)
        self.assertIn("Sem avaliação global independente para o SHA atual",PROJECT)
        self.assertIn('href="/evals"',PROJECT)
        self.assertIn('href="/deployments"',PROJECT)
        self.assertNotIn('label={p.productReadiness.ready?"Produto pronto"',PROJECT)

    def test_new_project_setup_is_generic_cross_repository(self):
        self.assertIn("Este projeto precisa de um repositório GitHub próprio",PROJECT)
        self.assertIn("não existe proprietário GitHub pré-definido",PROJECT)
        self.assertIn("<code>{p.key}</code>",PROJECT)
        self.assertIn("https://github.com/new?name=",PROJECT)
        self.assertNotIn("O Service Desk precisa",PROJECT)
        self.assertNotIn('"leandrosilveiradepaula/"+p.key',PROJECT)
        self.assertIn('href="https://github.com/settings/installations"',PROJECT)

    def test_keyboard_skip_to_main_is_focusable_and_visible(self):
        self.assertIn('<Link href="#main-content" className="skipToMain">Pular para o conteúdo principal</Link>',SHELL)
        self.assertIn('<main className="main" id="main-content" tabIndex={-1}>',SHELL)
        self.assertIn(".skipToMain:focus-visible{transform:translateY(0)}",CSS)
        self.assertIn("outline:3px solid #88b8ff;outline-offset:3px",CSS)
        self.assertNotIn("display:none",CSS.split("/* Global product-operability pass",1)[1])
        self.assertNotIn("visibility:hidden",CSS.split("/* Global product-operability pass",1)[1])
        self.assertNotIn("body{overflow-x:hidden",CSS)

    def test_typography_touch_sizing_and_responsive_audit_are_real(self):
        for k,minimum in (
            ("font-size-2xs",11),("font-size-xs",12),
            ("font-size-sm",13),("font-size-md",14),
            ("font-size-body",14),("font-size-subtitle",14),
        ):
            self.assertRegex(THEME,rf"--{k}:{minimum}px;")
        css=CSS.split("/* Global product-operability pass",1)[1]
        for selector in (
            ".main .tableRow",".main .detailItem",".main .metricNote",
            ".main .timelineMeta",".main .primary",".main button[type=\"submit\"]",
            ".readinessDomainChecklist",".readinessDomainHeading",
            ".readinessDomainDisclaimer",
        ):
            with self.subTest(selector=selector):self.assertIn(selector,css)
        self.assertIn("min-height:44px",css)
        self.assertIn("min-height:48px",css)
        self.assertIn("grid-template-columns:minmax(0,1fr)",css)
        self.assertIn("overflow-wrap:anywhere",css)

    def test_authenticated_browser_executes_visual_not_mock_checks(self):
        self.assertIn("mobile readability/touch audit failed on",BROWSER)
        self.assertIn("readability.bodyPx < 14 || readability.mainPx < 14",BROWSER)
        self.assertIn("readability.quickTargets.length !== 3",BROWSER)
        self.assertIn("target.heightPx < 44",BROWSER)
        self.assertIn("keyboard skip link does not become visible on focus",BROWSER)
        self.assertIn('page.locator(".readinessDomainChecklist [role=\'listitem\']")',BROWSER)
        self.assertIn("readinessDomains !== 6",BROWSER)
        self.assertIn("verifiedWithoutMutation:true",BROWSER)
        self.assertIn("blockedProjectMutations.length",BROWSER)
        self.assertIn("mobile horizontal overflow on",BROWSER)
        self.assertNotIn("overflowX = 'hidden'",BROWSER)

if __name__=="__main__":
    unittest.main()
