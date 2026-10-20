"""Owner-only no-model preflight trigger: identity, isolation and audit evidence."""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from ai_product_factory.offline_preflight_trigger import resolve_target, main

ROOT = Path(__file__).resolve().parents[1]
RUN = "16b12d17-9cb0-4578-a0e2-0d601f36b856"
CMD = f"/factory-offline-preflight ai-product-factory {RUN}"
OWNER = {
    "FACTORY_EVENT_NAME": "issue_comment",
    "FACTORY_AUTHOR_ASSOCIATION": "OWNER",
    "FACTORY_ISSUE_IS_PR": "false",
    "FACTORY_COMMENT_BODY": CMD,
}
DISPATCH = {
    "FACTORY_EVENT_NAME": "workflow_dispatch",
    "FACTORY_DISPATCH_ENABLED": "true",
    "FACTORY_JOURNEY_ENABLED": "false",
    "FACTORY_DISPATCH_PROJECT_KEY": "ai-product-factory",
    "FACTORY_DISPATCH_RUN_ID": RUN,
}


class OwnerOfflinePreflightTests(TestCase):
    def test_exact_owner_comment_and_manual_dispatch(self):
        self.assertEqual(resolve_target(OWNER), ("ai-product-factory", RUN))
        self.assertEqual(resolve_target(DISPATCH), ("ai-product-factory", RUN))

    def test_other_roles_and_pr_threads_are_rejected(self):
        for role in ("NONE", "CONTRIBUTOR", "COLLABORATOR", "MEMBER", ""):
            with self.subTest(role=role), self.assertRaises(ValueError):
                resolve_target({**OWNER, "FACTORY_AUTHOR_ASSOCIATION": role})
        for flag in ("true", "", "other"):
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                resolve_target({**OWNER, "FACTORY_ISSUE_IS_PR": flag})

    def test_malformed_owner_commands_fail_closed(self):
        variants = (
            CMD + " ", CMD + "\n", CMD + "\n/factory-wake",
            CMD + " extra", CMD.replace("ai-product-factory", "../other"),
            CMD.replace("ai-product-factory", "factory;echo"),
            CMD.replace(RUN, RUN.upper()),
            "/factory-offline-preflight", "/factory-wake",
            CMD.replace(RUN, "not-a-run"),
        )
        for command in variants:
            with self.subTest(command=command), self.assertRaises(ValueError):
                resolve_target({**OWNER, "FACTORY_COMMENT_BODY": command})

    def test_dispatch_cannot_fall_back_to_comment_or_run_workers(self):
        for override in (
            {"FACTORY_DISPATCH_ENABLED": "false"},
            {"FACTORY_JOURNEY_ENABLED": "true"},
            {"FACTORY_DISPATCH_RUN_ID": "invalid", "FACTORY_COMMENT_BODY": CMD},
            {"FACTORY_DISPATCH_PROJECT_KEY": "other;bad"},
            {"FACTORY_EVENT_NAME": "schedule"},
            {"FACTORY_EVENT_NAME": "repository_dispatch"},
        ):
            with self.subTest(override=override), self.assertRaises(ValueError):
                resolve_target({**DISPATCH, **override})

    def test_command_writes_only_validated_github_outputs(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "output"
            with patch.dict(os.environ, {**OWNER, "GITHUB_OUTPUT": str(path)}, clear=True):
                self.assertEqual(main(), 0)
            self.assertEqual(path.read_text(), f"project_key=ai-product-factory\nrun_id={RUN}\n")
            path.unlink()
            with patch.dict(os.environ, {**OWNER, "GITHUB_OUTPUT": str(path),
                                          "FACTORY_AUTHOR_ASSOCIATION": "NONE"}, clear=True):
                self.assertEqual(main(), 2)
            self.assertFalse(path.exists())

    def test_github_workflow_trust_and_worker_isolation(self):
        flow = (ROOT / ".github/workflows/autonomous-runner.yml").read_text()
        jobs = "\n" + flow.split("\njobs:\n", 1)[1]
        scheduler = jobs.split("\n  schedule-probe:\n", 1)[1].split("\n  github-access-preflight:\n", 1)[0]
        offline = jobs.split("\n  continuation-offline-preflight:\n", 1)[1]
        alerts = jobs.split("\n  alerts-owner-comment:\n", 1)[1].split("\n  codex-route-preflight:\n", 1)[0]
        self.assertIn("github.event.comment.body == '/factory-wake'", scheduler)
        self.assertIn("github.event.comment.body == '/factory-alerts'", alerts)
        self.assertIn("inputs.run_offline_preflight != true", scheduler)
        self.assertIn("github.event.comment.author_association == 'OWNER'", offline)
        self.assertIn("github.event.action == 'created'", offline)
        self.assertIn("!github.event.issue.pull_request", offline)
        self.assertIn("startsWith(github.event.comment.body, '/factory-offline-preflight ')", offline)
        self.assertIn("      issues: read", offline)
        self.assertIn("      contents: read", offline)
        self.assertIn("      id-token: write", offline)
        self.assertNotIn("      issues: write", offline)
        self.assertNotIn("OPENAI_API_KEY", offline)
        self.assertNotIn("FACTORY_PRIMARY_MODEL_ENABLED", offline)
        self.assertNotIn("FACTORY_GITHUB_TOKEN", offline)
        self.assertNotIn("--mode product", offline)
        self.assertNotIn("--mode recovery", offline)
        self.assertNotIn("factory_claim_next_run", offline)
        self.assertIn("persist-credentials: false", offline)
        self.assertIn("python -m ai_product_factory.offline_preflight_trigger", offline)
        self.assertIn("audit_offline_product_preflight.py", offline)
        self.assertIn("retention-days: 7", offline)
        self.assertLess(offline.index("offline_preflight_trigger"),
                        offline.index("uses: ./.github/actions/control-plane-oidc"))
        self.assertNotIn(chr(92)+"$"+"{{", offline)
        self.assertEqual(offline.count("uses: ./.github/actions/control-plane-oidc"), 1)


if __name__ == "__main__":
    import unittest
    unittest.main()
