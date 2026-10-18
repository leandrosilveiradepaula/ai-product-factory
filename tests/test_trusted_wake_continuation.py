"""Contract: trusted wake must continue only when durable work and auth allow it."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/autonomous-runner.yml").read_text()
AUTONOMOUS = ("schedule", "issue_comment", "repository_dispatch", "workflow_run")


def job(name: str) -> str:
    pattern = r"(?ms)^  " + re.escape(name) + r":\n(.*?)(?=^  [a-z][a-z0-9-]*:\n|\Z)"
    match = re.search(pattern, WORKFLOW)
    if not match:
        raise AssertionError("missing Actions job " + name)
    return match.group(1)


class TrustedWakeContinuation(unittest.TestCase):
    def test_untrusted_intake_or_backup_never_reaches_queue(self):
        probe = job("schedule-probe")
        for marker in (
            "github.actor == 'infodive-ai-product-factory[bot]'",
            "github.event.action == 'factory-intake-wake'",
            "github.event.client_payload.source == 'console-intake'",
            "github.event.workflow_run.event == 'schedule'",
            "github.event.workflow_run.conclusion == 'success'",
            "github.event.workflow_run.head_branch == 'main'",
            "github.event.workflow_run.repository.full_name == github.repository",
            "steps.backup_wake.outputs.wake == 'true'",
        ):
            self.assertIn(marker, probe, marker)

    def test_dispatch_requires_real_queue_or_fresh_product_output(self):
        dispatch = job("dispatch")
        for event in AUTONOMOUS:
            self.assertIn("github.event_name == '" + event + "'", dispatch)
        for marker in (
            "needs.schedule-probe.result == 'success'",
            "needs.schedule-probe.outputs.dispatch_work == 'true'",
            "needs.product-stage.outputs.dispatch_work == 'true'",
            "needs.product-stage.result != 'failure'",
            "needs.github-access-preflight.result != 'failure'",
            "needs.codex-route-preflight.result != 'failure'",
            "FACTORY_DISPATCH_PRIMARY_READY:",
            "FACTORY_DISPATCH_CODEX_READY:",
        ):
            self.assertIn(marker, dispatch, marker)
        self.assertNotIn("needs.schedule-probe.outputs.product_work == 'true'", dispatch)
        self.assertIn("inputs.project_key != '' || inputs.run_direct == true || inputs.run_codex == true", dispatch)

    def test_routed_workers_never_start_from_event_alone(self):
        direct, codex = job("direct"), job("codex")
        for lane in (direct, codex):
            for event in AUTONOMOUS:
                self.assertIn("github.event_name == '" + event + "'", lane)
            self.assertIn("needs.dispatch.result == 'success'", lane)
        self.assertIn("needs.dispatch.outputs.direct_count != '0'", direct)
        self.assertIn("needs.dispatch.outputs.codex_count != '0'", codex)
        self.assertIn("inputs.run_direct == true", direct)
        self.assertIn("inputs.run_codex == true", codex)
        self.assertIn("environment: openai-api", direct)
        self.assertIn("FACTORY_PRIMARY_MODEL_ENABLED:", direct)
        self.assertIn("Refuse Direct when paid primary model is not explicitly enabled", direct)
        self.assertIn("environment: openai-codex", codex)
        self.assertIn("vars.FACTORY_CODEX_ENABLED == 'true'", codex)
        self.assertIn("Detect Codex runtime readiness", codex)

    def test_new_product_codex_goes_through_official_auth_preflight(self):
        preflight = job("codex-route-preflight")
        self.assertIn("needs: [schedule-probe, product-stage]", preflight)
        self.assertIn("needs.schedule-probe.outputs.dispatch_work == 'true'", preflight)
        self.assertIn("needs.product-stage.outputs.dispatch_work == 'true'", preflight)
        self.assertIn("vars.FACTORY_CODEX_ENABLED == 'true'", preflight)
        for marker in ("OPENAI_FEDERATION_RULE_ID", "CODEX_ACCESS_TOKEN", "FACTORY_GITHUB_TOKEN"):
            self.assertIn(marker, preflight)

    def test_manual_codex_and_preview_stay_opt_in_and_evidence_gated(self):
        manual, preview = job("codex-manual"), job("preview")
        for lane in (manual, preview):
            for event in AUTONOMOUS:
                self.assertIn("github.event_name == '" + event + "'", lane)
            self.assertIn("needs.schedule-probe.result == 'success'", lane)
        for marker in (
            "needs.schedule-probe.outputs.codex_manual_work == 'true'",
            "needs.dispatch.outputs.codex_count != '0'",
            "FACTORY_CODEX_MANUAL_FALLBACK_ENABLED == 'true'",
            "inputs.run_codex == true",
        ):
            self.assertIn(marker, manual)
        for marker in (
            "needs.schedule-probe.outputs.preview_work == 'true'",
            "needs.specialist-security.result == 'success'",
            "needs.specialist-qa.result == 'success'",
            "needs.specialist-operations.result == 'success'",
            "inputs.run_preview == true",
            "Run at most one verified Preview",
        ):
            self.assertIn(marker, preview)

    def test_no_release_bypass_or_new_registration_autostart(self):
        release = job("release-followup")
        self.assertIn("needs.schedule-probe.outputs.release_work == 'true'", release)
        self.assertIn("--mode release", release)
        self.assertNotIn("merge_pull_request", WORKFLOW)
        self.assertNotIn("gh pr merge", WORKFLOW)
        self.assertEqual(WORKFLOW.count("    - cron:"), 2)
        control = (ROOT / "apps/console/lib/control-plane.ts").read_text()
        registration = control.split("export async function createProjectIntakeAndBootstrap(", 1)[1].split("export type ProjectExecutionControl", 1)[0]
        self.assertNotIn("requestIntakeWorkerWake()", registration)


if __name__ == "__main__":
    unittest.main()
