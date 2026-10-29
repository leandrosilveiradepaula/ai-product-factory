"""Offline guards for opt-in replacement of an existing CRM candidate."""
from __future__ import annotations

from dataclasses import dataclass, replace
import unittest

from ai_product_factory.nonproduction_candidate_switch import verify_candidate_switch

OLD = "a" * 40
NEW = "b" * 40
MAIN = "c" * 40
REPO = "leandrosilveiradepaula/crm-infodive"
BRANCH = "preview/crm22-rbac-security-evidence"


@dataclass
class PR:
    number: int
    head_sha: str
    head_ref: str
    base_ref: str = "main"
    base_sha: str = MAIN
    state: str = "open"
    merged: bool = False
    draft: bool = False
    head_repository: str = REPO


class FakeGithub:
    repository = REPO

    def __init__(self):
        self.old = PR(56, OLD, "preview/hardening-release-candidate")
        self.new = PR(202, NEW, BRANCH)

    def get_branch_sha(self, name):
        return {"main": MAIN, self.old.head_ref: OLD, BRANCH: NEW}[name]

    def get_pull_request(self, number):
        return {56: self.old, 202: self.new}[number]

    def compare_commits(self, base, head):
        assert (base, head) == (MAIN, NEW)
        return {"status": "ahead", "ahead_by": 1, "behind_by": 0}

    def get_pull_request_files(self, number):
        assert number == 202
        return ("src/lib/email-sync-tenant.ts", "test/email-sync-tenant-rbac.test.ts")

    def _call(self, method, path, *, query=None):
        if path.endswith("/pulls/202"):
            return {"body": "Correção ligada à issue #22, sem merge automático."}
        assert query == {"head_sha": NEW, "per_page": "100"}
        return {"total_count": 1, "workflow_runs": [{
            "id": 400001, "workflow_id": 372542929, "run_number": 8,
            "run_attempt": 1, "head_sha": NEW, "head_branch": BRANCH,
            "path": ".github/workflows/crm-validation.yml",
            "name": "CRM validation", "event": "pull_request",
            "status": "completed", "conclusion": "success",
        }]}


def project():
    return {
        "repository": REPO,
        "manifest": {
            "continuation_request": {
                "source": "github-owner", "id": "authorized-request",
                "summary": "Concluir issue #22 do CRM Infodive",
            },
            "delivery_target": {
                "schema_version": 1, "mode": "open_pr_candidate",
                "repository": REPO,
                "branch": "preview/hardening-release-candidate",
                "sha": OLD, "candidate_pr_number": 56,
                "repin_policy": {
                    "schema_version": 1, "enabled": True,
                    "native_ci": {
                        "schema_version": 1, "event": "pull_request",
                        "workflow_id": 372542929,
                        "workflow_path": ".github/workflows/crm-validation.yml",
                        "workflow_name": "CRM validation",
                    },
                },
            },
        },
    }


class SwitchTests(unittest.TestCase):
    def test_success_attests_both_candidate_identities(self):
        e = verify_candidate_switch(FakeGithub(), project=project(),
                                    candidate_pr_number=202, issue_number=22)
        self.assertEqual(e["new_sha"], NEW)
        self.assertEqual(e["old_sha"], OLD)
        self.assertEqual(e["pr_base_sha"], MAIN)
        self.assertEqual(e["ci_run_id"], 400001)

    def test_missing_authorization_refused(self):
        p = project()
        p["manifest"]["continuation_request"]["summary"] = "issue #23"
        with self.assertRaises(PermissionError):
            verify_candidate_switch(FakeGithub(), project=p,
                                    candidate_pr_number=202, issue_number=22)

    def test_old_candidate_drift_refused(self):
        g = FakeGithub()
        g.old = replace(g.old, head_sha=NEW)
        with self.assertRaises(PermissionError):
            verify_candidate_switch(g, project=project(),
                                    candidate_pr_number=202, issue_number=22)

    def test_draft_refused(self):
        g = FakeGithub()
        g.new = replace(g.new, draft=True)
        with self.assertRaises(PermissionError):
            verify_candidate_switch(g, project=project(),
                                    candidate_pr_number=202, issue_number=22)

    def test_wrong_base_refused(self):
        g = FakeGithub()
        g.new = replace(g.new, base_sha=OLD)
        with self.assertRaises(PermissionError):
            verify_candidate_switch(g, project=project(),
                                    candidate_pr_number=202, issue_number=22)

    def test_wrong_tenant_refused(self):
        g = FakeGithub()
        g.new = replace(g.new, head_repository="another/tenant")
        with self.assertRaises(PermissionError):
            verify_candidate_switch(g, project=project(),
                                    candidate_pr_number=202, issue_number=22)

    def test_failed_native_ci_refused(self):
        g = FakeGithub()
        original = g._call
        def bad(method, path, *, query=None):
            value = original(method, path, query=query)
            if "workflow_runs" in value:
                value["workflow_runs"][0]["conclusion"] = "failure"
            return value
        g._call = bad
        with self.assertRaises(PermissionError):
            verify_candidate_switch(g, project=project(),
                                    candidate_pr_number=202, issue_number=22)

    def test_pr_without_authorized_issue_refused(self):
        g = FakeGithub()
        original = g._call
        def bad(method, path, *, query=None):
            value = original(method, path, query=query)
            if "body" in value:
                value["body"] = "unrelated issue #23"
            return value
        g._call = bad
        with self.assertRaises(PermissionError):
            verify_candidate_switch(g, project=project(),
                                    candidate_pr_number=202, issue_number=22)


if __name__ == "__main__":
    unittest.main()
