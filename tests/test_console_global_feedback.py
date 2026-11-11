"""Contract checks for safe global Console loading and error feedback."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ConsoleGlobalFeedbackTests(unittest.TestCase):
    def test_root_loading_state_is_announced_without_claiming_success(self):
        source = (ROOT / "apps/console/app/loading.tsx").read_text(encoding="utf-8")
        self.assertIn('role="status"', source)
        self.assertIn('aria-live="polite"', source)
        self.assertIn("Control Plane", source)
        self.assertNotIn("conclu", source.lower())

    def test_root_error_state_is_retryable_and_redacts_render_error(self):
        source = (ROOT / "apps/console/app/error.tsx").read_text(encoding="utf-8")
        self.assertIn('"use client"', source)
        self.assertIn('role="alert"', source)
        self.assertIn('aria-live="assertive"', source)
        self.assertIn("onClick={reset}", source)
        self.assertIn("console_route_render_failed", source)
        self.assertNotIn("error.message", source)
        self.assertNotIn("error.stack", source)


if __name__ == "__main__":
    unittest.main()
