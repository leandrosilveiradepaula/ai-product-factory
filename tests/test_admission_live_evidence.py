"""Owner-only, model-free operational evidence and safe target validation."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from ai_product_factory.admission_audit_trigger import main as trigger_main, resolve_target

ROOT=Path(__file__).resolve().parents[1]
R="945c0da5-f36f-46da-a454-072037a988a5"
CMD="/factory-admission-diagnose ai-product-factory "+R
OWNER={"FACTORY_EVENT_NAME":"issue_comment","FACTORY_AUTHOR_ASSOCIATION":"OWNER",
       "FACTORY_ISSUE_IS_PR":"false","FACTORY_COMMENT_BODY":CMD}
DISPATCH={"FACTORY_EVENT_NAME":"workflow_dispatch","FACTORY_ADMISSION_ENABLED":"true",
          "FACTORY_JOURNEY_ENABLED":"false","FACTORY_OFFLINE_ENABLED":"false",
          "FACTORY_DISPATCH_PROJECT_KEY":"ai-product-factory","FACTORY_DISPATCH_RUN_ID":R}

class AdmissionLiveEvidenceTests(TestCase):
    def test_exact_owner_comment_and_disjoint_manual_dispatch(self):
        self.assertEqual(resolve_target(OWNER),("ai-product-factory",R))
        self.assertEqual(resolve_target({**OWNER,"FACTORY_COMMENT_BODY":"/factory-admission-diagnose ai-product-factory"}),("ai-product-factory",""))
        self.assertEqual(resolve_target(DISPATCH),("ai-product-factory",R))

    def test_owner_only_and_issue_only(self):
        for role in ("NONE","CONTRIBUTOR","MEMBER","COLLABORATOR",""):
            with self.subTest(role=role),self.assertRaises(ValueError):
                resolve_target({**OWNER,"FACTORY_AUTHOR_ASSOCIATION":role})
        for pr in ("true","","unknown"):
            with self.subTest(pr=pr),self.assertRaises(ValueError):
                resolve_target({**OWNER,"FACTORY_ISSUE_IS_PR":pr})

    def test_strict_syntax_no_injection_or_accidental_wake(self):
        for body in (
            CMD+" ",CMD+"\n",CMD+";echo",CMD+"\n/factory-wake",
            CMD.replace("ai-product-factory","../not-factory"),
            CMD.replace(R,"NOTUUID"),CMD.replace(R,R.upper()),
            "/factory-wake", "/factory-offline-preflight ai-product-factory "+R,
        ):
            with self.subTest(body=body[:80]),self.assertRaises(ValueError):
                resolve_target({**OWNER,"FACTORY_COMMENT_BODY":body})
        for change in (
            {"FACTORY_ADMISSION_ENABLED":"false"},
            {"FACTORY_JOURNEY_ENABLED":"true"},
            {"FACTORY_OFFLINE_ENABLED":"true"},
            {"FACTORY_DISPATCH_PROJECT_KEY":"x;cat"},
            {"FACTORY_DISPATCH_RUN_ID":"wrong"},
            {"FACTORY_EVENT_NAME":"schedule"},
            {"FACTORY_EVENT_NAME":"repository_dispatch"},
        ):
            with self.subTest(change=change),self.assertRaises(ValueError):
                resolve_target({**DISPATCH,**change})

    def test_diagnostic_only_writes_bounded_safe_output_after_validation(self):
        with TemporaryDirectory() as tmp:
            target=Path(tmp)/"github-output"
            with patch.dict(os.environ,{**OWNER,"GITHUB_OUTPUT":str(target)},clear=True):
                self.assertEqual(trigger_main(),0)
            self.assertEqual(target.read_text(),
                "project_key=ai-product-factory\nrun_id="+R+"\n")
            target.unlink()
            with patch.dict(os.environ,{**OWNER,"GITHUB_OUTPUT":str(target),
                "FACTORY_AUTHOR_ASSOCIATION":"NONE"},clear=True):
                self.assertEqual(trigger_main(),2)
            self.assertFalse(target.exists())

    def test_workflow_uses_protected_read_lane_not_scheduler_or_model(self):
        yaml=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
        job=yaml.split("\n  admission-readonly:",1)[1]
        schedule=yaml.split("\n  schedule-probe:",1)[1].split("\n  github-access-preflight:",1)[0]
        self.assertIn("inputs.run_admission_diagnosis != true",schedule)
        self.assertIn("github.event.comment.body == '/factory-wake'",schedule)
        self.assertNotIn("'/factory-admission-diagnose '",schedule)
        for term in (
            "github.event.comment.author_association == 'OWNER'",
            "github.event.action == 'created'","!github.event.issue.pull_request",
            "startsWith(github.event.comment.body, '/factory-admission-diagnose ')",
            "      contents: read","      id-token: write","      issues: read",
            "persist-credentials: false",
            "python -m ai_product_factory.admission_audit_trigger",
            "python scripts/audit_admission_diagnostics.py",
            "factory-admission-diagnosis-","retention-days: 7",
        ):
            with self.subTest(term=term):
                self.assertIn(term,job)
        self.assertLess(job.index("admission_audit_trigger"),
                        job.index("uses: ./.github/actions/control-plane-oidc"))
        for prohibited in (
            "OPENAI_API_KEY","FACTORY_GITHUB_TOKEN","FACTORY_PRIMARY_MODEL_ENABLED",
            "merge_pull_request","--mode product","--mode direct","--mode codex",
            "      issues: write","      contents: write","      pull-requests: write",
        ):
            self.assertNotIn(prohibited,job)
        for mode in ("journey-readonly","continuation-offline-preflight"):
            section=yaml.split("\n  "+mode+":",1)[1].split("\n  "+(
                "continuation-offline-preflight" if mode=="journey-readonly" else "admission-readonly"
            )+":",1)[0]
            self.assertIn("inputs.run_admission_diagnosis != true",section)

    def test_public_cli_redacts_untrusted_error_and_emits_zero_effects(self):
        path=ROOT/"scripts/audit_admission_diagnostics.py"
        spec=importlib.util.spec_from_file_location("admission_test_script",path)
        assert spec and spec.loader
        mod=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        stdout=io.StringIO()
        class BrokenReader:
            def read(self,**kwargs):
                raise RuntimeError("SECRET_PASSWORD=should_not_appear")
        with patch.object(mod,"SupabaseAdmissionReader",return_value=BrokenReader()):
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(mod.main(["--project-key","ai-product-factory"]),2)
        text=stdout.getvalue()
        self.assertNotIn("SECRET_PASSWORD",text)
        x=json.loads(text)
        self.assertEqual(x["reason_code"],"unverifiable_live_evidence")
        self.assertEqual((x["paid_calls"],x["writes"]),(0,0))
        self.assertFalse(x["product_ready"])

if __name__=="__main__":
    import unittest
    unittest.main()
