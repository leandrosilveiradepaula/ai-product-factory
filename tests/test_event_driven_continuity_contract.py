"""Static safety contract for real GitHub event -> eligible-queue continuation.

These assertions deliberately do not dispatch workflows, run models or write DB.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = (ROOT / '.github/workflows/autonomous-runner.yml').read_text()
CONSOLE = (ROOT / 'apps/console/lib/intake-worker-wake.ts').read_text()
PROBE = (ROOT / 'src/ai_product_factory/schedule_probe.py').read_text()


def job(name: str) -> str:
    found = re.search(r'^  ' + re.escape(name) + r':\s*$', RUNNER, re.M)
    if not found:
        raise AssertionError('missing job: ' + name)
    nxt = re.search(r'^  [a-z][a-z0-9-]*:\s*$', RUNNER[found.end():], re.M)
    return RUNNER[found.start():found.end() + nxt.start()] if nxt else RUNNER[found.start():]


class EventDrivenContinuityContract(unittest.TestCase):
    def test_console_produces_existing_real_events_not_start_or_paid_bypass(self):
        self.assertIn('/actions/workflows/autonomous-runner.yml/dispatches', CONSOLE)
        self.assertIn('requestFactoryIntakeWakeViaGitHubApp', CONSOLE)
        self.assertIn('event_type:"factory-intake-wake"',
                      (ROOT / 'apps/console/lib/github-app.ts').read_text())
        self.assertNotIn('merge_pull_request', CONSOLE)
        self.assertNotIn('FACTORY_PRIMARY_MODEL_ENABLED=true', CONSOLE)

    def test_direct_runs_only_after_actual_dispatch_has_claimed_work(self):
        lane = job('direct')
        self.assertIn("needs.dispatch.result == 'success'", lane)
        self.assertIn("needs.dispatch.outputs.direct_count != '0'", lane)
        self.assertIn("github.event_name == 'workflow_dispatch'", lane)
        self.assertNotIn("github.event_name == 'workflow_dispatch' && inputs.run_direct == true", lane)
        self.assertIn('FACTORY_PRIMARY_MODEL_ENABLED', lane)
        self.assertIn('FACTORY_GITHUB_TOKEN', lane)

    def test_codex_does_not_require_manual_flag_for_previously_authorized_queue(self):
        lane = job('codex')
        self.assertIn("needs.dispatch.outputs.codex_count != '0'", lane)
        self.assertIn("vars.FACTORY_CODEX_ENABLED == 'true'", lane)
        self.assertIn("github.event_name == 'workflow_dispatch'", lane)
        self.assertNotIn("github.event_name == 'workflow_dispatch' && inputs.run_codex == true", lane)

    def test_codex_manual_cannot_materialize_work_without_probe_or_claim(self):
        lane = job('codex-manual')
        self.assertIn("needs.schedule-probe.result == 'success'", lane)
        self.assertIn("needs.schedule-probe.outputs.codex_manual_work == 'true'", lane)
        self.assertIn("needs.dispatch.outputs.codex_count != '0'", lane)
        self.assertIn("github.event_name == 'workflow_dispatch'", lane)

    def test_preview_reconciles_queue_on_authenticated_workflow_dispatch(self):
        lane = job('preview')
        self.assertIn("needs.schedule-probe.result == 'success'", lane)
        self.assertIn("needs.schedule-probe.outputs.preview_work == 'true'", lane)
        self.assertIn("github.event_name == 'workflow_dispatch'", lane)
        self.assertNotIn("github.event_name == 'workflow_dispatch' && inputs.run_preview == true", lane)
        self.assertIn('--mode preview-probe', lane)
        self.assertIn('FACTORY_PREVIEW_EXPECTED_SHA', lane)

    def test_manual_read_only_audits_remain_isolated_from_paid_lanes(self):
        probe = job('schedule-probe')
        for marker in ('inputs.run_journey_audit != true',
                       'inputs.run_offline_preflight != true',
                       'inputs.run_admission_diagnosis != true'):
            self.assertIn(marker, probe)
        for lane in ('direct','codex','preview'):
            self.assertIn("(github.event_name != 'workflow_dispatch' || inputs.run_alerts != true)", job(lane))

    def test_independent_queue_read_reuses_existing_authority_but_never_forges_heartbeat(self):
        self.assertIn('def probe(self, *, record_telemetry: bool = True)', PROBE)
        self.assertIn('if record_telemetry else False', PROBE)
        self.assertIn('if record_telemetry and os.environ.get("GITHUB_EVENT_NAME") == "schedule"', PROBE)

    def test_normal_runner_still_preserves_owner_start_and_human_release(self):
        self.assertIn('  owner-start:', RUNNER)
        self.assertIn('  release-followup:', RUNNER)
        self.assertIn('  schedule:', RUNNER)  # temporary fallback; no abrupt removal
        self.assertIn("github.event.comment.author_association == 'OWNER'", RUNNER)
        self.assertNotIn('auto-merge', job('direct').lower())


if __name__ == '__main__':
    unittest.main()