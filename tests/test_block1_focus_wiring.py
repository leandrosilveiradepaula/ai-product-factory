"""Required CI scope gate must use trusted PR BASE checker and real HEAD diff."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FocusGateWiring(unittest.TestCase):
    def test_validate_test_job_runs_gate_on_open_and_edit(self):
        workflow = (ROOT / ".github/workflows/validate.yml").read_text()
        self.assertIn("types: [opened, synchronize, reopened, edited, ready_for_review]", workflow)
        test_job = workflow.split("\n  test:\n", 1)[1].split("\n\n  factory-acceptance:", 1)[0]
        self.assertIn("Enforce exact-SHA B1-B4 Factory scope", test_job)
        self.assertLess(test_job.index("Enforce exact-SHA B1-B4 Factory scope"),
                        test_job.index("Unit tests"))
        self.assertIn("if: github.event_name == 'pull_request'", test_job)
        self.assertIn("fetch-depth: 0", test_job)
        self.assertIn("persist-credentials: false", test_job)
        self.assertIn('git -C "$ROOT" show "$FOCUS_BASE:scripts/check_block1_focus.py"', test_job)
        self.assertIn('test "$(git -C "$ROOT" rev-parse HEAD)" = "$FOCUS_HEAD"', test_job)
        self.assertIn('--base "$FOCUS_BASE" --head "$FOCUS_HEAD"', test_job)

    def test_guardian_is_not_a_certifier_or_cross_repo_writes(self):
        body = (ROOT / "scripts/check_block1_focus.py").read_text()
        self.assertIn('"certification_pass_claimed": False', body)
        self.assertIn('"production_release_authorized": False', body)
        self.assertIn('"cross_repo_writes_authorized": False', body)
        self.assertNotIn("merge_pull_request(", body)
        self.assertNotIn("POST /repos", body)

    def test_agent_instructions_and_pr_template_carry_same_boundary(self):
        agents = (ROOT / "AGENTS.md").read_text()
        template = (ROOT / ".github/PULL_REQUEST_TEMPLATE.md").read_text()
        contract = (ROOT / "docs/BLOCK1_FOCUS_CONTRACT.md").read_text()
        self.assertIn("CONTROLE EXECUTÁVEL DE FOCO B1–B4", agents)
        for key in ("Factory-Block:", "Factory-Criteria:",
                    "Factory-Acceptance:", "Factory-Cross-Repo:",
                    "Factory-Human-Gates:"):
            self.assertIn(key, template)
        self.assertIn("check_block1_focus.py", contract)
        self.assertIn("19", contract)


if __name__ == "__main__":
    unittest.main()
