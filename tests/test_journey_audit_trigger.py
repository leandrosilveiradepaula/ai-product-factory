"""Fail-closed GitHub issue-comment trigger for actual read-only E2E audit."""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from ai_product_factory.journey_audit_trigger import main, resolve_target

RUN="945c0da5-f36f-46da-a454-072037a988a5"
SINCE="2026-10-20T03:00:00Z"
CMD=f"/factory-journey-audit ai-product-factory {RUN} {SINCE}"
OWNER={
    "FACTORY_EVENT_NAME":"issue_comment",
    "FACTORY_AUTHOR_ASSOCIATION":"OWNER",
    "FACTORY_ISSUE_IS_PR":"false",
    "FACTORY_COMMENT_BODY":CMD,
}
DISPATCH={
    "FACTORY_EVENT_NAME":"workflow_dispatch",
    "FACTORY_DISPATCH_ENABLED":"true",
    "FACTORY_OFFLINE_ENABLED":"false",
    "FACTORY_DISPATCH_PROJECT_KEY":"ai-product-factory",
    "FACTORY_DISPATCH_RUN_ID":RUN,
    "FACTORY_DISPATCH_SINCE_UTC":SINCE,
    "FACTORY_DISPATCH_REQUIRE_STAGE":"operations",
}
ROOT=Path(__file__).resolve().parents[1]


class ReadonlyOwnerJourneyTriggerTests(TestCase):
    def test_exact_issue_owner_and_explicit_manual_dispatch(self):
        self.assertEqual(resolve_target(OWNER),("ai-product-factory",RUN,SINCE,"operations"))
        self.assertEqual(resolve_target(DISPATCH),("ai-product-factory",RUN,SINCE,"operations"))

    def test_untrusted_roles_or_pr_threads_cannot_fetch_oidc(self):
        for role in ("COLLABORATOR","MEMBER","CONTRIBUTOR","NONE",""):
            with self.subTest(role=role),self.assertRaises(ValueError):
                resolve_target({**OWNER,"FACTORY_AUTHOR_ASSOCIATION":role})
        for flag in ("true","","other"):
            with self.subTest(flag=flag),self.assertRaises(ValueError):
                resolve_target({**OWNER,"FACTORY_ISSUE_IS_PR":flag})

    def test_malformed_command_date_injection_and_extra_lines_fail_closed(self):
        variants=(
            CMD+" ",CMD+"\n",CMD+"\n/factory-wake",CMD+" && echo hacked",
            CMD.replace("ai-product-factory","../other"),
            CMD.replace("ai-product-factory","factory;echo"),
            CMD.replace(RUN,RUN.upper()),
            CMD.replace(RUN,"not-a-run"),
            CMD.replace(SINCE,"2026-02-30T03:00:00Z"),
            CMD.replace(SINCE,"2026-10-20T03:00:00+00:00"),
            CMD.replace(SINCE,"2099-01-01T03:00:00Z"),
            "/factory-wake","/factory-offline-preflight",
        )
        for body in variants:
            with self.subTest(body=body[:70]),self.assertRaises(ValueError):
                resolve_target({**OWNER,"FACTORY_COMMENT_BODY":body})

    def test_manual_dispatch_cannot_be_satisfied_by_untrusted_owner_comment(self):
        for change in (
            {"FACTORY_DISPATCH_ENABLED":"false"},
            {"FACTORY_OFFLINE_ENABLED":"true"},
            {"FACTORY_DISPATCH_PROJECT_KEY":"other/../project"},
            {"FACTORY_DISPATCH_RUN_ID":RUN.upper()},
            {"FACTORY_DISPATCH_SINCE_UTC":"2026-14-20T03:00:00Z"},
            {"FACTORY_DISPATCH_REQUIRE_STAGE":"paid_model"},
            {"FACTORY_EVENT_NAME":"schedule","FACTORY_COMMENT_BODY":CMD},
            {"FACTORY_EVENT_NAME":"repository_dispatch","FACTORY_COMMENT_BODY":CMD},
        ):
            with self.subTest(change=change),self.assertRaises(ValueError):
                resolve_target({**DISPATCH,**change})

    def test_exact_outputs_only_written_after_validation(self):
        with TemporaryDirectory() as temp:
            path=Path(temp)/"out"
            with patch.dict(os.environ,{**OWNER,"GITHUB_OUTPUT":str(path)},clear=True):
                self.assertEqual(main(),0)
            self.assertEqual(path.read_text(),(
                f"project_key=ai-product-factory\n"
                f"run_id={RUN}\n"
                f"since_utc={SINCE}\n"
                "require_stage=operations\n"
            ))
            path.unlink()
            with patch.dict(os.environ,{**OWNER,"GITHUB_OUTPUT":str(path),
                                         "FACTORY_AUTHOR_ASSOCIATION":"NONE"},clear=True):
                self.assertEqual(main(),2)
            self.assertFalse(path.exists())

    def test_runner_has_only_read_capabilities_and_no_worker_or_model_path(self):
        workflow=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
        assert "\n  journey-readonly:" in workflow
        audit=workflow.split("\n  journey-readonly:",1)[1].split(
            "\n  continuation-offline-preflight:",1
        )[0]
        schedule=workflow.split("\n  schedule-probe:",1)[1].split(
            "\n  github-access-preflight:",1
        )[0]
        for key in (
            "github.event.action == 'created'",
            "github.event.comment.author_association == 'OWNER'",
            "!github.event.issue.pull_request",
            "startsWith(github.event.comment.body, '/factory-journey-audit ')",
            "      contents: read",
            "      id-token: write",
            "      issues: read",
            "      pull-requests: read",
            "persist-credentials: false",
            "python -m ai_product_factory.journey_audit_trigger",
            "python scripts/audit_autonomy_journey.py",
            "retention-days: 7",
        ):
            with self.subTest(required=key):
                self.assertIn(key,audit)
        self.assertLess(audit.index("journey_audit_trigger"),
                        audit.index("uses: ./.github/actions/control-plane-oidc"))
        for forbidden in (
            "OPENAI_API_KEY","FACTORY_PRIMARY_MODEL_ENABLED",
            "FACTORY_GITHUB_TOKEN","merge_pull_request",
            "--mode product","--mode direct","--mode codex",
            "      issues: write","      contents: write","      pull-requests: write",
        ):
            self.assertNotIn(forbidden,audit)
        self.assertIn("github.event.comment.body == '/factory-wake'",schedule)
        self.assertNotIn("'/factory-journey-audit '",schedule)


    def test_exact_nonproduction_scope_is_explicit_and_owner_only(self):
        body=CMD+" scope=nonproduction"
        self.assertEqual(resolve_target({
            **OWNER,"FACTORY_COMMENT_BODY":body,
        }),("ai-product-factory",RUN,SINCE,"nonproduction_integration"))
        for invalid in (
            CMD+" nonproduction", CMD+" scope=production",
            CMD+" scope=nonproduction extra", CMD+" scope=nonproduction\n",
            CMD+" scope=nonproduction;rm",
        ):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                resolve_target({**OWNER,"FACTORY_COMMENT_BODY":invalid})
        with self.assertRaises(ValueError):
            resolve_target({**OWNER,"FACTORY_COMMENT_BODY":body,
                            "FACTORY_AUTHOR_ASSOCIATION":"COLLABORATOR"})


if __name__=="__main__":
    import unittest
    unittest.main()
