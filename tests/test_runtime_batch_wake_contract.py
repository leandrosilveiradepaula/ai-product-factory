"""Only deterministic existing lanes may drain more than one item per cron wake."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
WORKFLOW=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
CLI=(ROOT/"src/ai_product_factory/runtime_cli.py").read_text()


class RuntimeBatchWakeContracts(unittest.TestCase):
    def test_only_existing_deterministic_workers_get_bounded_batch(self):
        required=(
            "--mode ci --batch-items 3",
            "--mode release --batch-items 3",
            "--mode change-set-integration --batch-items 3",
            "--mode specialist --specialist-role security --batch-items 3",
            "--mode specialist --specialist-role qa --batch-items 3",
            "--mode specialist --specialist-role operations --batch-items 3",
        )
        for arg in required:
            with self.subTest(arg=arg):
                self.assertIn(arg,WORKFLOW)
        self.assertNotIn("--mode product --batch-items",WORKFLOW)
        self.assertNotIn("--mode direct --batch-items",WORKFLOW)
        self.assertNotIn("--mode codex --batch-items",WORKFLOW)
        self.assertNotIn("--mode preview --batch-items",WORKFLOW)

    def test_one_item_is_default_for_manual_cli_and_runtime_gates_remain(self):
        self.assertIn('p.add_argument("--batch-items",type=int,default=1)',CLI)
        self.assertIn('run_bounded_deterministic_lane("release"',CLI)
        self.assertIn('run_bounded_deterministic_lane("ci"',CLI)
        self.assertIn('run_bounded_deterministic_lane("specialist"',CLI)
        self.assertIn('run_bounded_deterministic_lane("change-set-integration"',CLI)
        self.assertIn("def run_release_once",CLI)
        self.assertIn("observe_manual_merge(session)",CLI)
        self.assertIn("require_primary_runtime_enabled()",CLI)


if __name__=="__main__":
    unittest.main()
