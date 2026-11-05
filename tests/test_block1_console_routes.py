"""Adversarial tests for static Console API route classification."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("console_routes", ROOT / "scripts" / "audit_block1_console_routes.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class ConsoleRouteAuditTests(unittest.TestCase):
    def test_real_console_routes_are_inventory_only(self):
        report = mod.audit(ROOT)
        self.assertGreater(report["count"], 10)
        self.assertFalse(report["security_certified"])
        self.assertFalse(report["authenticated_negative_tests_executed"])
        self.assertEqual(report["paid_calls"], 0)
        self.assertEqual(report["writes"], 0)

    def test_missing_auth_origin_and_content_type_are_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            api = root / "apps" / "console" / "app" / "api"
            path = api / "danger" / "route.ts"
            path.parent.mkdir(parents=True)
            path.write_text("export async function POST(request:Request){return Response.json({ok:true})}",
                            encoding="utf-8")
            report = mod.audit(root)
            self.assertEqual(report["count"], 1)
            flags = report["blockers"][0]["flags"]
            self.assertIn("operator_guard_not_found", flags)
            self.assertIn("mutation_origin_guard_not_found", flags)
            self.assertIn("mutation_content_type_guard_not_found", flags)
            self.assertFalse(report["security_certified"])

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            api = root / "apps" / "console" / "app" / "api"
            api.mkdir(parents=True)
            (api / "route.ts").symlink_to(ROOT / "apps" / "console" / "app" / "api" / "health" / "route.ts")
            with self.assertRaises(ValueError):
                mod.audit(root)


if __name__ == "__main__":
    unittest.main()
