from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PreviewPromotionWorkflowTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
