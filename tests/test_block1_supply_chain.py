"""Supply-chain audit negative contracts without network or secrets."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("supply_audit", ROOT / "scripts" / "audit_block1_supply_chain.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class SupplyChainAuditTests(unittest.TestCase):
    def fixture(self, root):
        (root / "apps" / "console").mkdir(parents=True)
        (root / ".github" / "workflows").mkdir(parents=True)
        (root / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
        (root / "apps" / "console" / "package.json").write_text(json.dumps({
            "dependencies": {"next": "15.5.28"}, "devDependencies": {}
        }), encoding="utf-8")
        (root / "apps" / "console" / "package-lock.json").write_text(json.dumps({
            "lockfileVersion": 3, "packages": {"": {"dependencies": {"next": "15.5.28"}},
            "node_modules/next": {"version": "15.5.28"}}
        }), encoding="utf-8")
        (root / ".github" / "workflows" / "test.yml").write_text(
            "steps:\n  - uses: actions/checkout@" + "a" * 40 + "\n", encoding="utf-8")

    def test_real_tree_does_not_claim_security_certification(self):
        report = mod.audit(ROOT)
        self.assertGreater(report["workflow_files_scanned"], 0)
        self.assertFalse(report["security_certified"])
        self.assertFalse(report["npm_dependency_advisory_verified"])
        self.assertFalse(report["independent_secret_scan_verified"])
        self.assertEqual(report["paid_calls"], 0)

    def test_pinned_fixture_and_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            self.assertTrue(mod.audit(root)["source_contracts_ok"])
            workflow = root / ".github" / "workflows" / "test.yml"
            workflow.write_text("steps:\n  - uses: actions/checkout@v4\n", encoding="utf-8")
            self.assertEqual(mod.audit(root)["unpinned_actions"], ["test.yml:actions/checkout"])
            workflow.write_text("steps:\n  - uses: actions/checkout@" + "a" * 40 +
                                "\n  - run: echo ok\n  OPENAI_API_KEY: literal-secret\n", encoding="utf-8")
            report = mod.audit(root)
            self.assertEqual(report["credential_assignment_candidates"], ["test.yml"])
            self.assertNotIn("literal-secret", json.dumps(report))
            pkg = root / "apps" / "console" / "package.json"
            pkg.write_text(json.dumps({"dependencies": {"next": "16.0.0"}}), encoding="utf-8")
            self.assertFalse(mod.audit(root)["source_contracts_ok"])
            self.assertTrue(mod.audit(root)["manifest_lock_drift"])

    def test_missing_lockfile_and_symlink_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            (root / "apps" / "console" / "package-lock.json").unlink()
            with self.assertRaises(ValueError):
                mod.audit(root)
            (root / "apps" / "console" / "package-lock.json").symlink_to(
                ROOT / "apps" / "console" / "package-lock.json")
            with self.assertRaises(ValueError):
                mod.audit(root)


if __name__ == "__main__":
    unittest.main()
