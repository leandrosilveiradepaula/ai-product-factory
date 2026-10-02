from datetime import datetime, timedelta, timezone
import unittest

from scripts.preview_budget_guard import (
    decide,
    evaluate_local_budget,
    recent_successful_promotions,
)


NOW = datetime(2026, 10, 2, 18, 0, tzinfo=timezone.utc)


class PreviewBudgetGuardTests(unittest.TestCase):
    def test_local_budget_is_bounded(self):
        self.assertTrue(evaluate_local_budget(4)["allowed"])
        blocked = evaluate_local_budget(5)
        self.assertFalse(blocked["allowed"])
        self.assertEqual(blocked["state"], "blocked_local_budget")

    def test_recent_successful_promotions_only_counts_last_24h(self):
        def transport(method, url, headers, payload):
            self.assertIn("promote-preview-candidate.yml/runs", url)
            return {
                "workflow_runs": [
                    {
                        "id": 1,
                        "status": "completed",
                        "conclusion": "success",
                        "created_at": (NOW - timedelta(hours=2)).isoformat(),
                    },
                    {
                        "id": 2,
                        "status": "completed",
                        "conclusion": "failure",
                        "created_at": (NOW - timedelta(hours=2)).isoformat(),
                    },
                    {
                        "id": 3,
                        "status": "completed",
                        "conclusion": "success",
                        "created_at": (NOW - timedelta(hours=25)).isoformat(),
                    },
                    {
                        "id": 99,
                        "status": "completed",
                        "conclusion": "success",
                        "created_at": (NOW - timedelta(hours=1)).isoformat(),
                    },
                ]
            }

        count = recent_successful_promotions(
            token="github-token",
            repository="owner/repo",
            current_run_id="99",
            now=NOW,
            request_json=transport,
        )
        self.assertEqual(count, 1)

    def test_missing_vercel_credentials_uses_bounded_github_fallback(self):
        def transport(method, url, headers, payload):
            return {"workflow_runs": []}

        decision = decide(
            github_token="github-token",
            repository="owner/repo",
            current_run_id="99",
            now=NOW,
            request_json=transport,
        )
        self.assertTrue(decision["allowed"])
        self.assertEqual(decision["source"], "github_actions")
        self.assertIn("not configured", decision["fallback_reason"])

    def test_vercel_usage_is_authoritative_when_credentials_exist(self):
        def transport(method, url, headers, payload):
            if "api.vercel.com" in url:
                return {
                    "deployments": [
                        {"uid": str(i), "createdAt": int(NOW.timestamp() * 1000), "projectId": "p"}
                        for i in range(95)
                    ],
                    "pagination": {},
                }
            raise AssertionError(url)

        decision = decide(
            github_token="github-token",
            repository="owner/repo",
            current_run_id="99",
            vercel_token="vercel-token",
            team_id="team-id",
            now=NOW,
            request_json=transport,
        )
        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["source"], "vercel_api")
        self.assertEqual(decision["state"], "blocked")


if __name__ == "__main__":
    unittest.main()
