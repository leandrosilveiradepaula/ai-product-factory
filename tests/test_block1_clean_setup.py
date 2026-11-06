"""Negative tests of non-root, credentialless documented setup policy."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("block1_clean_setup", ROOT / "scripts/exercise_block1_clean_setup.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
ENV = {"PATH": "/usr/bin:/bin", "HOME": "/tmp", "PYTHONPATH": str(ROOT / "src"),
       "PYTHONDONTWRITEBYTECODE": "1"}


class CleanSetupContracts(unittest.TestCase):
    def test_non_root_credentials_are_required_to_be_absent(self):
        for user_id, env in (
            (0, ENV),
            (65534, dict(ENV, OPENAI_API_KEY="not-a-real-secret")),
            (65534, dict(ENV, GITHUB_TOKEN="not-a-real-secret")),
            (65534, dict(ENV, SUPABASE_SECRET_KEY="not-a-real-secret")),
            (65534, dict(ENV, PYTHONPATH="/wrong/src")),
        ):
            with self.subTest(user_id=user_id, env=list(env)):
                result = mod.exercise(ROOT, env, user_id)
                self.assertFalse(result["setup_commands_passed"])
                self.assertEqual(result["commands"], [])
                self.assertFalse(result["block1_certified"])

    def test_no_commands_are_executed_when_readme_contract_missing(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            new_root = Path(tmp)
            (new_root / "README.md").write_text("empty\n")
            env = dict(ENV, PYTHONPATH=str(new_root / "src"))
            result = mod.exercise(new_root, env, 65534)
            self.assertFalse(result["readme_commands_present"])
            self.assertEqual(result["commands"], [])
            self.assertFalse(result["setup_commands_passed"])

    def test_report_never_grants_certification(self):
        result = mod.exercise(ROOT, dict(ENV, OPENAI_API_KEY="not-a-real-secret"), 65534)
        self.assertFalse(result["documentation_setup_configuration_certified"])
        self.assertFalse(result["release_authorized"])
        self.assertEqual(result["paid_model_calls"], 0)


if __name__ == "__main__":
    unittest.main()
