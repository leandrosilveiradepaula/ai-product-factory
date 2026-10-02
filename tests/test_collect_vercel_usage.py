from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse
import unittest

from scripts.collect_vercel_usage import collect, list_team_deployments


class CollectorTests(unittest.TestCase):
    def test_paginates_and_deduplicates(self):
        calls = []

        def transport(method, url, headers, payload):
            calls.append((method, url, headers, payload))
            if len(calls) == 1:
                return {"deployments": [
                    {"uid": "new", "createdAt": 1200, "projectId": "factory"},
                    {"uid": "boundary", "createdAt": 900, "projectId": "crm"},
                ], "pagination": {"next": 900}}
            return {"deployments": [
                {"uid": "boundary", "createdAt": 900, "projectId": "crm"},
                {"uid": "old", "createdAt": 400, "projectId": "factory"},
            ], "pagination": {"next": 400}}

        rows = list_team_deployments(
            token="vercel-test-token", team_id="team-test", since_ms=500, request_json=transport
        )
        self.assertEqual({row["uid"] for row in rows}, {"new", "boundary"})
        self.assertEqual(len(calls), 2)
        self.assertEqual(parse_qs(urlparse(calls[1][1]).query)["until"], ["900"])

    def test_records_rolling_daily_snapshot_via_broker(self):
        calls = []

        def transport(method, url, headers, payload):
            calls.append((method, url, headers, payload))
            if method == "GET":
                return {"deployments": [
                    {"uid": "a", "createdAt": 1_800_000_000_000, "projectId": "factory"},
                    {"uid": "b", "createdAt": 1_800_000_000_000, "projectId": "crm"},
                ], "pagination": {}}
            return "snapshot-id"

        result = collect(
            vercel_token="vercel-test-token",
            team_id="team-test",
            supabase_url="https://supabase.test/functions/v1/factory-runtime-control-plane",
            oidc_token="oidc-test-token",
            now=datetime.fromtimestamp(1_800_000_001, tz=timezone.utc),
            request_json=transport,
        )
        method, url, headers, payload = calls[-1]
        self.assertEqual(result["used"], 2)
        self.assertEqual(method, "POST")
        self.assertTrue(url.endswith("/rest/v1/rpc/factory_record_resource_limit"))
        self.assertEqual(headers["Authorization"], "Bearer oidc-test-token")
        self.assertEqual(payload["p_used_value"], 2)
        self.assertEqual(payload["p_limit_value"], 100)
        self.assertEqual(payload["p_window_key"], "rolling_24h")
        self.assertEqual(payload["p_metadata"], {"project_counts": {"crm": 1, "factory": 1}})


if __name__ == "__main__":
    unittest.main()
