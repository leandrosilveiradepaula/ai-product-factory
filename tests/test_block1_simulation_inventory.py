"""Offline negative tests for the runtime simulation-marker inventory."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("block1_simulation_inventory",
                                              ROOT / "scripts" / "inventory_block1_simulation_paths.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class SimulationInventoryTests(unittest.TestCase):
    def test_current_tree_does_not_claim_reachability_proof(self):
        report = mod.inventory(ROOT)
        self.assertGreater(report["source_files"], 0)
        self.assertEqual(len(report["fingerprint"]), 64)
        self.assertFalse(report["independent_pass"])
        self.assertFalse(report["production_ready"])
        self.assertEqual(report["paid_calls"], 0)
        self.assertEqual(report["writes_to_production"], 0)
        self.assertTrue(all(set(row) == {"path", "line", "kinds"} for row in report["locations"]))

    def test_deterministic_and_no_secret_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src" / "ai_product_factory"
            src.mkdir(parents=True)
            (src / "runtime.py").write_text(
                'API_KEY = "do_not_print"\n'
                'dry_run = True\n'
                '# demo fallback\n'
                'fixture = None\n', encoding="utf-8")
            first = mod.inventory(root)
            second = mod.inventory(root)
            self.assertEqual(first, second)
            self.assertEqual(first["marker_occurrences_by_line"], 3)
            self.assertEqual([x["line"] for x in first["locations"]], [2, 3, 4])
            self.assertNotIn("do_not_print", str(first))

    def test_symlink_and_invalid_python_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src" / "ai_product_factory"
            src.mkdir(parents=True)
            (src / "runtime.py").write_text("def invalid(\n", encoding="utf-8")
            with self.assertRaises(SyntaxError):
                mod.inventory(root)
            (src / "runtime.py").unlink()
            try:
                (src / "runtime.py").symlink_to(ROOT / "src" / "ai_product_factory" / "__init__.py")
            except OSError as exc:
                self.skipTest(f"symlink creation unavailable: {exc.winerror if hasattr(exc, 'winerror') else exc}")
            with self.assertRaises(ValueError):
                mod.inventory(root)

    def test_missing_tree_rejected(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
            mod.inventory(Path(tmp))


if __name__ == "__main__":
    unittest.main()
