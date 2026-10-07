import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]


class PreviewBrowserScriptContractTests(unittest.TestCase):
    def test_script_uses_exact_runtime_preview_url(self):
        text=(ROOT/"scripts/verify_preview.mjs").read_text()
        self.assertIn("process.env.FACTORY_PREVIEW_URL",text)
        self.assertIn("page.goto(previewUrl",text)
        self.assertIn('emit("success"',text)
        self.assertIn('emit("failure"',text)

    def test_scheduled_preview_job_self_hosts_playwright_only_when_needed(self):
        text=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
        preview=text.split("\n  preview:",1)[1].split("\n  alerts:",1)[0]
        self.assertIn("inputs.run_preview == true",preview)
        self.assertIn("github.event_name == 'schedule'",preview)
        self.assertIn("--mode preview-probe",preview)
        self.assertIn("steps.preview_probe.outputs.browser == 'true'",preview)
        self.assertIn("checks: read",preview)
        self.assertIn("playwright@1.63.0",preview)
        self.assertIn('FACTORY_BROWSER_EVIDENCE_ENABLED: "true"',preview)
        self.assertIn("scripts/verify_preview.mjs",preview)
        self.assertNotIn("contents: write",preview)
        self.assertNotIn("pull-requests: write",preview)

    def test_exact_preview_push_is_scoped_to_console_changes(self):
        text=(ROOT/".github/workflows/exact-preview-browser-evidence.yml").read_text()
        push=text.split("  push:",1)[1].split("  workflow_dispatch:",1)[0]
        self.assertIn('paths:',push)
        self.assertIn('- "apps/console/**"',push)

    def test_vercel_preview_ignore_command_matches_console_only_policy(self):
        text=(ROOT/"apps/console/vercel.json").read_text()
        self.assertIn('preview/*) git diff --quiet HEAD^ HEAD ./',text)
        self.assertNotIn('preview/*) exit 1',text)
        self.assertIn('../../config/factory.release-policy.v1.json',text)


if __name__=="__main__":unittest.main()
