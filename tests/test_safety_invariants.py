import pathlib,unittest
from decimal import Decimal
from ai_product_factory.cost_policy import evaluate_cost_ceiling
from ai_product_factory.models import RiskProfile
from ai_product_factory.release_policy import ReleaseEnvironment,evaluate_release

ROOT=pathlib.Path(__file__).resolve().parents[1]
class SafetyInvariantTests(unittest.TestCase):
 def test_production_is_always_human_gated(self):
  for risk in (RiskProfile(),RiskProfile(destructive_data_change=True),RiskProfile(new_paid_service=True)):
   d=evaluate_release(ReleaseEnvironment.PROD,risk);self.assertTrue(d.human_gate_required);self.assertFalse(d.may_release_autonomously)
 def test_strict_paid_execution_needs_budget_and_reservation(self):
  self.assertFalse(evaluate_cost_ceiling(budget=None,known_spend=Decimal("0"),reserved_cost=Decimal("1"),strict=True).allowed)
  self.assertFalse(evaluate_cost_ceiling(budget=Decimal("10"),known_spend=Decimal("0"),reserved_cost=None,strict=True).allowed)
 def test_scheduled_direct_requires_explicit_primary_and_budget_gates(self):
  text=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
  direct=text.split("\n  direct:",1)[1].split("\n\n  preview:",1)[0]
  self.assertIn("inputs.run_direct == true",direct)
  self.assertIn("github.event_name == 'schedule'",direct)
  self.assertIn('FACTORY_PRIMARY_MODEL_ENABLED: "true"',direct)
  self.assertIn('FACTORY_PRIMARY_AUTH_MODE: api_key',direct)
  self.assertIn('FACTORY_MODEL_BUDGET_USD: "4.00"',direct)
  self.assertIn('FACTORY_MODEL_RESERVE_USD: "0.50"',direct)
 def test_direct_is_inert_without_control_plane_credentials(self):
  text=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
  direct=text.split("\n  direct:",1)[1].split("\n\n  codex:",1)[0]
  self.assertIn("Detect Direct Control Plane readiness",direct)
  self.assertIn("Direct execution is inert: Control Plane credentials are not configured.",direct)
  self.assertIn("steps.readiness.outputs.control_plane == 'true'",direct)
  process=direct.split("Process assigned Direct specialist task",1)[1]
  self.assertIn("steps.readiness.outputs.control_plane == 'true'",process)

 def test_api_key_primary_jobs_use_oidc_only_for_control_plane(self):
  text=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
  product=text.split("\n  product-stage:",1)[1].split("\n  ci-followup:",1)[0]
  direct=text.split("\n  direct:",1)[1].split("\n\n  codex:",1)[0]
  for block in (product,direct):
   self.assertIn("FACTORY_PRIMARY_AUTH_MODE: api_key",block)
   self.assertIn("./.github/actions/control-plane-oidc",block)
   self.assertNotIn("OPENAI_FEDERATION_RULE_ID",block)
   self.assertNotIn("OPENAI_IDENTITY_TOKEN_FILE",block)
  codex=text.split("\n  codex:",1)[1].split("\n  codex-manual:",1)[0]
  self.assertIn("id-token: write",codex)
  self.assertIn("OPENAI_FEDERATION_RULE_ID",codex)

 def test_control_plane_actions_use_oidc_without_supabase_secrets(self):
  text=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
  self.assertNotIn("secrets.SUPABASE_SECRET_KEY",text)
  self.assertNotIn("secrets.SUPABASE_SERVICE_ROLE_KEY",text)
  self.assertNotIn("secrets.SUPABASE_URL",text)
  self.assertGreaterEqual(text.count("./.github/actions/control-plane-oidc"),8)
 def test_alert_job_is_scheduled_and_deduplicated_sink_is_explicitly_enabled(self):
  text=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
  alerts=text.split("\n  alerts:",1)[1]
  self.assertIn("github.event_name == 'schedule'",alerts)
  self.assertIn("inputs.run_alerts == true",alerts)
  self.assertIn('FACTORY_GITHUB_ALERTS_ENABLED: "true"',alerts)
 def test_release_followup_cannot_merge_or_write_code(self):
  text=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
  release=text.split("\n  release-followup:",1)[1].split("\n  dispatch:",1)[0]
  self.assertIn("pull-requests: read",release)
  self.assertIn("issues: write",release)
  self.assertNotIn("contents: write",release)
  runtime=(ROOT/"src/ai_product_factory/runtime_cli.py").read_text()
  start=runtime.split("def run_release_once",1)[1].split("def run_alerts_once",1)[0]
  self.assertNotIn("merge_pull_request",start)
 def test_scheduled_preview_is_read_only_and_probed_before_browser_install(self):
  text=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
  preview=text.split("\n  preview:",1)[1].split("\n  alerts:",1)[0]
  self.assertIn("github.event_name == 'schedule'",preview)
  self.assertIn("inputs.run_preview == true",preview)
  self.assertIn("--mode preview-probe",preview)
  self.assertIn("steps.preview_probe.outputs.browser == 'true'",preview)
  self.assertIn("contents: read",preview)
  self.assertIn("issues: read",preview)
  self.assertIn("pull-requests: read",preview)
  self.assertNotIn("contents: write",preview)
  self.assertNotIn("pull-requests: write",preview)
 def test_cross_repo_jobs_receive_explicit_factory_github_secret(self):
  text=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
  for job,next_job in (("ci-followup","release-followup"),("release-followup","dispatch"),("direct","preview"),("preview","alerts")):
   block=text.split(f"\n  {job}:",1)[1].split(f"\n  {next_job}:",1)[0]
   self.assertIn("FACTORY_GITHUB_TOKEN",block)
 def test_codex_worker_is_wif_only_bounded_and_inert_without_readiness(self):
  workflow=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
  codex=workflow.split("\n  codex:",1)[1].split("\n\n  preview:",1)[0]
  self.assertIn("id-token: write",codex)
  self.assertIn("FACTORY_CODEX_ENABLED",codex)
  self.assertIn("OPENAI_FEDERATION_RULE_ID",codex)
  self.assertIn("OPENAI_WIF_AUDIENCE",codex)
  self.assertIn("FACTORY_GITHUB_TOKEN",codex)
  self.assertIn("steps.readiness.outputs.ready == 'true'",codex)
  self.assertIn("@openai/codex@0.157.0",codex)
  self.assertNotIn("OPENAI_API_KEY",codex)
  producer=(ROOT/"src/ai_product_factory/codex_cli_producer.py").read_text()
  self.assertIn("FACTORY_CODEX_MAX_FILES",producer)
  self.assertIn("FACTORY_CODEX_MAX_BYTES",producer)
  self.assertIn("63-question benchmark",producer)
  self.assertNotIn("danger-full-access",producer)
 def test_runtime_has_no_automatic_merge_capability(self):
  adapter=(ROOT/"src/ai_product_factory/github_rest.py").read_text()
  protocol=(ROOT/"src/ai_product_factory/github_loop.py").read_text()
  self.assertNotIn("def merge_pull_request",adapter)
  self.assertNotIn("def merge_pull_request",protocol)
 def test_primary_requires_explicit_enable_flag(self):
  text=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
  self.assertIn('FACTORY_PRIMARY_MODEL_ENABLED',text)
  self.assertIn('FACTORY_PRIMARY_MODEL_ENABLED\" = \"true',text)
if __name__=="__main__":unittest.main()
