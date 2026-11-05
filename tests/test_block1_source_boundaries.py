"""Adversarial tests for the source-boundary audit, no live credentials."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("block1_boundaries", ROOT / "scripts" / "audit_block1_source_boundaries.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SourceBoundaryTests(unittest.TestCase):
    def files(self):
        return {path: (ROOT / path).read_text(encoding="utf-8") for path in module.REQUIRED}

    def test_checked_out_source_has_expected_fail_closed_contracts(self):
        result = module.inspect_boundaries(self.files())
        self.assertTrue(result["all_source_contracts_present"], result["checks"])
        self.assertFalse(result["security_certified"])
        self.assertFalse(result["release_authorized"])
        self.assertEqual(result["paid_calls"], 0)

    def test_missing_file_and_empty_source_are_rejected(self):
        files = self.files()
        files.pop("src/ai_product_factory/github_auth.py")
        with self.assertRaises(ValueError):
            module.inspect_boundaries(files)
        files = self.files()
        files["src/ai_product_factory/github_auth.py"] = ""
        with self.assertRaises(ValueError):
            module.inspect_boundaries(files)

    def test_cross_repo_permission_guard_removal_fails(self):
        files = self.files()
        files["src/ai_product_factory/github_auth.py"] = files["src/ai_product_factory/github_auth.py"].replace(
            "raise PermissionError(", "raise RuntimeError("
        )
        result = module.inspect_boundaries(files)
        self.assertFalse(result["all_source_contracts_present"])
        self.assertFalse(result["checks"]["cross_repo_rejection"])
        self.assertFalse(result["security_certified"])

    def test_missing_baseline_and_ci_fail(self):
        files = self.files()
        files[".github/workflows/autonomous-runner.yml"] = files[".github/workflows/autonomous-runner.yml"].replace(
            "--require-verified-baseline", "--unsafe-no-baseline"
        )
        result = module.inspect_boundaries(files)
        self.assertFalse(result["checks"]["certifier_baseline_required"])
        self.assertFalse(result["all_source_contracts_present"])
        files = self.files()
        files[".github/workflows/validate.yml"] = files[".github/workflows/validate.yml"].replace(
            "  factory-acceptance:", "  disabled-acceptance:"
        )
        self.assertFalse(module.inspect_boundaries(files)["checks"]["ci_has_unit_and_acceptance"])

    def test_unparseable_auth_source_is_rejected(self):
        files = self.files()
        files["src/ai_product_factory/github_auth.py"] = "def bad(\n"
        with self.assertRaises(SyntaxError):
            module.inspect_boundaries(files)


if __name__ == "__main__":
    unittest.main()
