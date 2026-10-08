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
        self.assertIn("PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD",preview)
        self.assertIn("FACTORY_BROWSER_EXECUTABLE_PATH: /usr/bin/google-chrome",preview)
        self.assertNotIn("playwright install --with-deps",preview)
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


    def test_trusted_browser_verifier_is_manual_only_and_requires_url(self):
        workflow=(ROOT/".github/workflows/console-browser-evidence.yml").read_text()

        self.assertIn("workflow_dispatch:",workflow)
        self.assertNotIn("\n  push:",workflow)
        self.assertIn("preview_url:",workflow)
        self.assertIn("required: true",workflow)
        self.assertNotIn(".github/preview-target.json",workflow)
        self.assertNotIn("candidate_sha",workflow)


    def test_trusted_browser_verifier_uses_preinstalled_system_chrome(self):
        workflow=(ROOT/".github/workflows/console-browser-evidence.yml").read_text()
        script=(ROOT/"scripts/verify_preview.mjs").read_text()

        self.assertIn('PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD: "1"',workflow)
        self.assertIn('FACTORY_BROWSER_EXECUTABLE_PATH: /usr/bin/google-chrome',workflow)
        self.assertIn('test -x /usr/bin/google-chrome',workflow)
        self.assertNotIn('playwright install --with-deps',workflow)
        self.assertIn('process.env.FACTORY_BROWSER_EXECUTABLE_PATH',script)
        self.assertIn('executablePath: browserExecutablePath',script)

    def test_browser_gate_stays_fail_closed_when_system_chrome_is_missing(self):
        workflow=(ROOT/".github/workflows/console-browser-evidence.yml").read_text()
        autonomous=(ROOT/".github/workflows/autonomous-runner.yml").read_text()

        self.assertIn('test -x /usr/bin/google-chrome',workflow)
        self.assertIn('test -x "$FACTORY_BROWSER_EXECUTABLE_PATH"',autonomous)
        self.assertNotIn('|| true',workflow.split('test -x /usr/bin/google-chrome',1)[1].splitlines()[0])


if __name__=="__main__":unittest.main()
