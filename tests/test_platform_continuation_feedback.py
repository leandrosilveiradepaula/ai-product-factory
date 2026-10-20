"""Real Factory continuation: platform source and Console submission safeguards."""
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ai_product_factory.platform_source_context import live_platform_source_context
from ai_product_factory.supabase_runtime_queue import SupabaseRuntimeQueue

SHA = "a" * 40
MOVED = "b" * 40
REPO = "leandrosilveiradepaula/ai-product-factory"
PROJECT = {
    "project_kind": "platform", "repository": REPO,
    "manifest": {"continuation_request": {
        "summary": "Check src/ai_product_factory/runtime_cli.py and add diagnostics"
    }},
}


class FakeGitHub:
    repository = REPO

    def __init__(self):
        self.branches = [SHA, SHA]
        self.reads = []
        self.paths = ("src/ai_product_factory/runtime_cli.py",)
        self.docs = {
            "AGENTS.md": "# Factory rules",
            "PROJECT_PLAN.md": "# Factory plan",
            "src/ai_product_factory/runtime_cli.py": "def main(): pass",
        }

    def get_branch_sha(self, branch):
        assert branch == "main"
        return self.branches.pop(0)

    def get_file_text(self, path, *, ref):
        assert ref == SHA
        self.reads.append((path, ref))
        return self.docs[path]

    def list_file_paths(self, *, ref):
        assert ref == SHA
        return self.paths


class PlatformSourceTests(unittest.TestCase):
    def test_platform_uses_exact_main_evidence_without_fake_preview_pr(self):
        gh = FakeGitHub()
        context = {"state_snapshot": {"summary": "historical", "evidence": [{"source": "db"}]},
                   "current_state_facts": {"github_access": {"status": "ready"}}}
        result = live_platform_source_context(project=PROJECT, context=context, github=gh)
        live = result["current_state_facts"]["live_candidate"]
        self.assertEqual(live["sha"], SHA)
        self.assertIsNone(live["verified_open_pr"])
        self.assertEqual(live["observed_from"], "live_github_main_exact_sha")
        self.assertEqual(live["source_evidence"]["assessed_commit"], SHA)
        self.assertEqual([row["path"] for row in live["source_evidence"]["inspected_files"]],
                         ["src/ai_product_factory/runtime_cli.py"])
        self.assertEqual(result["current_state_facts"]["github_access"]["verified_main_sha"], SHA)
        self.assertEqual(context["current_state_facts"]["github_access"], {"status": "ready"})

    def test_platform_requires_consistent_main_and_governance(self):
        moved = FakeGitHub()
        moved.branches = [SHA, MOVED]
        with self.assertRaisesRegex(PermissionError, "main moved"):
            live_platform_source_context(project=PROJECT, context={}, github=moved)
        bad = FakeGitHub()
        bad.docs["AGENTS.md"] = ""
        with self.assertRaisesRegex(PermissionError, "governance"):
            live_platform_source_context(project=PROJECT, context={}, github=bad)
        missing = FakeGitHub()
        missing.docs["PROJECT_PLAN.md"] = " " * 10
        with self.assertRaisesRegex(PermissionError, "governance"):
            live_platform_source_context(project=PROJECT, context={}, github=missing)

    def test_platform_cannot_cross_repository_or_reclassify_crm(self):
        with self.assertRaisesRegex(PermissionError, "explicitly registered"):
            live_platform_source_context(
                project={**PROJECT, "project_kind": "existing"},
                context={}, github=FakeGitHub())
        mismatch = FakeGitHub()
        mismatch.repository = "someone/else"
        with self.assertRaisesRegex(PermissionError, "differs"):
            live_platform_source_context(project=PROJECT, context={}, github=mismatch)
        with self.assertRaisesRegex(PermissionError, "invalid repository"):
            live_platform_source_context(
                project={**PROJECT, "repository": "../other"},
                context={}, github=FakeGitHub())

    def test_platform_github_lookups_have_no_writes(self):
        gh = FakeGitHub()
        gh.create_branch = Mock(side_effect=AssertionError("write"))
        gh.commit_files = Mock(side_effect=AssertionError("write"))
        gh.create_pull_request = Mock(side_effect=AssertionError("write"))
        live_platform_source_context(project=PROJECT, context={}, github=gh)
        gh.create_branch.assert_not_called()
        gh.commit_files.assert_not_called()
        gh.create_pull_request.assert_not_called()

    def test_claim_uses_platform_path_only_for_registered_platform(self):
        queue = SupabaseRuntimeQueue(url="https://example.supabase.co", service_role_key="example")
        queue._get = Mock(return_value=[{"id": "p", **PROJECT}])
        context = {"state_snapshot": {"summary": "durable", "evidence": [1]}}
        with patch("ai_product_factory.supabase_runtime_queue.GitHubRestAdapter") as adapter:
            adapter.return_value = FakeGitHub()
            actual = queue._live_candidate_context("p", context)
        self.assertEqual(actual["current_state_facts"]["live_candidate"]["sha"], SHA)
        adapter.assert_called_once_with(repository=REPO)
        queue._get.return_value = [{"id": "p", **PROJECT, "project_kind": "greenfield"}]
        with self.assertRaisesRegex(PermissionError, "existing or platform"):
            queue._live_candidate_context("p", context)


ROOT = Path(__file__).resolve().parents[1]


class ConsoleContinuationFeedbackTests(unittest.TestCase):
    def test_submit_status_is_visible_and_disables_double_click(self):
        component = (ROOT / "apps/console/app/projects/[key]/request/continuation-submit.tsx").read_text()
        page = (ROOT / "apps/console/app/projects/[key]/request/page.tsx").read_text()
        self.assertIn("useFormStatus", component)
        self.assertIn("disabled={pending}", component)
        self.assertIn("aria-busy={pending}", component)
        self.assertIn('role="status"', component)
        self.assertIn('aria-live="polite"', component)
        self.assertIn("Registrando pedido...", component)
        self.assertIn("<ContinuationSubmit/>", page)
        self.assertIn('name="request_id"', page)
        self.assertIn("!result.created?\"replayed\"", page)

    def test_idempotency_and_wake_are_still_server_authoritative(self):
        page = (ROOT / "apps/console/app/projects/[key]/request/page.tsx").read_text()
        control = (ROOT / "apps/console/lib/control-plane.ts").read_text()
        self.assertIn("await enqueueProjectContinuation(projectKey,request,files.length,requestId)", page)
        self.assertIn("p_request_id:requestId", control)
        self.assertIn("if(result.created)", control)
        self.assertNotIn("requestIntakeWorkerWake()", page)


if __name__ == "__main__":
    unittest.main()
