"""Positive and negative contracts for remote-less Git rollback rehearsal."""
from pathlib import Path
import importlib.util
import unittest
from unittest.mock import patch
from types import SimpleNamespace

P = Path(__file__).resolve().parents[1] / "scripts/verify_block1_isolated_revert.py"
spec = importlib.util.spec_from_file_location("block1_revert", P)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class OfflineRevertTests(unittest.TestCase):
    def test_real_revert_restores_tree_without_release(self):
        result = mod.exercise()
        self.assertTrue(result["passed"])
        self.assertTrue(result["reverted_tree_equal_to_baseline"])
        self.assertTrue(result["production_human_gate_required"])
        self.assertTrue(result["no_git_remotes"])
        self.assertEqual(result["commit_count"], 3)
        self.assertFalse(result["production_rollback_executed"])
        self.assertFalse(result["block1_certified"])
        self.assertEqual(result["production_writes"], 0)
        self.assertEqual(result["paid_calls"], 0)

    def test_cannot_pass_an_existing_repository(self):
        with self.assertRaises(ValueError):
            mod.exercise(root=Path("."))

    def test_unsafe_policy_fails_before_any_git_work(self):
        with patch.object(mod, "evaluate_release", return_value=SimpleNamespace(
                may_release_autonomously=True, human_gate_required=False)):
            with self.assertRaisesRegex(RuntimeError, "production_human_gate_not_enforced"):
                mod.exercise()

    def test_failed_revert_cannot_certify(self):
        with patch.object(mod, "_git", side_effect=RuntimeError("git unavailable")):
            with self.assertRaisesRegex(RuntimeError, "git unavailable"):
                mod.exercise()


if __name__ == "__main__":
    unittest.main()
