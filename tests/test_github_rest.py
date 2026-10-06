import json
import unittest
from unittest.mock import patch

from ai_product_factory.github_loop import CIState
from ai_product_factory.github_rest import GitHubRestAdapter


class FakeGitHubTransport:
    def __init__(self):
        self.calls = []
        self.check_runs = [{"name": "test", "status": "completed", "conclusion": "success", "details_url": "https://example/check", "output": {}}]
        self.check_runs_forbidden = False
        self.workflow_runs = [{"name":"CRM validation","status":"completed","conclusion":"success","html_url":"https://example/actions/1"}]
        self.commit_statuses = [{"context":"Vercel","state":"success","target_url":"https://preview.example","description":"Deployment completed"}]

    def __call__(self, method, url, headers, body):
        payload = json.loads(body.decode()) if body else None
        self.calls.append((method, url, headers, payload))
        if "/issues/5" in url and method == "GET":
            return 200, {"number": 5, "title": "Feature", "body": "Do it", "html_url": "https://example/issue/5"}
        if "/search/issues?" in url and method == "GET":
            if "is%3Apr" in url:
                return 200, {"items": [{"number": 9, "title": "Manual Codex", "body": "Factory run: run-1", "html_url": "https://example/pr/9", "pull_request": {}}]}
            return 200, {"items": [{"number": 7, "title": "Alert", "body": "<!-- factory-alert:dead_letter -->", "html_url": "https://example/issue/7"}]}
        if "/git/ref/heads/" in url and method == "GET":
            return 200, {"object": {"sha": "base123"}}
        if url.endswith("/git/refs") and method == "POST":
            return 201, {"ref": payload["ref"], "object": {"sha": payload["sha"]}}
        if "/git/commits/base123" in url and method == "GET":
            return 200, {"tree": {"sha": "tree0"}}
        if "/git/trees/tree0?recursive=1" in url and method == "GET":
            return 200, {"truncated": False, "tree": [
                {"path":"AGENTS.md","type":"blob"},
                {"path":"src/app/debug/page.tsx","type":"blob"},
                {"path":"src/app/debug","type":"tree"},
            ]}
        if url.endswith("/git/blobs") and method == "POST":
            return 201, {"sha": "blob1"}
        if url.endswith("/git/trees") and method == "POST":
            return 201, {"sha": "tree1"}
        if url.endswith("/git/commits") and method == "POST":
            return 201, {"sha": "commit1"}
        if "/git/refs/heads/" in url and method == "PATCH":
            return 200, {"object": {"sha": payload["sha"]}}
        if url.endswith("/pulls") and method == "POST":
            return 201, {"number": 9, "html_url": "https://example/pr/9", "head": {"sha": "commit1", "ref": "feat/x", "repo": {"full_name": "owner/repo"}}, "base": {"ref": "main", "sha": "base123"}}
        if "/pulls/9/files" in url and method == "GET":
            return 200, [{"filename":"apps/console/app/page.tsx"},{"filename":"src/core.py"}]
        if "/pulls/9" in url and method == "GET":
            return 200, {"number": 9, "html_url": "https://example/pr/9", "head": {"sha": "commit1", "ref": "codex/refactor", "repo": {"full_name": "owner/repo"}}, "base": {"ref": "main", "sha": "base123"}}
        if "/check-runs" in url and method == "GET":
            if self.check_runs_forbidden:
                return 403, {"message": "forbidden"}
            return 200, {"check_runs": self.check_runs}
        if "/actions/runs?" in url and method == "GET":
            return 200, {"workflow_runs": self.workflow_runs}
        if "/commits/commit1/status" in url and method == "GET":
            return 200, {"statuses": self.commit_statuses}
        if "/issues/5" in url and method == "PATCH":
            return 200, {"number": 5, "state": "closed"}
        return 500, {"message": "unexpected"}

class GitHubRestAdapterTests(unittest.TestCase):
    def setUp(self):
        self.transport = FakeGitHubTransport()
        self.github = GitHubRestAdapter(repository="owner/repo", token="token-placeholder", transport=self.transport)

    def test_find_open_issue_containing_marker(self):
        issue = self.github.find_open_issue_containing("factory-alert:dead_letter")
        self.assertIsNotNone(issue)
        self.assertEqual(issue.number, 7)
        self.assertIn("search/issues", self.transport.calls[-1][1])

    def test_find_open_pull_request_containing_marker(self):
        pr = self.github.find_open_pull_request_containing("Factory run: run-1")
        self.assertIsNotNone(pr)
        self.assertEqual(pr.number, 9)
        self.assertEqual(pr.head_ref, "codex/refactor")
        self.assertEqual(pr.base_ref, "main")
        self.assertEqual(pr.base_sha, "base123")
        self.assertEqual(pr.head_repository, "owner/repo")

    def test_token_is_only_in_authorization_header(self):
        self.github.get_issue(5)
        _, _, headers, _ = self.transport.calls[-1]
        self.assertEqual(headers["Authorization"], "Bearer token-placeholder")

    def test_branch_and_atomic_commit(self):
        self.github.create_branch("feat/x")
        sha = self.github.commit_files("feat/x", {"a.py": "print('x')"}, message="feat: x")
        self.assertEqual(sha, "commit1")

    def test_create_pr_and_green_ci(self):
        pr = self.github.create_pull_request(title="x", body="y", head="feat/x")
        self.assertEqual(pr.number, 9)
        self.assertEqual(self.github.get_ci_state(9), CIState.SUCCESS)

    def test_pull_request_files_are_structured(self):
        files=self.github.get_pull_request_files(9)
        self.assertEqual(files,("apps/console/app/page.tsx","src/core.py"))

    def test_repository_file_tree_is_exact_and_blob_only(self):
        paths=self.github.list_file_paths(ref="base123")
        self.assertEqual(paths,("AGENTS.md","src/app/debug/page.tsx"))
    def test_pending_and_failed_ci(self):
        self.transport.check_runs = [{"status": "in_progress", "conclusion": None}]
        self.assertEqual(self.github.get_ci_state(9), CIState.PENDING)
        self.transport.check_runs = [{"status": "completed", "conclusion": "failure"}]
        self.assertEqual(self.github.get_ci_state(9), CIState.FAILURE)

    def test_fine_grained_ci_fallback_uses_actions_and_commit_statuses(self):
        self.transport.check_runs_forbidden = True
        self.assertEqual(self.github.get_ci_state(9), CIState.SUCCESS)
        self.assertEqual(self.github.last_ci_evidence_source, "github_actions_statuses")
        urls=[call[1] for call in self.transport.calls]
        self.assertTrue(any("/actions/runs?" in url for url in urls))
        self.assertTrue(any("/commits/commit1/status" in url for url in urls))

    def test_fine_grained_ci_fallback_is_fail_closed_without_workflow_evidence(self):
        self.transport.check_runs_forbidden = True
        self.transport.workflow_runs = []
        self.assertEqual(self.github.get_ci_state(9), CIState.PENDING)

    def test_fine_grained_ci_fallback_reports_workflow_failure(self):
        self.transport.check_runs_forbidden = True
        self.transport.workflow_runs = [{"name":"CRM validation","status":"completed","conclusion":"failure","html_url":"https://example/actions/1"}]
        self.assertEqual(self.github.get_ci_state(9), CIState.FAILURE)
        failures=self.github.get_failed_checks(9)
        self.assertEqual(failures[0].name,"CRM validation")

    def test_failed_checks_are_structured(self):
        self.transport.check_runs = [{
            "name": "unit-tests",
            "status": "completed",
            "conclusion": "failure",
            "details_url": "https://example/check/1",
            "output": {"summary": "2 tests failed"},
        }]
        failures = self.github.get_failed_checks(9)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].name, "unit-tests")
        self.assertEqual(failures[0].summary, "2 tests failed")

    def test_adapter_exposes_no_merge_operation(self):
        self.assertFalse(hasattr(self.github, "merge_pull_request"))

    def test_missing_token_fails_fast(self):
        with patch.dict("os.environ",{},clear=True):
            with self.assertRaises(ValueError):
                GitHubRestAdapter(repository="owner/repo", token="", transport=self.transport)

if __name__ == "__main__":
    unittest.main()
