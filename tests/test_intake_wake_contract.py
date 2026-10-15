from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
WAKE=(ROOT/"apps/console/lib/intake-worker-wake.ts").read_text()
APP=(ROOT/"apps/console/lib/github-app.ts").read_text()
CONTROL=(ROOT/"apps/console/lib/control-plane.ts").read_text()
RUNNER=(ROOT/".github/workflows/autonomous-runner.yml").read_text()

class IntakeWakeContract(unittest.TestCase):
 def test_existing_app_fallback_is_scoped_and_short_lived(self):
  self.assertIn("requestFactoryIntakeWakeViaGitHubApp",WAKE)
  self.assertIn('repositories:["ai-product-factory"]',APP)
  self.assertIn('permissions:{contents:"write"}',APP)
  self.assertIn('event_type:"factory-intake-wake"',APP)
  self.assertIn("app/installations/",APP)
  self.assertNotIn("NEXT_PUBLIC_",WAKE)
  self.assertNotIn("installation_token_persisted:true",APP)

 def test_only_exact_factory_app_can_wake_runner(self):
  self.assertIn("repository_dispatch:",RUNNER)
  self.assertIn("types: [factory-intake-wake]",RUNNER)
  self.assertIn("github.actor == 'infodive-ai-product-factory[bot]'",RUNNER)
  self.assertIn("github.event.client_payload.source == 'console-intake'",RUNNER)
  self.assertIn("needs.schedule-probe.outputs.product_work == 'true'",RUNNER)
  self.assertIn("steps.readiness.outputs.primary_model == 'true'",RUNNER)

 def test_durable_intake_precedes_optional_wake_audit(self):
  atomic=CONTROL.index('rpc/factory_start_project_intake_v1')
  confirmation=CONTROL.index('result.request_id!==draftId')
  wake=CONTROL.index("const wakeStatus=await requestIntakeWorkerWake()")
  audit=CONTROL.index('event_type:"project.bootstrap.wake_attempted"')
  self.assertLess(atomic,confirmation)
  self.assertLess(confirmation,wake)
  self.assertLess(wake,audit)
  self.assertIn("if(result.created)",CONTROL)
  self.assertIn("if(!audit.ok)",CONTROL)
  self.assertIn("return {projectId:String(result.project_id)",CONTROL)

 def test_no_cost_or_merge_bypass(self):
  self.assertNotIn("merge_pull_request",WAKE+APP[-2500:])
  self.assertNotIn("FACTORY_PRIMARY_MODEL_ENABLED=true",WAKE)
  self.assertNotIn("OPENAI_API_KEY",WAKE)

if __name__=="__main__":
 unittest.main()
