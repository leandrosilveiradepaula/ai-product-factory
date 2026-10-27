"""Prevent an obsolete standalone Service Desk recovery from becoming an active runbook."""
from __future__ import annotations

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RetiredGreenfieldRunbookTests(unittest.TestCase):
    def read(self, name: str) -> str:
        return (ROOT / name).read_text(encoding="utf-8")

    def test_retired_run_has_no_actionable_cli_invocation(self):
        runbook = self.read("docs/PREVIEW_BACKEND_RECOVERY.md")
        self.assertIn("27/10/2026", runbook.split("## Why this exists", 1)[0])
        self.assertIn("NÃO EXECUTAR", runbook)
        self.assertIn("FINALIZATION_EXECUTION_CONTRACT.md", runbook)
        self.assertNotIn("--project-key infodive-service-desk", runbook)
        self.assertNotIn("--run-id 52998a8f-b478-46b3-9529-08bea72034f3", runbook)
        self.assertNotIn("--execute --ack-environment-authorized", runbook)
        for block in re.findall(r"(?ms)^```(?:bash|sh|shell)?\s*\n(.*?)^```", runbook):
            self.assertNotIn("infodive-service-desk", block)
            self.assertNotIn("52998a8f-b478-46b3-9529-08bea72034f3", block)

    def test_current_operations_and_manual_start_are_fail_closed(self):
        ops = self.read("docs/OPERATIONS.md")
        manual = self.read("docs/MANUAL_PROJECT_EXECUTION_OPERATIONS.md")
        self.assertIn("27/10/2026", ops[:450])
        self.assertIn("Service Desk standalone foi aposentado", ops[:1200])
        self.assertIn("27/10/2026", manual[:500])
        self.assertIn("CRM Infodive", manual[:1100])
        self.assertNotIn("verify a real user journey in a separate isolated project", manual)

    def test_readme_pilot_priority_is_current(self):
        readme = self.read("README.md")
        self.assertIn("## Piloto prioritário de certificação", readme)
        self.assertIn("leandrosilveiradepaula/crm-infodive", readme)
        self.assertIn("Service Desk é módulo", readme)
        self.assertIn("63 perguntas", readme)


class CurrentBootstrapContractTests(unittest.TestCase):
    def test_readme_documents_both_shells_and_src_layout(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("export PYTHONPATH=src", text)
        self.assertIn('$env:PYTHONPATH = "src"', text)
        self.assertIn("Python 3.11+", text)
        self.assertIn("python scripts/check_test_collection.py", text)
        self.assertIn("não acessam Supabase", text)

    def test_documented_offline_cli_commands_work_from_checkout(self):
        import json
        import os
        import subprocess
        import sys
        env = {"PATH": os.environ.get("PATH", ""),
               "PYTHONPATH": str(ROOT / "src"),
               "PYTHONDONTWRITEBYTECODE": "1"}
        samples = [
            (["validate", "config/factory.example.json"], "valid", True),
            (["codex-decision", "--complexity", "high", "--files", "20", "--deep-debug"], "should_use", True),
        ]
        for args, field, expected in samples:
            with self.subTest(command=args[0]):
                output = subprocess.run(
                    [sys.executable, "-m", "ai_product_factory.cli", *args],
                    cwd=ROOT, env=env, capture_output=True, text=True, timeout=12,
                )
                self.assertEqual(output.returncode, 0, output.stderr[:300])
                self.assertEqual(json.loads(output.stdout)[field], expected)


if __name__ == "__main__":
    unittest.main()
