import unittest
from unittest.mock import patch

from ai_product_factory.github_capability_preflight import GitHubCapabilityPreflight
from ai_product_factory.github_rest import GitHubRestAdapter
from ai_product_factory.project_github_access import ProjectGitHubAccessItem


class Transport:
    def __init__(self, *, actions_status=200, checks_status=403):
        self.actions_status=actions_status
        self.checks_status=checks_status

    def __call__(self, method, url, headers, body):
        if url.endswith("/repos/owner/repo"):
            return 200, {"id":123,"default_branch":"main"}
        if "/contents?" in url:
            return 200, []
        if "/issues?" in url:
            return 200, []
        if "/pulls?" in url:
            return 200, []
        if "/actions/runs?" in url:
            return self.actions_status, {"workflow_runs":[]}
        if "/git/ref/heads/main" in url:
            return 200, {"object":{"sha":"abc"}}
        if "/commits/abc/status" in url:
            return 200, {"statuses":[]}
        if "/commits/abc/check-runs?" in url:
            return self.checks_status, {"check_runs":[]}
        raise AssertionError(url)


def item():
    return ProjectGitHubAccessItem(
        project_id="p",
        project_key="crm",
        repository="owner/repo",
        auth_mode="fine_grained_pat",
        observed_capabilities={},
    )


class Tests(unittest.TestCase):
    def test_fine_grained_pat_uses_actions_and_statuses_when_checks_are_unavailable(self):
        github=GitHubRestAdapter(repository="owner/repo",token="token",transport=Transport())
        with patch.dict("os.environ",{},clear=True):
            out=GitHubCapabilityPreflight(github).run(item())
        self.assertEqual(out.status,"partial")
        self.assertEqual(out.observed_capabilities["actions_read"],"verified")
        self.assertEqual(out.observed_capabilities["commit_statuses_read"],"verified")
        self.assertEqual(out.observed_capabilities["ci_evidence_read"],"verified")
        self.assertEqual(out.observed_capabilities["contents_write"],"unverified")
        self.assertIn("write capabilities",out.error)

    def test_missing_required_read_capability_blocks(self):
        github=GitHubRestAdapter(repository="owner/repo",token="token",transport=Transport(actions_status=403))
        with patch.dict("os.environ",{},clear=True):
            out=GitHubCapabilityPreflight(github).run(item())
        self.assertEqual(out.status,"blocked")
        self.assertEqual(out.observed_capabilities["actions_read"],"missing")
        self.assertEqual(out.observed_capabilities["ci_evidence_read"],"missing")
        self.assertIn("actions_read",out.error)

    def test_native_repository_write_capabilities_are_backed_by_workflow_policy(self):
        github=GitHubRestAdapter(repository="owner/repo",token="token",transport=Transport(checks_status=200))
        with patch.dict("os.environ",{"GITHUB_REPOSITORY":"owner/repo"},clear=True):
            out=GitHubCapabilityPreflight(github).run(item())
        self.assertEqual(out.auth_mode,"native_github_token")
        self.assertEqual(out.status,"ready")
        self.assertEqual(out.observed_capabilities["contents_write"],"verified")
        self.assertIsNone(out.error)


if __name__=="__main__":
    unittest.main()
