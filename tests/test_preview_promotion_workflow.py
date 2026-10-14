from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PreviewPromotionWorkflowTests(unittest.TestCase):
    def test_provider_rate_limit_observed_before_consuming_preview_quota(self):
        workflow=(ROOT/".github/workflows/promote-preview-candidate.yml").read_text()
        self.assertIn("statuses: read",workflow)
        self.assertIn("python -m scripts.preview_provider_cooldown",workflow)
        self.assertLess(workflow.index("python -m scripts.preview_provider_cooldown"),workflow.index("python -m scripts.preview_budget_guard"))

    def test_budget_guard_is_invoked_as_module(self):
        workflow = (ROOT / ".github/workflows/promote-preview-candidate.yml").read_text()
        self.assertIn("python -m scripts.preview_budget_guard", workflow)

    def test_summary_does_not_use_shell_command_substitution(self):
        workflow = (ROOT / ".github/workflows/promote-preview-candidate.yml").read_text()
        self.assertIn("printf '%s\\n' \"- candidate: ${CANDIDATE_SHA:-n/a}\"", workflow)
        self.assertIn("printf '%s\\n' \"- action: $action\"", workflow)
        self.assertNotIn('echo "- candidate: `$CANDIDATE_SHA`"', workflow)
        self.assertNotIn('echo "- action: `$action`"', workflow)

    def test_budget_guard_supports_direct_execution_imports(self):
        guard = (ROOT / "scripts/preview_budget_guard.py").read_text()
        self.assertIn("if __package__:", guard)
        self.assertIn("from collect_vercel_usage import list_team_deployments", guard)
        self.assertIn("from vercel_preview_guard import evaluate_quota", guard)

    def test_console_validation_can_auto_promote_only_console_changes(self):
        workflow = (ROOT / ".github/workflows/promote-preview-candidate.yml").read_text()
        self.assertIn('workflow_run:', workflow)
        self.assertIn('workflows: ["Console validation"]', workflow)
        self.assertIn('github.event.workflow_run.event == \'pull_request\'', workflow)
        self.assertIn('startsWith("apps/console/")', workflow)
        self.assertIn('promotion_action", "not_applicable"', workflow)
        self.assertIn('github.event_name == \'workflow_dispatch\'', workflow)

    def test_automatic_draft_is_not_applicable_without_deployment(self):
        workflow=(ROOT/".github/workflows/promote-preview-candidate.yml").read_text()
        resolve=workflow.split("      - name: Resolve exact candidate and Preview applicability",1)[1].split("      - name: Verify exact PR candidate",1)[0]
        self.assertIn('if (!manual && pr.state === "open" && pr.draft &&',resolve)
        self.assertIn('pr.head?.sha === sha',resolve)
        self.assertIn('promotion_action", "not_applicable_draft"',resolve)
        self.assertIn('core.setOutput("applicable", "false")',resolve)
        self.assertIn('core.setOutput("source", "automatic")',resolve)
        self.assertLess(resolve.index('not_applicable_draft'),resolve.index('if (pr.state !== "open" || pr.draft'))
        self.assertIn('return core.setFailed("candidate must be an open, non-draft',resolve)
        # A skipped resolve must not reach quota checks, ref mutation or browser dispatch.
        self.assertIn("if: steps.resolve.outputs.applicable == 'true'",workflow)
        self.assertIn("if: steps.resolve.outputs.applicable == 'true' && steps.verify.outputs.needs_promotion == 'true'",workflow)

    def test_manual_and_automatic_preview_require_same_pr_eligibility(self):
        workflow=(ROOT/".github/workflows/promote-preview-candidate.yml").read_text()
        resolve=workflow.split("      - name: Resolve exact candidate and Preview applicability",1)[1].split("      - name: Verify exact PR candidate",1)[0]
        self.assertIn('const manual = context.eventName === "workflow_dispatch"',resolve)
        self.assertIn('pr = requested;',resolve)
        self.assertIn('pr.state !== "open" || pr.draft',resolve)
        self.assertIn('pr.base?.ref !== "main"',resolve)
        self.assertIn('pr.base?.repo?.full_name !== fullRepo',resolve)
        self.assertIn('pr.head?.repo?.full_name !== fullRepo',resolve)
        self.assertIn('pr.head?.sha !== sha',resolve)
        self.assertIn('github.rest.pulls.listFiles',resolve)
        self.assertIn('startsWith("apps/console/")',resolve)
        self.assertIn('manual ? "manual" : "automatic"',resolve)
        self.assertNotIn('core.setOutput("applicable", "true");\\n              return;',resolve)

    def test_token_driven_promotion_dispatches_exact_browser_evidence(self):
        promote = (ROOT / ".github/workflows/promote-preview-candidate.yml").read_text()
        exact = (ROOT / ".github/workflows/exact-preview-browser-evidence.yml").read_text()
        self.assertIn("actions: write", promote)
        self.assertIn('workflow_id: "exact-preview-browser-evidence.yml"', promote)
        self.assertIn("Factory Preview browser evidence", promote)
        self.assertIn("createWorkflowDispatch", promote)
        self.assertIn("workflow_dispatch:", exact)
        self.assertIn('"evidence/preview/**"', exact)
        self.assertIn("Factory Preview browser evidence", exact)
        self.assertIn("statuses: write", exact)

    def test_initial_preview_ref_is_seeded_then_advanced_to_candidate(self):
        workflow = (ROOT / ".github/workflows/promote-preview-candidate.yml").read_text()
        self.assertIn("github.rest.git.getCommit", workflow)
        self.assertIn('commit.parents?.[0]?.sha', workflow)
        self.assertIn('github.rest.git.createRef({...context.repo, ref: "refs/" + ref, sha: seedSha})', workflow)
        self.assertIn("github.rest.git.updateRef({...context.repo, ref, sha, force: true})", workflow)
        self.assertIn('promotion_action", "created_then_updated"', workflow)
        self.assertNotIn('createRef({...context.repo, ref: "refs/" + ref, sha})', workflow)


    def test_revalidates_after_ci_poll_and_immediately_before_ref_write(self):
        workflow=(ROOT/".github/workflows/promote-preview-candidate.yml").read_text()
        verify=workflow.split("      - name: Verify exact PR candidate",1)[1].split("      - name: Block fresh Preview attempts",1)[0]
        promote=workflow.split("      - name: Create or update one preview ref",1)[1].split("      - name: Ensure exact Preview browser evidence",1)[0]
        self.assertLess(verify.index('if (!green)'),verify.index('const {data: fresh}'))
        self.assertLess(verify.index('const {data: fresh}'),verify.index('getRef({...context.repo, ref}') )
        self.assertIn('fresh.draft !== false',verify)
        self.assertIn('fresh.head?.sha !== sha',verify)
        self.assertIn('fresh.base?.ref !== "main"',verify)
        self.assertIn('promotion_action", "stale"',verify)
        self.assertIn("python -m scripts.preview_provider_cooldown",workflow)
        self.assertIn("python -m scripts.preview_budget_guard",workflow)
        self.assertIn('const {data: pr} = await github.rest.pulls.get(',promote)
        self.assertIn('pr.state !== "open" || pr.draft !== false',promote)
        self.assertIn('pr.base?.ref !== "main"',promote)
        self.assertIn('pr.base?.repo?.full_name !== fullRepo',promote)
        self.assertIn('pr.head?.repo?.full_name !== fullRepo',promote)
        self.assertIn('pr.head?.sha !== sha',promote)
        self.assertLess(promote.index('const {data: pr}'),promote.index('github.rest.git.updateRef'))
        self.assertLess(promote.index('const {data: checks}'),promote.index('github.rest.git.updateRef'))
        self.assertIn('c.head_sha === sha',promote)
        self.assertIn('skipped_stale',promote)
        self.assertIn('skipped_checks',promote)
        self.assertIn('skipped_no_console',promote)
        self.assertIn('github.rest.pulls.listFiles',promote)
        self.assertIn('startsWith("apps/console/")',promote)

    def test_browser_dispatch_is_strictly_after_confirmed_promotion_and_ref(self):
        workflow=(ROOT/".github/workflows/promote-preview-candidate.yml").read_text()
        browser=workflow.split("      - name: Ensure exact Preview browser evidence",1)[1].split("      - name: Record durable Preview promotion summary",1)[0]
        self.assertIn("steps.verify.outputs.promotion_action == 'reused'",browser)
        self.assertIn("steps.promote.outputs.promotion_action == 'updated'",browser)
        self.assertIn("steps.promote.outputs.promotion_action == 'created_then_updated'",browser)
        self.assertNotIn("promotion_action != 'stale'",browser)
        self.assertIn('pr.draft !== false',browser)
        self.assertIn('pr.head?.sha !== sha',browser)
        self.assertIn('previewRef.object.sha !== sha',browser)
        self.assertIn('skipped_ref_mismatch',browser)
        self.assertIn('skipped_stale',browser)
        self.assertLess(browser.index('github.rest.git.getRef'),browser.index('actions.createWorkflowDispatch'))
        self.assertLess(browser.index('const {data: pr}'),browser.index('actions.createWorkflowDispatch'))

    def test_privileged_event_and_permissions_not_expanded(self):
        workflow=(ROOT/".github/workflows/promote-preview-candidate.yml").read_text()
        trigger=workflow.split("\non:\n",1)[1].split("\npermissions:\n",1)[0]
        self.assertIn("workflow_dispatch:",trigger)
        self.assertIn("workflow_run:",trigger)
        self.assertNotIn("pull_request_target:",trigger)
        self.assertNotIn("ready_for_review",trigger)
        self.assertNotIn("issue_comment:",trigger)
        self.assertNotIn("schedule:",trigger)
        self.assertIn("    checks: read",workflow) if "    checks: read" in workflow else self.assertIn("  checks: read",workflow)
        self.assertIn("  pull-requests: read",workflow)
        self.assertIn("  actions: write",workflow)
        self.assertIn("  contents: write",workflow)



if __name__ == "__main__":
    unittest.main()
