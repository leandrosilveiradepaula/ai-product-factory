import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MODULE=ROOT/"apps"/"console"/"lib"/"migration-operator.ts"
PAGE=ROOT/"apps"/"console"/"app"/"gates"/"page.tsx"
POLICY=ROOT/"config"/"factory.supabase-migration-policy.v1.json"
RUNTIME=ROOT/"src"/"ai_product_factory"/"runtime_cli.py"
GITHUB_ADAPTER=ROOT/"src"/"ai_product_factory"/"github_rest.py"


class ConsoleMigrationApplyTests(unittest.TestCase):
    def test_migration_path_is_admin_production_and_server_secret_only(self):
        text=MODULE.read_text()
        self.assertIn("requireConsoleAdmin()",text)
        self.assertIn('process.env.VERCEL_ENV!=="production"',text)
        self.assertIn("FACTORY_SUPABASE_MANAGEMENT_TOKEN",text)
        self.assertIn("FACTORY_RELEASE_GITHUB_TOKEN",text)
        self.assertNotIn("NEXT_PUBLIC_FACTORY_SUPABASE",text)

    def test_migration_is_bound_to_explicit_gate_pr_sha_and_versioned_file(self):
        text=MODULE.read_text()
        for marker in (
            'metadata.requested_action!=="apply_control_plane_migration"',
            "metadata.decision_only!==true",
            "metadata.automatic_apply!==false",
            "candidate!==expectedCandidate",
            'prState==="open"',
            'prState==="closed"',
            "Boolean(pr.draft)",
            "prMerged",
            "merge_commit_sha",
            'String(pr.base?.ref)!=="main"',
            "String(pr.head?.sha)!==candidate",
            "MIGRATION_PATH_RE",
            "migrationName!==match[2]",
            "/contents/",
        ):
            self.assertIn(marker,text)

    def test_merged_pr_recovery_is_fail_closed_for_closed_unmerged_prs(self):
        text=MODULE.read_text()
        self.assertIn('if(!prMerged||!String(pr.merge_commit_sha||"").match(SHA_RE))',text)
        self.assertIn('throw new Error("PR da migration foi fechado sem merge.")',text)
        self.assertIn('String(pr.head?.sha)!==candidate',text)
        self.assertIn('pr_state:prState',text)
        self.assertIn('pr_merged:prMerged',text)

    def test_checks_are_revalidated_before_fetching_and_applying_sql(self):
        text=MODULE.read_text()
        checks=text.index("/check-runs")
        contents=text.index("/contents/")
        apply_call=text.index("await applyMigration(configured.supabase_project_ref")
        self.assertLess(checks,contents)
        self.assertLess(contents,apply_call)
        self.assertIn("required_checks",POLICY.read_text())

    def test_management_api_uses_official_migrations_endpoint_not_generic_query(self):
        text=MODULE.read_text()
        self.assertIn("/database/migrations",text)
        self.assertNotIn("/database/query",text)
        self.assertIn("migrationNameSet",text)
        self.assertIn("alreadyApplied:true",text)

    def test_preflight_is_audited_and_post_is_idempotent(self):
        text=MODULE.read_text()
        self.assertIn("human_migration.console_preflight_succeeded",text)
        self.assertIn('"Idempotency-Key":idempotencyKey',text)
        self.assertIn('createHash("sha256")',text)
        preflight=text.index("human_migration.console_preflight_succeeded")
        apply_call=text.index("await applyMigration(configured.supabase_project_ref")
        self.assertLess(preflight,apply_call)

    def test_apply_is_audited_and_only_then_gate_is_resolved(self):
        text=MODULE.read_text()
        requested=text.index("human_migration.console_apply_requested")
        apply_call=text.index("await applyMigration(")
        succeeded=text.index("human_migration.console_apply_succeeded")
        resolve=text.rindex("await resolveAppliedGate")
        self.assertLess(requested,apply_call)
        self.assertLess(apply_call,succeeded)
        self.assertLess(succeeded,resolve)
        self.assertIn("human_migration.console_apply_failed",text)

    def test_console_renders_explicit_apply_button_without_runtime_auto_apply(self):
        page=PAGE.read_text()
        self.assertIn("Aplicar migration em produção",page)
        self.assertIn("<form action={applyMigration}",page)
        self.assertIn("candidate_commit",page)
        self.assertNotIn("FACTORY_SUPABASE_MANAGEMENT_TOKEN",page)
        self.assertNotIn("applyPendingMigrationFromConsole",RUNTIME.read_text())
        self.assertNotIn("database/migrations",GITHUB_ADAPTER.read_text())

    def test_policy_is_project_scoped_and_bounded(self):
        text=POLICY.read_text()
        self.assertIn('"ai-product-factory"',text)
        self.assertIn('"leandrosilveiradepaula/ai-product-factory"',text)
        self.assertIn('"fjplmxfcshhbmzgvyqlm"',text)
        self.assertIn('"supabase/migrations/"',text)
        self.assertIn('"max_migration_bytes": 1048576',text)

    def test_migration_action_has_visible_pending_and_success_feedback(self):
        page=PAGE.read_text()
        pending=(ROOT/"apps"/"console"/"app"/"gates"/"gate-decision-form.tsx").read_text()
        success=(ROOT/"apps"/"console"/"app"/"gates"/"gate-action-success-banner.tsx").read_text()
        self.assertIn('pendingLabel="Aplicando migration em produção..."',page)
        self.assertIn("Isso pode levar alguns segundos",page)
        self.assertIn('redirect("/gates?success=migration_applied")',page)
        self.assertIn("Migration aplicada com sucesso",page)
        self.assertIn("gateBusyPanel",pending)
        self.assertIn('disabled={pending}',pending)
        self.assertIn('aria-busy={pending}',pending)
        self.assertIn('role="status"',success)
        self.assertIn('url.searchParams.delete("success")',success)



if __name__=="__main__":
    unittest.main()
