"""Negative and positive offline README setup exercise tests."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.exercise_block1_setup import exercise

ROOT = Path(__file__).resolve().parents[1]


class Block1SetupExerciseTests(unittest.TestCase):
    def test_documented_commands_execute_without_credentials(self):
        result = exercise(ROOT)
        self.assertTrue(result["all_succeeded"], result["commands"])
        self.assertEqual(len(result["commands"]), 2)
        self.assertFalse(result["product_ready"])
        self.assertEqual(result["paid_calls"], 0)
        self.assertEqual(result["writes_to_production"], 0)

    def test_readme_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("not the documented setup", encoding="utf-8")
            with self.assertRaises(ValueError):
                exercise(root)

    def test_subprocess_does_not_inherit_secrets(self):
        with patch("scripts.exercise_block1_setup.subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = "ok"
            exercise(ROOT)
            self.assertEqual(run.call_count, 2)
            for call in run.call_args_list:
                env = call.kwargs["env"]
                self.assertEqual(set(env), {"PATH", "PYTHONPATH", "PYTHONDONTWRITEBYTECODE"})
                self.assertNotIn("OPENAI_API_KEY", env)
                self.assertNotIn("SUPABASE_SECRET_KEY", env)


if __name__ == "__main__":
    unittest.main()
