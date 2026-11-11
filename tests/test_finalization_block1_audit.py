"""Negative, offline contract tests for the Block 1 inventory (not certification)."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "audit_finalization_block1", ROOT / "scripts" / "audit_finalization_block1.py"
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)
SHA = "a" * 40


class Block1AuditTests(unittest.TestCase):
    def test_all_nine_criteria_are_explicitly_non_certifying(self):
        report = module.audit(ROOT, sha=SHA)
        self.assertEqual(report["scope"], "block1_source_inventory_not_certification")
        self.assertEqual(len(report["criteria"]), 9)
        self.assertFalse(report["product_ready"])
        self.assertEqual(report["certified_criteria"], 0)
        self.assertFalse(report["independent_execution_proof"])
        self.assertEqual(report["writes_to_production"], 0)
        self.assertEqual(report["paid_calls"], 0)
        self.assertTrue(all(v["status"] in ("partial", "missing")
                            and v["independent_pass"] is False
                            for v in report["criteria"].values()))

    def test_missing_required_source_is_not_a_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src" / "ai_product_factory").mkdir(parents=True)
            result = module.audit(root, sha=SHA)
            self.assertEqual(result["criteria"]["security/authn_authz"]["status"], "missing")
            self.assertEqual(result["criteria"]["documentation/operations"]["status"], "missing")
            self.assertEqual(result["criteria"]["test_strategy/regression_gates"]["status"], "missing")

    def test_invalid_sha_and_symlinked_document_are_rejected(self):
        for invalid in ("a" * 39, "A" * 40, "z" * 40, SHA + "\n"):
            with self.subTest(sha=invalid), self.assertRaises(ValueError):
                module.audit(ROOT, sha=invalid)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src" / "ai_product_factory").mkdir(parents=True)
            try:
                (root / "README.md").symlink_to(ROOT / "README.md")
            except OSError as exc:
                self.skipTest("symlink creation is not permitted by this Windows host: " + str(exc.winerror))
            report = module.audit(root, sha=SHA)
            self.assertEqual(report["criteria"]["documentation/setup_configuration"]["status"], "missing")

    def test_source_inventory_does_not_leak_secret_values(self):
        report = module.audit(ROOT, sha=SHA)
        payload = json.dumps(report)
        self.assertNotIn("OPENAI_API_KEY=", payload)
        self.assertNotIn("SUPABASE_SECRET_KEY=", payload)
        self.assertEqual(sorted(report["source_digests"]), list(report["source_digests"]))
        self.assertTrue(all(len(value) == 64 for value in report["source_digests"].values()))

    def test_source_marker_scanner_detects_negative_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src" / "ai_product_factory"
            src.mkdir(parents=True)
            (src / "simulation.py").write_text("dry_run = True\n", encoding="utf-8")
            report = module.audit(root, sha=SHA)
            self.assertEqual(report["simulation_marker_paths"], ["src/ai_product_factory/simulation.py"])
            self.assertEqual(report["criteria"]["functional_completeness/mock_noop_demo_inventory"]["status"], "partial")


if __name__ == "__main__":
    unittest.main()
