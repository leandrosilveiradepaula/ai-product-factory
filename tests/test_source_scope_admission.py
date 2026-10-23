"""Offline-first source admission, no model usage for incomplete code scope."""
from __future__ import annotations

import unittest
from copy import deepcopy
from unittest.mock import Mock

from ai_product_factory.source_scope_admission import (
    SourceScopeBlocked, assess_bounded_source_scope,
)
from ai_product_factory.platform_source_context import live_platform_source_context
from ai_product_factory.supabase_runtime_queue import SupabaseRuntimeQueue
from ai_product_factory.offline_product_preflight import check_recorded_product_run
from ai_product_factory.github_rest import GitHubIssue

SHA = "a" * 40
REPO = "leandrosilveiradepaula/ai-product-factory"
RUN = "16b12d17-9cb0-4578-a0e2-0d601f36b856"
PROJECT_ID = "fc613c86-3eb7-44d8-a53c-4eea51220e4c"
TASK_ID = "8f661602-620e-4a2e-bcb7-7a4b607f4759"
PATH = "scripts/audit_autonomy_journey.py"


def evidence():
    return {
        "status": "bounded_source_inspected",
        "assessed_commit": SHA,
        "inspected_files": [{
            "path": PATH, "assessed_commit": SHA,
            "content": "def audit(): return True",
            "complete": True,
        }],
        "missing_paths": [],
        "omitted_paths": [],
    }


class SourceScopeAdmissionTests(unittest.TestCase):
    def test_exact_sha_complete_code_scope_is_admitted_as_source_only(self):
        outcome = assess_bounded_source_scope(evidence(), sha=SHA)
        self.assertEqual(outcome["status"], "complete")
        self.assertTrue(outcome["code_inspected"])
        self.assertEqual(outcome["inspected_count"], 1)
        self.assertNotIn("model", outcome)
        self.assertNotIn("release", outcome)


    def test_four_current_source_files_are_admitted_but_fifth_is_rejected(self):
        scope = evidence()
        for path in (
            "src/lib/builder.ts",
            "src/lib/builder.test.ts",
            "src/components/Builder.test.tsx",
        ):
            scope["inspected_files"].append({
                "path": path, "assessed_commit": SHA,
                "content": "verified source at exact SHA",
                "complete": True,
            })
        assessed = assess_bounded_source_scope(scope, sha=SHA)
        self.assertEqual(assessed["inspected_count"], 4)
        self.assertEqual(assessed["status"], "complete")
        scope["inspected_files"].append({
            "path": "src/lib/unbounded.ts", "assessed_commit": SHA,
            "content": "should be rejected", "complete": True,
        })
        with self.assertRaises(SourceScopeBlocked):
            assess_bounded_source_scope(scope, sha=SHA)

    def test_issue_mismatch_and_oversized_active_scope_are_fixed_reason_codes(self):
        self.assertEqual(SourceScopeBlocked("source_authorization_issue_mismatch").code,
                         "source_authorization_issue_mismatch")
        self.assertEqual(SourceScopeBlocked("source_active_scope_oversized").code,
                         "source_active_scope_oversized")
        with self.assertRaises(ValueError):
            SourceScopeBlocked("CRM issue #24: arbitrary source text")

    def test_missing_omitted_truncated_code_is_partial_not_a_human_gate(self):
        scenarios = (
            ("missing_paths", ["src/ai_product_factory/runtime_cli.py"], "missing_count"),
            ("omitted_paths", ["src/ai_product_factory/schedule_probe.py"], "omitted_count"),
        )
        for key, value, counter in scenarios:
            scope = evidence()
            scope[key] = value
            outcome = assess_bounded_source_scope(scope, sha=SHA)
            self.assertEqual(outcome["status"], "partial")
            self.assertEqual(outcome[counter], 1)
            self.assertTrue(outcome["code_inspected"])
        scope = evidence()
        scope["inspected_files"][0]["complete"] = False
        outcome = assess_bounded_source_scope(scope, sha=SHA)
        self.assertEqual(outcome["status"], "partial")
        self.assertEqual(outcome["truncated_count"], 1)

    def test_scoped_new_files_without_existing_code_can_be_planned(self):
        scope = {"status": "scoped_source_missing", "assessed_commit": SHA,
                 "inspected_files": [], "missing_paths": ["src/new_module.py"],
                 "omitted_paths": []}
        outcome = assess_bounded_source_scope(scope, sha=SHA)
        self.assertEqual(outcome["status"], "new_files_only")
        self.assertFalse(outcome["code_inspected"])
        self.assertEqual(outcome["missing_count"], 1)

    def test_sha_mismatch_malformed_or_duplicate_files_are_rejected(self):
        cases = []
        x = evidence(); x["assessed_commit"] = "b" * 40; cases.append(x)
        x = evidence(); x["inspected_files"][0]["assessed_commit"] = "b" * 40; cases.append(x)
        x = evidence(); x["inspected_files"][0]["path"] = "../private.txt"; cases.append(x)
        x = evidence(); x["inspected_files"][0]["content"] = "   "; cases.append(x)
        x = evidence(); x["inspected_files"].append(deepcopy(x["inspected_files"][0])); cases.append(x)
        x = evidence(); x["missing_paths"] = {"sneaky": True}; cases.append(x)
        for bad in cases:
            with self.subTest(payload=repr(bad)[:65]), self.assertRaises(SourceScopeBlocked):
                assess_bounded_source_scope(bad, sha=SHA)

    def test_unscoped_natural_language_is_not_misreported_as_code_inspection(self):
        broad = {
            "status": "no_scoped_source_paths", "assessed_commit": SHA,
            "inspected_files": [], "missing_paths": [],
        }
        outcome = assess_bounded_source_scope(broad, sha=SHA)
        self.assertEqual(outcome["status"], "unscoped")
        self.assertFalse(outcome["code_inspected"])
        self.assertEqual(outcome["inspected_count"], 0)

    def test_fail_closed_reason_vocabulary_cannot_embed_secret(self):
        with self.assertRaises(ValueError):
            SourceScopeBlocked("leaked-secret-in-provider-message")


class FakeGitHub:
    repository = REPO

    def __init__(self, paths, issue_paths):
        self.paths = tuple(paths)
        self.issue_paths = issue_paths
        self.reads = []
        self.writes = Mock(side_effect=AssertionError("writes forbidden"))
        self.docs = {
            "AGENTS.md": "# approved source rules",
            "PROJECT_PLAN.md": "# validated platform plan",
            PATH: "def audit(): return True",
        }

    def get_branch_sha(self, branch):
        self.reads.append(("main", branch))
        return SHA

    def get_file_text(self, path, *, ref):
        assert ref == SHA
        self.reads.append((path, ref))
        return self.docs[path]

    def list_file_paths(self, *, ref):
        assert ref == SHA
        return self.paths

    def get_issue(self, number):
        assert number == 987
        return GitHubIssue(number, "New safe diagnostic", self.issue_paths, "issue-url")


class PlatformAutomaticAdmissionTests(unittest.TestCase):
    def project(self):
        return {"project_kind": "platform", "repository": REPO,
                "manifest": {"continuation_request": {"summary": "Implementar issue #987"}}}

    def test_real_platform_reader_records_sha_and_free_admission(self):
        github = FakeGitHub((PATH,), "Inspect " + PATH)
        result = live_platform_source_context(project=self.project(), context={}, github=github)
        candidate = result["current_state_facts"]["live_candidate"]
        self.assertEqual(candidate["source_admission"]["status"], "complete")
        self.assertEqual(candidate["source_evidence"]["issue_reference"], 987)
        self.assertEqual(candidate["sha"], SHA)
        self.assertEqual(candidate["verified_open_pr"], None)
        self.assertEqual(sum(1 for p,_ in github.reads if p == PATH), 1)
        github.writes.assert_not_called()

    def test_missing_explicit_issue_path_is_partial_and_not_falsely_complete(self):
        github = FakeGitHub((PATH,), "Inspect " + PATH + " and src/ai_product_factory/runtime_cli.py")
        context = live_platform_source_context(project=self.project(), context={}, github=github)
        admission = context["current_state_facts"]["live_candidate"]["source_admission"]
        self.assertEqual(admission["status"], "partial")
        self.assertEqual(admission["missing_count"], 1)
        github.writes.assert_not_called()

    def test_unscoped_issue_not_confused_with_verified_code(self):
        github = FakeGitHub((PATH,), "Investigate an existing system")
        result = live_platform_source_context(project=self.project(), context={}, github=github)
        candidate = result["current_state_facts"]["live_candidate"]
        self.assertEqual(candidate["source_admission"]["status"], "unscoped")
        self.assertEqual(candidate["source_evidence"]["status"], "no_scoped_source_paths")
        github.writes.assert_not_called()


class RuntimeSourceAdmissibilityTests(unittest.TestCase):
    def make_queue(self):
        queue = SupabaseRuntimeQueue(url="https://example.supabase.co", service_role_key="test")
        events = []

        def rpc(name, payload):
            events.append((name, payload))
            if name == "factory_claim_next_run":
                return {
                    "run_id": RUN, "task_id": TASK_ID, "project_id": PROJECT_ID,
                    "project_key": "ai-product-factory",
                    "stages": ["reconciliation", "gap_analysis", "planning"],
                    "execution_generation": 1, "context": {},
                }
            if name in {"factory_assert_claimed_run_epoch", "factory_finish_run"}:
                return None
            raise AssertionError("unexpected write " + name)

        queue._rpc = rpc
        queue._reconciliation_context = lambda project, context: context
        return queue, events

    def test_platform_scope_error_settles_claim_with_stable_redacted_code(self):
        queue, events = self.make_queue()
        queue._live_candidate_context = Mock(side_effect=SourceScopeBlocked("source_evidence_inconsistent"))
        with self.assertRaises(SourceScopeBlocked):
            queue.claim_next("worker")
        self.assertEqual([name for name, _ in events], [
            "factory_claim_next_run", "factory_assert_claimed_run_epoch",
            "factory_finish_run",
        ])
        self.assertEqual(events[-1][1]["p_status"], "failed")
        self.assertEqual(events[-1][1]["p_error"], "reconciliation_source_evidence_inconsistent")
        queue._live_candidate_context.assert_called_once()

    def test_unscoped_source_does_not_forge_verified_code(self):
        queue, events = self.make_queue()
        queue._live_candidate_context = lambda _project, ctx: {**ctx, "source_admission": {
            "status": "unscoped", "code_inspected": False
        }}
        actual = queue.claim_next("worker")
        self.assertFalse(actual.context["source_admission"]["code_inspected"])
        self.assertEqual([name for name,_ in events], ["factory_claim_next_run"])

    def test_offline_audit_marks_partial_scope_without_claiming_e2e(self):
        queue = self.make_queue()[0]
        def read(path):
            if path.startswith("factory_projects?"):
                return [{"id": PROJECT_ID, "project_key": "ai-product-factory",
                         "project_kind": "platform", "repository": REPO,
                         "is_active": True, "manifest": {}}]
            if path.startswith("factory_runs?"):
                return [{"id": RUN, "task_id": TASK_ID, "status": "failed",
                         "metadata": {"stages": ["reconciliation", "gap_analysis", "planning"]}}]
            if path.startswith("factory_tasks?"):
                return [{"id": TASK_ID, "project_id": PROJECT_ID, "status": "failed"}]
            raise AssertionError("unknown read")
        queue._get = read
        queue._reconciliation_context = lambda _id, ctx: {
            **ctx, "state_snapshot": {"summary": "historical", "evidence": [1]}
        }
        queue._live_candidate_context = Mock(return_value={
            "current_state_facts": {"live_candidate": {
                "sha": SHA, "source_evidence": evidence(),
                "source_admission": {"status": "partial", "code_inspected": True},
            }}
        })
        report = check_recorded_product_run(project_key="ai-product-factory",run_id=RUN,queue=queue)
        self.assertEqual(report["source_preflight"], "partial")
        self.assertEqual(report["reason_code"], "source_scope_partial")
        self.assertTrue(report["code_inspected"])
        self.assertEqual(report["state"], "historical_terminal")
        self.assertFalse(report["e2e_verified"])
        self.assertEqual(report["paid_model_calls"], 0)

    def test_offline_audit_returns_sanitized_code_without_paid_model(self):
        queue = self.make_queue()[0]
        def read(path):
            if path.startswith("factory_projects?"):
                return [{"id": PROJECT_ID, "project_key": "ai-product-factory",
                         "project_kind": "platform", "repository": REPO,
                         "is_active": True, "manifest": {}}]
            if path.startswith("factory_runs?"):
                return [{"id": RUN, "task_id": TASK_ID, "status": "failed",
                         "metadata": {"stages": ["reconciliation", "gap_analysis", "planning"]}}]
            if path.startswith("factory_tasks?"):
                return [{"id": TASK_ID, "project_id": PROJECT_ID, "status": "failed"}]
            raise AssertionError("unknown read")
        queue._get = read
        queue._reconciliation_context = lambda _id, ctx: {
            **ctx, "state_snapshot": {"summary": "historical", "evidence": [1]}
        }
        queue._live_candidate_context = Mock(side_effect=SourceScopeBlocked("source_sha_unverified"))
        report = check_recorded_product_run(project_key="ai-product-factory",run_id=RUN,queue=queue)
        self.assertEqual(report["source_preflight"], "blocked")
        self.assertEqual(report["reason_code"], "source_sha_unverified")
        self.assertEqual(report["source_scope_status"], "blocked")
        self.assertEqual(report["state"], "historical_terminal")
        self.assertEqual(report["paid_model_calls"], 0)
        self.assertEqual(report["writes"], 0)


if __name__ == "__main__":
    unittest.main()
