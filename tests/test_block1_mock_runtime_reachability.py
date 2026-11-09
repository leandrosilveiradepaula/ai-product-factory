import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("mock_reachability", ROOT / "scripts" / "audit_block1_mock_runtime_reachability.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RuntimeSimulationReachabilityTests(unittest.TestCase):
    def write(self, root, relative, value):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")

    def test_current_runtime_marks_only_explicit_rejection_guards(self):
        report = module.audit(ROOT)
        self.assertIn("runtime_cli", report["reachable_modules"])
        self.assertFalse(report["simulation_can_authorize_release"])
        self.assertFalse(report["independent_pass"])
        self.assertFalse(report["functional_completeness_certified"])
        self.assertEqual(report["unclassified_runtime_markers"], [])

    def test_unclassified_marker_in_runtime_import_closure_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write(root, "src/ai_product_factory/runtime_cli.py", "from .worker import execute\n")
            self.write(root, "src/ai_product_factory/worker.py", "MODE = 'demo'\n")
            report = module.audit(root)
            self.assertEqual(report["unclassified_runtime_markers"][0]["constant"], "MODE")

    def test_unrelated_raise_does_not_make_simulation_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write(root, "src/ai_product_factory/runtime_cli.py", "from .worker import execute\n")
            self.write(root, "src/ai_product_factory/worker.py",
                       "BAD = {'mock'}\ndef execute(x):\n if x == 'invalid': raise ValueError('invalid')\n return x in BAD\n")
            report = module.audit(root)
            self.assertEqual([row["constant"] for row in report["unclassified_runtime_markers"]], ["BAD"])
            self.assertFalse(report["independent_pass"])

    def test_raise_in_else_does_not_certify_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write(root, "src/ai_product_factory/runtime_cli.py", "from .worker import execute\n")
            self.write(root, "src/ai_product_factory/worker.py",
                       "BAD = {'mock'}\ndef execute(x):\n if x in BAD:\n  return 'accepted'\n else:\n  raise ValueError('unrelated')\n")
            report = module.audit(root)
            self.assertEqual(len(report["unclassified_runtime_markers"]), 1)

    def test_nested_raise_does_not_certify_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write(root, "src/ai_product_factory/runtime_cli.py", "from .worker import execute\n")
            self.write(root, "src/ai_product_factory/worker.py",
                       "BAD = {'demo'}\ndef execute(x):\n if x in BAD:\n  def unrelated():\n   raise ValueError('unused')\n  return True\n")
            report = module.audit(root)
            self.assertEqual(len(report["unclassified_runtime_markers"]), 1)

    def test_marker_with_raise_is_classified_as_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write(root, "src/ai_product_factory/runtime_cli.py", "from .worker import execute\n")
            self.write(root, "src/ai_product_factory/worker.py", "BAD = {'mock'}\ndef execute(x):\n if x in BAD: raise ValueError('blocked')\n")
            report = module.audit(root)
            self.assertEqual(report["unclassified_runtime_markers"], [])
