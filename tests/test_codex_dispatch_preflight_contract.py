"""Fail-closed independent automatic Codex routing; zero paid invocations."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
WORKFLOW=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
PY=(ROOT/"src/ai_product_factory/runtime_cli.py").read_text()

class CodexPreflightContractTests(unittest.TestCase):
    def test_preflight_uses_only_protected_codex_environment(self):
        pre=WORKFLOW.split("\n  codex-route-preflight:\n",1)[1]
        self.assertIn("environment: openai-codex",pre)
        self.assertIn("vars.FACTORY_CODEX_ENABLED == 'true'",pre)
        self.assertIn("needs.schedule-probe.outputs.dispatch_work == 'true'",pre)
        self.assertIn("OPENAI_FEDERATION_RULE_ID:",pre)
        self.assertIn("OPENAI_WIF_AUDIENCE:",pre)
        self.assertIn("CODEX_ACCESS_TOKEN:",pre)
        self.assertIn("FACTORY_GITHUB_TOKEN:",pre)
        self.assertIn('ready=false',pre)
        self.assertIn('echo "ready=$ready" >> "$GITHUB_OUTPUT"',pre)
        self.assertNotIn("codex exec",pre)
        self.assertNotIn("OPENAI_API_KEY:",pre)

    def test_dispatch_only_receives_boolean_without_credentials(self):
        dispatch=WORKFLOW.split("\n  dispatch:\n",1)[1].split("\n  direct:\n",1)[0]
        self.assertIn("codex-route-preflight",dispatch)
        self.assertIn("needs.codex-route-preflight.outputs.ready == 'true'",dispatch)
        self.assertIn("FACTORY_DISPATCH_CODEX_READY:",dispatch)
        self.assertNotIn("CODEX_ACCESS_TOKEN:",dispatch)
        self.assertNotIn("OPENAI_FEDERATION_RULE_ID:",dispatch)
        self.assertNotIn("OPENAI_API_KEY:",dispatch)

    def test_codex_runtime_supports_official_token_but_never_partial_wif_fallback(self):
        before=PY.split("def require_codex_runtime_enabled()",1)[1].split("\ndef build_handler(",1)[0]
        self.assertIn('os.getenv("FACTORY_CODEX_ENABLED")!="true"',before)
        self.assertIn('elif not os.getenv("CODEX_ACCESS_TOKEN","").strip()',before)
        self.assertIn('os.path.isfile(os.environ["OPENAI_IDENTITY_TOKEN_FILE"])',before)
        self.assertIn('FACTORY_GITHUB_TOKEN',before)
        dispatch=PY.split("def allowed_dispatch_routes()",1)[1].split("\ndef run_dispatch_once(",1)[0]
        self.assertNotIn('enabled.append("codex")\n elif (os.getenv("FACTORY_CODEX_ENABLED")',dispatch)
        self.assertIn('os.getenv("FACTORY_CODEX_ENABLED")!="true"',dispatch)
        self.assertNotIn('require_paid_runtime_budget()',dispatch)
        self.assertNotIn('CODEX_ACCESS_TOKEN',dispatch)

if __name__=="__main__":
    unittest.main()
