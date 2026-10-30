"""Offline contracts for bounded external webhook recovery; never touch production."""
from pathlib import Path
import unittest
from unittest.mock import patch
from ai_product_factory.external_webhook_recovery import reconcile_external_wakes

ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/"supabase/migrations/20261030024500_reconcile_external_webhook_wake_retries.sql").read_text()
WORKFLOW=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
SOURCE=(ROOT/"src/ai_product_factory/external_webhook_recovery.py").read_text()

class ExternalWakeRecoveryContract(unittest.TestCase):
 def test_no_new_start_worker_claim_paid_calls_or_merge(self):
  for marker in ("create policy","security definer","insert into public.factory_runs",
    "update public.factory_runs","merge_pull_request","openai_api_key"):
   self.assertNotIn(marker,SQL.lower()+SOURCE.lower())
  self.assertIn("for update skip locked",SQL)
  self.assertIn("p_max_items not between 1 and 8",SQL)
  self.assertIn("c.state='running'",SQL)
  self.assertIn("c.generation=v_w.execution_generation",SQL)
  self.assertIn("a.installation_id=v_w.installation_id",SQL)
  self.assertIn("r.candidate_commit=v_w.candidate_commit",SQL)
  self.assertIn("p_pr_number", (ROOT/"supabase/migrations/20261029165500_github_external_event_wake_outbox.sql").read_text())
  self.assertIn("http_dispatch_204',false",SQL)
  self.assertIn("task_executed',false",SQL)
  self.assertIn("grant execute on function public.factory_reconcile_external_webhook_wakes_v1",SQL)
  self.assertIn("to service_role",SQL)
  self.assertIn("from public,anon,authenticated",SQL)
 def test_runs_after_trusted_probe_not_on_unverified_event(self):
  self.assertLess(WORKFLOW.index("Probe durable work queues without side effects"),
                  WORKFLOW.index("Reconcile externally authenticated wake intents after authoritative probe"))
  self.assertIn("steps.probe.outcome == 'success'",WORKFLOW)
  self.assertIn('type(signal.get(key)) is not bool',WORKFLOW)
  self.assertIn("BLOCKED_MIGRATION_NOT_APPLIED",WORKFLOW)
 def test_invalid_args_fail_before_network(self):
  with self.assertRaises(ValueError):
   reconcile_external_wakes(workflow_run_id=0,ci_work=False,preview_work=False,release_work=False)
  with self.assertRaises(ValueError):
   reconcile_external_wakes(workflow_run_id=1,ci_work=1,preview_work=False,release_work=False)
  with self.assertRaises(ValueError):
   reconcile_external_wakes(workflow_run_id=1,ci_work=False,preview_work=False,release_work=False,max_items=20)
