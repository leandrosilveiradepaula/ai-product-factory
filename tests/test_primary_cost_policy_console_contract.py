"""No network/model calls: guard the UI, privileged SQL and Python contract."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
MIGRATION=(ROOT/"supabase/migrations/20261015231500_factory_primary_cost_policy.sql").read_text()
WF=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
PREFLIGHT=(ROOT/".github/workflows/control-plane-oidc-preflight.yml").read_text()
POLICY=(ROOT/"src/ai_product_factory/primary_cost_config.py").read_text()
RUNTIME=(ROOT/"src/ai_product_factory/runtime_cli.py").read_text()
METERED=(ROOT/"src/ai_product_factory/metered_provider.py").read_text()
READY=(ROOT/"src/ai_product_factory/product_worker_readiness.py").read_text()
SERVICE=(ROOT/"apps/console/lib/primary-cost-policy.ts").read_text()
ROUTE=(ROOT/"apps/console/app/api/configuration/cost-policy/route.ts").read_text()
CONFIG=(ROOT/"apps/console/app/configuration/page.tsx").read_text()
USAGE=(ROOT/"apps/console/app/usage/page.tsx").read_text()
PANEL=(ROOT/"apps/console/app/configuration/cost-policy-panel.tsx").read_text()


class ConfigurableFinancialPolicyContracts(unittest.TestCase):
 def test_schema_is_singleton_service_role_only_rls_and_seeded_at_approved_budget(self):
  for marker in (
   "create table if not exists public.factory_primary_cost_policy",
   "check (policy_key='primary')",
   "budget_usd numeric(12,4) not null",
   "reserve_usd numeric(12,4) not null",
   "enable row level security",
   "revoke all on table public.factory_primary_cost_policy from public,anon,authenticated",
   "grant select,update on table public.factory_primary_cost_policy to service_role",
   "values('primary',10.00,0.50,1) on conflict(policy_key) do nothing",
  ):self.assertIn(marker,MIGRATION)
  self.assertNotIn("create policy",MIGRATION.lower())
  self.assertNotIn("security definer",MIGRATION.lower())

 def test_update_requires_human_admin_version_and_append_only_audit_in_transaction(self):
  for marker in (
   "security invoker","set search_path to ''",
   "p_confirm_paid_limit is distinct from true",
   "role='admin' and is_active=true",
   "where policy_key='primary' for update",
   "version=previous.version+1",
   "previous.version is distinct from p_expected_version",
   "'factory.cost_policy.updated'",
   "insert into public.factory_audit_events",
   "revoke all on function public.factory_update_primary_cost_policy",
   "grant execute on function public.factory_update_primary_cost_policy",
  ):self.assertIn(marker,MIGRATION)
  self.assertNotIn("grant execute on function public.factory_update_primary_cost_policy(uuid,integer,numeric,numeric,text,boolean)\n to anon",MIGRATION.lower())

 def test_workflows_have_no_money_values_or_paid_probes(self):
  for work in (WF,PREFLIGHT):
   self.assertNotIn("FACTORY_MODEL_BUDGET_USD:",work)
   self.assertNotIn("FACTORY_MODEL_RESERVE_USD:",work)
  self.assertIn('vars.FACTORY_PRIMARY_MODEL_ENABLED == \'true\'',WF)
  self.assertIn("--mode product-readiness-evidence",WF)
  self.assertIn("steps.product_readiness_evidence.outputs.ready == 'true'",WF)
  self.assertNotIn("gh pr merge",WF)

 def test_all_paid_lanes_require_authoritative_live_policy(self):
  self.assertIn("SupabasePrimaryCostPolicyReader",POLICY)
  self.assertIn("require_primary_cost_capacity",RUNTIME)
  self.assertIn("require_primary_cost_capacity()",METERED)
  self.assertIn("SupabasePrimaryCostPolicyReader",READY)
  for code in (POLICY,METERED,READY,RUNTIME):
   self.assertNotIn('os.getenv("FACTORY_MODEL_BUDGET_USD")',code)
   self.assertNotIn('os.getenv("FACTORY_MODEL_RESERVE_USD")',code)
  self.assertIn("unknown_cost_events > 0",POLICY)
  self.assertIn("require_cost_ceiling(",POLICY)

 def test_console_auth_csrf_confirmation_and_version(self):
  self.assertIn("requireConsoleAdmin()",ROUTE)
  self.assertIn('origin!==url.origin',ROUTE)
  self.assertIn('application/x-www-form-urlencoded',ROUTE)
  self.assertIn('requireConsoleAdmin()',SERVICE)
  self.assertIn('/rpc/factory_update_primary_cost_policy',SERVICE)
  self.assertIn('p_expected_version:input.version',SERVICE)
  self.assertIn('p_confirm_paid_limit:true',SERVICE)
  self.assertIn('confirmed=body.get("confirm") === "true"',ROUTE)
  self.assertIn('name="confirm" value="true" required',PANEL)
  self.assertIn('ConfirmSubmit',PANEL)
  self.assertNotIn('NEXT_PUBLIC_',SERVICE+ROUTE+PANEL)
  self.assertNotIn("merge_pull_request",SERVICE+ROUTE+PANEL)

 def test_display_has_no_hardcoded_runtime_budget_and_proves_ledger_completeness(self):
  self.assertIn("getPrimaryCostPolicyView()",CONFIG)
  self.assertIn("getPrimaryCostPolicyView()",USAGE)
  self.assertIn("readCompleteOperationalRows",SERVICE)
  self.assertIn("unknownPaidCostEvents:null",SERVICE)
  self.assertIn('id="orcamento"',PANEL)
  self.assertNotIn("US$ 4,00",USAGE)
  self.assertNotIn("US$ 10,00",USAGE)
  self.assertNotIn("US$ 0,50",USAGE)


if __name__=="__main__":
 unittest.main()
