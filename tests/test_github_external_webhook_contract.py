"""Fail-closed wiring contract; dynamic HMAC and SQL isolated tests run in CI."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
ROUTE=(ROOT/"apps/console/app/api/integrations/github-app/webhook/route.ts").read_text()
VERIFIER=(ROOT/"apps/console/lib/github-webhook-verification-config.ts").read_text()
OUTBOX=(ROOT/"apps/console/lib/github-webhook-outbox.ts").read_text()
SECURITY=(ROOT/"apps/console/lib/github-webhook-security.ts").read_text()
SQL=(ROOT/"supabase/migrations/20261029165500_github_external_event_wake_outbox.sql").read_text()
WORKFLOW=(ROOT/".github/workflows/github-external-webhook-postgres.yml").read_text()

class Tests(unittest.TestCase):
 def test_public_endpoint_is_explicitly_disabled_before_reading_body_or_creds(self):
  self.assertIn('process.env.FACTORY_GITHUB_WEBHOOK_ENABLED!=="true"',ROUTE)
  self.assertLess(ROUTE.index('FACTORY_GITHUB_WEBHOOK_ENABLED'),ROUTE.index('getGitHubWebhookVerificationConfig()'))
  self.assertIn('return answer(503,"disabled")',ROUTE)
  self.assertIn('export const runtime="nodejs"',ROUTE)
  self.assertNotIn('requireConsoleAdmin',ROUTE)
 def test_git_signature_checked_before_event_processing_or_db_claim(self):
  self.assertLess(ROUTE.index('authenticateGitHubWebhook('),ROUTE.index('normalizeGitHubWebhook('))
  self.assertLess(ROUTE.index('normalizeGitHubWebhook('),ROUTE.index('claimExternalWebhookWake('))
  self.assertLess(ROUTE.index('claimExternalWebhookWake('),ROUTE.index('requestIntakeWorkerWake()'))
  self.assertIn('timingSafeEqual',SECURITY)
  self.assertIn('MAX_WEBHOOK_BYTES',ROUTE)
  self.assertIn('"x-hub-signature-256"',SECURITY)
  self.assertIn('"x-github-delivery"',SECURITY)
 def test_secret_is_vault_retrieved_privately_without_browser_fallback(self):
  self.assertIn('factory_get_github_app_credentials',VERIFIER)
  self.assertIn('getSupabaseServerConfig',VERIFIER)
  self.assertIn('result.webhook_secret',VERIFIER)
  self.assertNotIn('NEXT_PUBLIC_',VERIFIER+ROUTE+OUTBOX)
  self.assertNotIn('FACTORY_GITHUB_WEBHOOK_SECRET',VERIFIER+ROUTE+OUTBOX)
  self.assertIn('https://fjplmxfcshhbmzgvyqlm.supabase.co',VERIFIER)
 def test_public_endpoint_never_claims_work_calls_models_or_merges(self):
  for s in ('merge_pull_request','OPENAI_API_KEY','run_direct_once','release_run','get_ci_state','apply_migration'):
   self.assertNotIn(s,ROUTE+OUTBOX+VERIFIER)
  self.assertIn('acknowledgeExternalWebhookWake',ROUTE)
  self.assertIn('return answer(503,"wake_pending")',ROUTE)
 def test_database_grants_are_strict_and_delivery_dedup_is_atomic(self):
  for item in ('enable row level security','on conflict(delivery_id) do nothing',
    'for update','delivery_id uuid primary key',"c.state='running'",'c.generation',
    "a.auth_mode='github_app'", "a.status='ready'",'a.repository_id=p_repository_id',
    'a.installation_id=p_installation_id',"r.candidate_commit=p_candidate_commit",
    "r.status=v_expected_status",'execution_generation','retryable','lease_until'):
   self.assertIn(item,SQL,item)
  for fn in ('factory_claim_external_webhook_wake_v1', 'factory_ack_external_webhook_wake_v1'):
   self.assertIn('revoke all on function public.'+fn,SQL)
   self.assertIn('grant execute on function public.'+fn,SQL)
  self.assertIn('grant select,insert,update on public.factory_external_webhook_wakes to service_role',SQL)
  self.assertNotIn('create policy',SQL)
  self.assertNotIn('security definer',SQL.lower())
 def test_isolated_postgresql_no_production_dsn_and_pin(self):
  self.assertIn('postgres:16',WORKFLOW)
  self.assertIn('factory_external_webhook_test',WORKFLOW)
  self.assertIn('psycopg[binary]==3.2.10',WORKFLOW)
  self.assertIn('FACTORY_WEBHOOK_TEST_ISOLATED: "true"',WORKFLOW)

if __name__=='__main__':unittest.main()