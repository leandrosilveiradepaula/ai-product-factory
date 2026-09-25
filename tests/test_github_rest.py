import json
import unittest

from ai_product_factory.github_loop import CIState
from ai_product_factory.github_rest import GitHubRestAdapter


class FakeGitHubTransport:
    def __init__(self):
        self.calls = []
        self.check_runs = [{"status": "completed", "conclusion": "success"}]

    def __call__(self, method, url, headers, body):
        payload = json.loads(body.decode()) if body else None
        self.calls.append((method, url, headers, payload))
        if "/issues/5" in url and method == "GET":
            return 200, {"number": 5, "title": "Feature", "body": "Do it", "html_url": "https://example/issue/5"}
        if "/git/ref/heads/" in url and method == "GET":
            return 200, {"object": {"sha": "base123"}}
        if url.endswith("/git/refs") and method == "POST":
            return 201, {"ref": payload["ref"], "object": {"sha": payload["sha"]}}
        if "/git/commits/base123" in url and method == "GET":
            return 200, {"tree": {"sha": "tree0"}}
        if url.endswith("/git/blobs") and method == "POST":
            return 201, {"sha": "blob1"}
        if url.endswith("/git/trees") and method == "POST":
            return 201, {"sha": "tree1"}
        if url.endswith("/git/commits") and method == "POST":
            return 201, {"sha": "commit1"}
        if "/git/refs/heads/" in url and method == "PATCH":
            return 200, {"object": {"sha": payload["sha"]}}
        if url.endswith("/pulls") and method == "POST":
            return 201, {"number": 9, "html_url": "https://example/pr/9", "head": {"sha": "commit1"}}
        if "/pulls/9" in url and method == "GET":
            return 200, {"number": 9, "html_url": "https://example/pr/9", "head": {"sha": "commit1"}}
        if "/check-runs" in url and method == "GET":
            return 200, {"check_runs": self.check_runs}
        if "/pulls/9/merge" in url and method == "PUT":
            return 200, {"merged": True, "sha": "merge999"}
        if "/issues/5" in url and method == "PATCH":
            return 200, {"number": 5, "state": "closed"}
        return 500, {"message": "unexpected"}

class GitHubRestAdapterTests(unittest.TestCase):
    def setUp(self):
        self.transport = FakeGitHubTransport()
        self.github = GitHubRestAdapter(repository="owner/repo", token="token-placeholder", transport=self.transport)

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

    def test_pending_and_failed_ci(self):
        self.transport.check_runs = [{"status": "in_progress", "conclusion": None}]
        self.assertEqual(self.github.get_ci_state(9), CIState.PENDING)
        self.transport.check_runs = [{"status": "completed", "conclusion": "failure"}]
        self.assertEqual(self.github.get_ci_state(9), CIState.FAILURE)

    def test_merge_uses_current_head_sha(self):
        sha = self.github.merge_pull_request(9)
        self.assertEqual(sha, "merge999")

    def test_missing_token_fails_fast(self):
        with self.assertRaises(ValueError):
            GitHubRestAdapter(repository="owner/repo", token="", transport=self.transport)

if __name__ == "__main__":
    unittest.main()
