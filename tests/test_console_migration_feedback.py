from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
PAGE=(ROOT/"apps/console/app/gates/page.tsx").read_text()
PENDING=(ROOT/"apps/console/app/gates/gate-decision-form.tsx").read_text()
OUTCOME=(ROOT/"apps/console/lib/migration-feedback.ts").read_text()
BANNER=(ROOT/"apps/console/app/gates/gate-action-success-banner.tsx").read_text()
CSS=(ROOT/"apps/console/app/globals.css").read_text()
OPERATOR=(ROOT/"apps/console/lib/migration-operator.ts").read_text()
CONSOLE_CI=(ROOT/".github/workflows/console.yml").read_text()

class VerifiedMigrationFeedbackTests(unittest.TestCase):
 def test_confirmation_is_not_derived_from_user_supplied_query(self):
  self.assertIn('await getVerifiedMigrationOutcome(params.migration_result)',PAGE)
  self.assertIn('gate.status!=="approved"',OUTCOME)
  self.assertIn('metadata?.requested_action!=="apply_control_plane_migration"',OUTCOME)
  self.assertIn("event?.payload?.candidate_commit===expectedCommit",OUTCOME)
  self.assertIn("event?.payload?.migration_name===expectedName",OUTCOME)
  self.assertIn("human_migration.console_apply_succeeded",OUTCOME)
  self.assertIn("human_migration.console_already_applied",OUTCOME)
  self.assertIn("if(!matching)return null",OUTCOME)
  self.assertIn('cache:"no-store"',OUTCOME)

 def test_server_action_redirects_only_after_verified_operator_return(self):
  action=PAGE.split("async function applyMigration(formData:FormData){",1)[1].split("const githubAppNotices",1)[0]
  self.assertLess(action.index("await applyPendingMigrationFromConsole"),action.index("redirect(\"/gates?migration_result=\""))
  self.assertLess(action.index('revalidatePath("/gates")'),action.index("redirect(\"/gates?migration_result=\""))
  self.assertIn('catch(error){redirectGateError(error);}',action)

 def test_pending_state_disables_controls_and_says_what_is_happening(self):
  self.assertIn('const {pending}=useFormStatus()',PENDING)
  self.assertIn('disabled={pending}',PENDING)
  self.assertIn('aria-busy={pending}',PENDING)
  self.assertIn('role="status"',PENDING)
  self.assertIn('aria-live="polite"',PENDING)
  self.assertIn("Não envie a operação novamente",PAGE)
  self.assertIn("Revalidando o SHA",PAGE)
  self.assertIn("gateBusySpinner",CSS)
  self.assertIn("prefers-reduced-motion:reduce",CSS)

 def test_success_is_dismissible_and_query_is_removed(self):
  self.assertIn('url.searchParams.delete("migration_result")',BANNER)
  self.assertIn("window.history.replaceState",BANNER)
  self.assertIn('aria-label="Fechar confirmação"',BANNER)
  self.assertIn('role="status"',BANNER)
  self.assertIn("alreadyApplied?",BANNER)

 def test_receipt_is_bound_to_exact_gate_run_and_sql_integrity(self):
  self.assertIn("gate_id:gateId",OPERATOR)
  self.assertIn("gate.id!==gateId",OUTCOME)
  self.assertIn("run.id!==gate.run_id",OUTCOME)
  self.assertIn("event?.payload?.gate_id===gateId",OUTCOME)
  self.assertIn('event?.payload?.source_integrity==="exact_sql_verified"',OUTCOME)
  self.assertIn("catch{",OUTCOME)
  self.assertIn("node ../../scripts/test_console_migration_interaction.cjs",CONSOLE_CI)
  self.assertIn("node --test ../../scripts/test_console_migration_browser.cjs",CONSOLE_CI)
  proof=(ROOT/"scripts/test_console_migration_browser.cjs").read_text()
  component=(ROOT/"scripts/fixtures/migration-browser-entry.tsx").read_text()
  self.assertIn('getByRole("button",{name:"Aplicar migration em produção"})',proof)
  self.assertIn('window.__factoryMigrationProof.complete("verified")',proof)
  self.assertIn('window.__factoryMigrationProof.complete("already_applied")',proof)
  self.assertIn('window.__factoryMigrationProof.complete(result)',proof)
  self.assertIn('mutation',proof)
  self.assertIn('127.0.0.1',proof)
  self.assertIn('GateDecisionPending',component)
  self.assertIn('GateActionSuccessBanner',component)
  self.assertIn('GateActionErrorBanner',component)
  self.assertIn('ConfirmSubmit',component)
  self.assertNotIn('supabase.co',component)
  self.assertNotIn('FACTORY_SUPABASE_MANAGEMENT_TOKEN',component)

if __name__=="__main__":unittest.main()
