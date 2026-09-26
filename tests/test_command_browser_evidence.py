import json
import os
import subprocess
import unittest
from unittest.mock import patch

from ai_product_factory.command_browser_evidence import CommandBrowserEvidenceAdapter,CommandBrowserEvidenceConfig

class Tests(unittest.TestCase):
    def test_success_uses_exact_preview_url_and_structured_checks(self):
        seen={}
        def runner(argv,env,timeout):
            seen.update(argv=argv,url=env["FACTORY_PREVIEW_URL"],timeout=timeout)
            return 0,json.dumps({"status":"success","checks":["page_load","console_clean"],"preview_url":"https://spoof.invalid"}),""
        adapter=CommandBrowserEvidenceAdapter(CommandBrowserEvidenceConfig(("node","verify.mjs"),15),runner=runner)
        out=adapter.verify("https://preview.example")
        self.assertEqual(out.status,"success")
        self.assertEqual(out.preview_url,"https://preview.example")
        self.assertEqual(out.checks,("page_load","console_clean"))
        self.assertEqual(seen["argv"],("node","verify.mjs"))
        self.assertEqual(seen["url"],"https://preview.example")

    def test_nonzero_exit_becomes_failure_evidence(self):
        adapter=CommandBrowserEvidenceAdapter(CommandBrowserEvidenceConfig(("verify",)),runner=lambda a,e,t:(2,"","browser failed"))
        out=adapter.verify("https://preview.example")
        self.assertEqual(out.status,"failure")
        self.assertIn("browser failed",out.detail)

    def test_invalid_json_becomes_failure_evidence(self):
        adapter=CommandBrowserEvidenceAdapter(CommandBrowserEvidenceConfig(("verify",)),runner=lambda a,e,t:(0,"not-json",""))
        self.assertEqual(adapter.verify("https://preview.example").status,"failure")

    def test_timeout_becomes_failure_evidence(self):
        def runner(a,e,t): raise subprocess.TimeoutExpired(a,t)
        adapter=CommandBrowserEvidenceAdapter(CommandBrowserEvidenceConfig(("verify",)),runner=runner)
        self.assertEqual(adapter.verify("https://preview.example").status,"failure")

    def test_env_config_requires_json_argv(self):
        with patch.dict(os.environ,{"FACTORY_BROWSER_EVIDENCE_COMMAND_JSON":'["node","verify.mjs"]',"FACTORY_BROWSER_EVIDENCE_TIMEOUT_SECONDS":"30"},clear=True):
            cfg=CommandBrowserEvidenceConfig.from_env()
        self.assertEqual(cfg.argv,("node","verify.mjs"))
        self.assertEqual(cfg.timeout_seconds,30)

if __name__=="__main__": unittest.main()
