"""Fail-closed contracts for the OIDC visual evidence broker and Actions workflow."""
from pathlib import Path
import json
import unittest

ROOT=Path(__file__).resolve().parents[1]
BROKER=(ROOT/"supabase/functions/factory-visual-evidence-broker/index.ts").read_text()
WORKFLOW=(ROOT/".github/workflows/authenticated-visual-evidence.yml").read_text()
CAPTURE=(ROOT/"scripts/capture_authenticated_console.mjs").read_text()
TARGET=json.loads((ROOT/".github/authenticated-visual-target.json").read_text())

class VisualEvidenceBrokerRetryContract(unittest.TestCase):
    def test_oidc_identity_must_match_run_and_attempt_for_all_actions(self):
        self.assertIn('String(claims.run_id ?? "") !== String(workflowRunId)', BROKER)
        self.assertIn('String(claims.run_attempt ?? "") !== String(runAttempt)', BROKER)
        self.assertIn('error: "github_oidc_invalid"', BROKER)
        self.assertIn('error: "run_identity_mismatch"', BROKER)
        self.assertIn('return json(403', BROKER)
        self.assertIn('workflow_ref:', BROKER)
        self.assertIn('environment: "openai-api"', BROKER)

    def test_duplicate_run_checked_before_account_creation_and_no_upsert(self):
        provision=BROKER.split('if (action === "provision") {',1)[1].split('if (action === "captured")',1)[0]
        self.assertIn('runAttempt !== 1', provision)
        self.assertIn('error: "rerun_requires_new_workflow_run"', provision)
        self.assertIn('&select=workflow_run_id&limit=1', provision)
        self.assertIn('error: "duplicate_workflow_run"', provision)
        self.assertLess(provision.index('if (rows.length)'),provision.index('adminFetch("/auth/v1/admin/users"'))
        self.assertNotIn('resolution=merge-duplicates', BROKER)

    def test_error_responses_never_leak_jwt_or_database_body(self):
        self.assertIn('class BrokerFailure extends Error', BROKER)
        self.assertIn('new BrokerFailure(503, "broker_operation_failed")', BROKER)
        self.assertIn('return json(safe.status, { error: safe.code })', BROKER)
        self.assertNotIn('detail.slice(', BROKER)
        self.assertNotIn('detail: error instanceof Error', BROKER)

    def test_replay_is_blocked_before_browser_and_broker(self):
        head=WORKFLOW.split('- name: Reject reused GitHub run ID',1)[1]
        self.assertIn('GITHUB_RUN_ATTEMPT:-0', head)
        self.assertIn('Use a new workflow_dispatch', head)
        self.assertLess(WORKFLOW.index('Reject reused GitHub run ID'),WORKFLOW.index('Mint provisioning GitHub OIDC token'))
        for action in ('provision','captured','cleanup','expire'):
            self.assertIn('action:"'+action+'",workflowRunId:Number(process.env.GITHUB_RUN_ID),runAttempt:Number(process.env.GITHUB_RUN_ATTEMPT)',WORKFLOW)

    def test_cleanup_runs_even_if_captured_state_update_fails(self):
        section=WORKFLOW.split('if [ "$CAPTURE_OUTCOME" = "success" ]',1)[1]
        self.assertIn('capture_status=$?', section)
        self.assertIn('cleanup_status=$?', section)
        self.assertIn('if [ "$capture_status" -ne 0 ] || [ "$cleanup_status" -ne 0 ]', section)
        self.assertIn('await cleanupUser(userId);',BROKER)
        self.assertIn('Never report "expired"', BROKER)

    def test_durable_production_target_matches_verified_console_sha(self):
        self.assertEqual(TARGET["preview_url"],"https://ai-product-factory-console.vercel.app")
        self.assertEqual(TARGET["candidate_sha"],"34c614be92a544bb52c1b2634fc6c82b1be6d25e")
        self.assertIn(".github/authenticated-visual-target.json",WORKFLOW)
        self.assertIn('id-token: write',WORKFLOW)

    def test_authenticated_capture_fails_on_http_errors_and_mobile_overflow(self):
        self.assertIn('consoleErrors.length || pageErrors.length || badResponses.length',CAPTURE)
        self.assertIn('response.status() >= 400',CAPTURE)
        self.assertIn('{name:"configuration-mobile",path:"/configuration"}',CAPTURE)
        self.assertIn('layout.scrollWidth > layout.innerWidth + 2',CAPTURE)
        self.assertNotIn('body{overflow-x:hidden',CAPTURE)

if __name__=="__main__":
    unittest.main()
