"""Real TSX status semantics must stay covered by unprivileged Console CI."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
UI=(ROOT/"apps/console/app/ui.tsx").read_text()
CI=(ROOT/".github/workflows/console.yml").read_text()
RUNTIME=(ROOT/"scripts/test_console_status_semantics.cjs").read_text()

class StatusSemanticsContract(unittest.TestCase):
    def test_actual_tsx_behavior_runs_in_console_ci_after_npm_ci(self):
        command="node ../../scripts/test_console_status_semantics.cjs"
        self.assertIn(command,CI)
        self.assertLess(CI.index("      - run: npm ci"),CI.index(command))
        self.assertIn("ts.transpileModule",RUNTIME)
        self.assertIn('apps/console/app/ui.tsx',RUNTIME)
        self.assertIn("StatusPill({status",RUNTIME)
        self.assertNotIn("fetch(",RUNTIME)

    def test_unknown_or_negated_status_never_uses_substring_success(self):
        self.assertIn("successStatuses.has(value)",UI)
        self.assertNotIn('value.includes(token)',UI)
        for value in ("inactive","unhealthy","not_ready","not_verified",
                      "provider_status_success_unverified","not_applicable"):
            self.assertIn('"'+value+'"',UI)
            self.assertIn('"'+value+'"',RUNTIME)

    def test_accessible_custom_label_does_not_hide_raw_state(self):
        self.assertIn("aria-label={spokenLabel}",UI)
        self.assertIn("tone===\"success\"&&inferred!==\"success\"",UI)
        self.assertIn("custom visible labels preserve underlying state",RUNTIME)

if __name__=="__main__":
    unittest.main()
