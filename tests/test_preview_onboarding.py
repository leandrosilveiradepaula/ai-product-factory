import unittest

from ai_product_factory.preview_onboarding import detect_github_vercel_preview_policy


class PreviewOnboardingTests(unittest.TestCase):
    def test_detects_vercel_github_from_commit_status(self):
        out=detect_github_vercel_preview_policy(
            manifest={},
            default_branch="main",
            commit_sha="abc123",
            statuses=[{
                "id":7,
                "context":"Vercel",
                "state":"success",
                "target_url":"https://vercel.com/team/project/deployment",
            }],
            checks=[],
        )
        self.assertEqual(out.policy,{"provider":"vercel","mode":"github","required":True})
        self.assertEqual(out.evidence["source"],"github_vercel_integration")
        self.assertEqual(out.evidence["commit_sha"],"abc123")
        self.assertEqual(out.evidence["signals"][0]["kind"],"commit_status")

    def test_detects_vercel_github_from_check_app(self):
        out=detect_github_vercel_preview_policy(
            manifest={},
            default_branch="main",
            commit_sha="abc123",
            statuses=[],
            checks=[{
                "id":8,
                "name":"Vercel Preview Comments",
                "status":"completed",
                "conclusion":"success",
                "app":{"slug":"vercel"},
            }],
        )
        self.assertIsNotNone(out.policy)
        self.assertEqual(out.evidence["signals"][0]["kind"],"check_run")

    def test_preserves_explicit_non_preview_policy(self):
        existing={"required":False,"reason":"backend only"}
        out=detect_github_vercel_preview_policy(
            manifest={"preview":existing},
            default_branch="main",
            commit_sha="abc123",
            statuses=[{
                "context":"Vercel",
                "state":"success",
                "target_url":"https://vercel.com/team/project/deployment",
            }],
            checks=[],
        )
        self.assertIsNone(out.policy)
        self.assertEqual(out.reason,"existing_policy_preserved")
        self.assertEqual(out.evidence["preview"],existing)

    def test_absence_of_vercel_evidence_never_disables_preview(self):
        out=detect_github_vercel_preview_policy(
            manifest={},
            default_branch="main",
            commit_sha="abc123",
            statuses=[{
                "context":"ci",
                "state":"success",
                "target_url":"https://github.com/owner/repo/actions/runs/1",
            }],
            checks=[],
        )
        self.assertIsNone(out.policy)
        self.assertEqual(out.reason,"no_vercel_integration_evidence")

    def test_rejects_context_named_vercel_without_vercel_target(self):
        out=detect_github_vercel_preview_policy(
            manifest={},
            default_branch="main",
            commit_sha="abc123",
            statuses=[{
                "context":"Vercel",
                "state":"success",
                "target_url":"https://example.com/not-vercel",
            }],
            checks=[],
        )
        self.assertIsNone(out.policy)


if __name__=="__main__":
    unittest.main()
