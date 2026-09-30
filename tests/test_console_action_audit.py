import re
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/"apps"/"console"/"app"


def route_file(href:str)->Path:
    if href=="/":
        return APP/"page.tsx"
    return APP/href.lstrip("/")/"page.tsx"


class ConsoleActionAuditTests(unittest.TestCase):
    def test_sidebar_static_links_have_real_routes(self):
        text=(APP/"nav.tsx").read_text()
        hrefs=re.findall(r'href:"([^"]+)"',text)
        self.assertGreater(len(hrefs),5)
        missing=[href for href in hrefs if not route_file(href).exists()]
        self.assertEqual(missing,[])

    def test_topbar_and_primary_project_links_have_real_routes(self):
        files=[
            APP/"layout.tsx",
            APP/"page.tsx",
            APP/"projects"/"page.tsx",
            APP/"runs"/"page.tsx",
            APP/"queue"/"page.tsx",
        ]
        hrefs=set()
        for path in files:
            text=path.read_text()
            hrefs.update(re.findall(r'href="(/[^"#?{]*)"',text))
        missing=[href for href in sorted(hrefs) if not route_file(href).exists()]
        self.assertEqual(missing,[])

    def test_configuration_tabs_are_actionable_anchors(self):
        text=(APP/"configuration"/"page.tsx").read_text()
        for target in ("governanca","modelos","execucao","preview","seguranca"):
            self.assertIn(f'href="#{target}"',text)
            self.assertIn(f'id="{target}"',text)
        self.assertNotIn('<div className="configTabs"><span',text)

    def test_auth_pages_do_not_render_authenticated_console_shell(self):
        layout=(APP/"layout.tsx").read_text()
        shell=(APP/"shell.tsx").read_text()
        self.assertIn("<ConsoleShell>{children}</ConsoleShell>",layout)
        self.assertIn('pathname==="/login"',shell)
        self.assertIn('pathname==="/unauthorized"',shell)
        auth_block=shell.split("if(authOnly){",1)[1].split("return <div className=\"consoleShell\">",1)[0]
        self.assertNotIn("ConsoleNav",auth_block)
        self.assertNotIn("Sessão ativa",auth_block)
        self.assertNotIn("Factory saudável",auth_block)
        self.assertNotIn("Factory saudável",shell)
        self.assertNotIn("<span>Online</span>",shell)

    def test_shell_environment_label_is_not_hardcoded_to_production(self):
        layout=(APP/"layout.tsx").read_text()
        shell=(APP/"shell.tsx").read_text()
        self.assertIn("process.env.VERCEL_ENV",layout)
        self.assertIn('?"Produção":',layout)
        self.assertIn('?"Preview":',layout)
        self.assertIn("environmentLabel",shell)
        self.assertNotIn('<span className="envBadge">produção</span>',shell)

    def test_login_preserves_validated_next_destination(self):
        login=(APP/"login"/"page.tsx").read_text()
        actions=(APP/"auth-actions.ts").read_text()
        middleware=(ROOT/"apps"/"console"/"middleware.ts").read_text()
        self.assertIn('name="next"',login)
        self.assertIn("safeNext",login)
        self.assertIn("safeNext",actions)
        self.assertIn("redirect(next)",actions)
        self.assertIn('url.searchParams.set("next",path+request.nextUrl.search)',middleware)
        self.assertIn('value.startsWith("//")',actions)
        self.assertIn('value.includes("\\\\")',actions)

    def test_auth_redirect_preserves_oauth_callback_query(self):
        middleware=(ROOT/"apps"/"console"/"middleware.ts").read_text()
        self.assertIn("path+request.nextUrl.search",middleware)
        callback=(APP/"api"/"integrations"/"supabase"/"callback"/"route.ts").read_text()
        self.assertIn('u.searchParams.get("code")',callback)
        self.assertIn('u.searchParams.get("state")',callback)

    def test_intake_edit_preserves_values_and_draft_attachments(self):
        form=(APP/"projects"/"new"/"intake-form.tsx").read_text()
        actions=(APP/"projects"/"new"/"actions.ts").read_text()
        review=(APP/"projects"/"new"/"review"/"page.tsx").read_text()
        attachments=(ROOT/"apps"/"console"/"lib"/"attachments.ts").read_text()
        self.assertIn('name="draft_id"',form)
        self.assertIn("defaultValue={initial?.summary",form)
        self.assertIn("defaultValue={initial?.name",form)
        self.assertIn("countProjectDraftFiles",actions)
        self.assertIn("existingCount+files.length>10",actions)
        self.assertIn('"/projects/new?intake="',review)
        self.assertIn('target="_blank"',review)
        self.assertIn("normalizeIntake",review)
        self.assertIn("validateIntake",review)
        self.assertIn("countProjectDraftFiles",attachments)

    def test_dashboard_never_falls_back_to_demo_data(self):
        text=(ROOT/"apps"/"console"/"lib"/"control-plane.ts").read_text()
        self.assertNotIn("const demo:Dashboard",text)
        self.assertNotIn("return demo",text)
        self.assertIn('throw new Error("Control Plane não configurado.")',text)

    def test_mutating_controls_are_bound_to_server_actions(self):
        gates=(APP/"gates"/"page.tsx").read_text()
        operators=(APP/"admin"/"operators"/"page.tsx").read_text()
        review=(APP/"projects"/"new"/"review"/"page.tsx").read_text()
        self.assertIn("<form action={resolveGate}",gates)
        self.assertIn('name="resolution" value="approved"',gates)
        self.assertIn('name="resolution" value="rejected"',gates)
        self.assertIn("<form action={updateOperator}",operators)
        self.assertIn('name="active" value="true"',operators)
        self.assertIn("<form action={start}",review)

    def test_supabase_connect_visual_action_has_real_route_handlers(self):
        detail=(APP/"projects"/"[key]"/"page.tsx").read_text()
        self.assertIn("/api/integrations/supabase/connect",detail)
        self.assertIn('operator.role==="admin"',detail)
        self.assertIn("supabaseMessages",detail)
        self.assertIn("verification_failed",detail)
        self.assertIn("Administrador necessário",detail)
        projects=(APP/"projects"/"page.tsx").read_text()
        self.assertIn("oauth_invalid",projects)
        self.assertIn("project_missing",projects)
        self.assertTrue((APP/"api"/"integrations"/"supabase"/"connect"/"route.ts").exists())
        self.assertTrue((APP/"api"/"integrations"/"supabase"/"callback"/"route.ts").exists())


if __name__=="__main__":
    unittest.main()
