from datetime import datetime, timedelta, timezone
import unittest

from scripts.preview_budget_guard import (
    decide,
    evaluate_local_budget,
    recent_successful_promotions,
)


NOW = datetime(2026, 10, 2, 18, 0, tzinfo=timezone.utc)


class PreviewBudgetGuardTests(unittest.TestCase):
    def test_local_observation_never_invents_provider_quota(self):
        normal = evaluate_local_budget(4)
        self.assertTrue(normal["allowed"])
        self.assertEqual(normal["state"], "local_observation")
        self.assertFalse(normal["authoritative"])

        high = evaluate_local_budget(5)
        self.assertTrue(high["allowed"])
        self.assertEqual(high["state"], "local_observation_high")
        self.assertFalse(high["authoritative"])
        self.assertIn("advisory only", high["reason"])

    def test_recent_successful_promotions_only_counts_real_ref_updates(self):
        def transport(method, url, headers, payload):
            if "promote-preview-candidate.yml/runs" in url:
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
            if "/actions/runs/1/jobs" in url:
                return {
                    "jobs": [{
                        "steps": [{
                            "name": "Create or update one preview ref to the exact candidate",
                            "conclusion": "skipped",
                        }]
                    }]
                }
            if "/actions/runs/2/jobs" in url:
                return {
                    "jobs": [{
                        "steps": [{
                            "name": "Create or update one preview ref to the exact candidate",
                            "conclusion": "success",
                        }]
                    }]
                }
            raise AssertionError(url)

        count = recent_successful_promotions(
            token="github-token",
            repository="owner/repo",
            current_run_id="99",
            now=NOW,
            request_json=transport,
        )
        self.assertEqual(count, 1)


    def test_standard_preview_path_uses_advisory_github_observation(self):
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
        self.assertFalse(decision["authoritative"])
        self.assertIn("outside the standard Preview promotion path", decision["fallback_reason"])


    def test_high_local_count_does_not_block_without_provider_quota(self):
        def transport(method, url, headers, payload):
            if "promote-preview-candidate.yml/runs" in url:
                return {
                    "workflow_runs": [
                        {
                            "id": i,
                            "status": "completed",
                            "conclusion": "success",
                            "created_at": (NOW - timedelta(hours=1)).isoformat(),
                        }
                        for i in range(1, 7)
                    ]
                }
            if "/jobs" in url:
                return {
                    "jobs": [{
                        "steps": [{
                            "name": "Create or update one preview ref to the exact candidate",
                            "conclusion": "success",
                        }]
                    }]
                }
            raise AssertionError(url)

        decision = decide(
            github_token="github-token",
            repository="owner/repo",
            current_run_id="99",
            now=NOW,
            request_json=transport,
        )
        self.assertTrue(decision["allowed"])
        self.assertEqual(decision["state"], "local_observation_high")
        self.assertEqual(decision["used"], 6)
        self.assertFalse(decision["authoritative"])

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
