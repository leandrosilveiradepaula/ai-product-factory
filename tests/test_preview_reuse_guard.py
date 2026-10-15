"""An unchanged exact Preview ref must not be mistaken for a deployed site."""
from datetime import datetime, timedelta, timezone
import unittest

from scripts.preview_reuse_guard import inspect_reused_preview

NOW = datetime(2026, 10, 15, 22, 26, tzinfo=timezone.utc)
SHA = "a" * 40
READY = {
    "context": "Vercel", "state": "success",
    "description": "Deployment has completed",
    "updated_at": NOW.isoformat(),
    "target_url": "https://vercel.com/team/ai-product-factory-console/dpl_ready",
}
LIMIT = {
    "context": "Vercel", "state": "failure",
    "description": "Deployment rate limited — retry in 24 hours.",
    "updated_at": NOW.isoformat(),
    "target_url": "https://vercel.com/team?upgradeToPro=build-rate-limit",
}


class ReusedPreviewEvidenceGuardTests(unittest.TestCase):
    def decide(self, rows, *, sha=SHA, token="test", now=NOW):
        def fetch(method, url, headers):
            self.assertEqual(method, "GET")
            self.assertEqual(
                url, "https://api.github.com/repos/example/factory/commits/"
                + SHA + "/status"
            )
            self.assertEqual(headers["Authorization"], "Bearer test")
            return {"statuses": rows}
        return inspect_reused_preview(
            token=token, repository="example/factory", sha=sha,
            now=now, get_json=fetch,
        )

    def test_completed_deployment_can_proceed_to_real_browser_checks(self):
        result = self.decide([READY])
        self.assertTrue(result["allowed"])
        self.assertFalse(result["authoritative_quota"])
        self.assertEqual(result["state"], "confirmed_deployment_on_exact_sha")
        self.assertEqual(result["candidate_sha"], SHA)

    def test_reused_ref_with_no_vercel_status_is_not_ready(self):
        result = self.decide([])
        self.assertFalse(result["allowed"])
        self.assertEqual(result["state"], "no_vercel_deployment_evidence")

    def test_rate_limit_with_prior_success_stays_blocked(self):
        older = {**READY, "updated_at": (NOW - timedelta(minutes=20)).isoformat()}
        result = self.decide([older, LIMIT])
        self.assertFalse(result["allowed"])
        self.assertEqual(result["state"], "provider_rate_limited")

    def test_newer_genuine_success_can_be_rechecked_without_new_ref(self):
        older = {**LIMIT, "updated_at": (NOW - timedelta(minutes=20)).isoformat()}
        result = self.decide([older, READY])
        self.assertTrue(result["allowed"])

    def test_newest_ignored_build_is_not_ready(self):
        ignored = {
            **READY, "description": "Canceled by Ignored Build Step",
        }
        self.assertFalse(self.decide([ignored])["allowed"])

    def test_success_from_different_provider_context_is_not_evidence(self):
        other = {**READY, "context": "Factory Preview browser evidence"}
        self.assertEqual(
            self.decide([other])["state"], "no_vercel_deployment_evidence"
        )

    def test_vercel_success_requires_actual_deployment_detail_url(self):
        for url in (
            None, "http://vercel.com/team/project/dpl_real",
            "https://vercel.com/team?upgradeToPro=build-rate-limit",
            "https://other.example/team/project/dpl_fake",
        ):
            with self.subTest(url=url):
                self.assertFalse(self.decide([{**READY, "target_url": url}])["allowed"])

    def test_pending_and_generic_failure_are_not_ready(self):
        for state, description in (("pending", "Building"), ("failure", "Build error")):
            with self.subTest(state=state):
                self.assertFalse(
                    self.decide([{**READY, "state": state, "description": description}])["allowed"]
                )

    def test_ambiguous_last_timestamp_is_fail_closed(self):
        result = self.decide([READY, LIMIT])
        self.assertEqual(result["state"], "ambiguous_vercel_status")
        self.assertFalse(result["allowed"])

    def test_no_unbounded_or_malformed_commit_status_inventory(self):
        for rows in ([READY] * 101, [{"context": "Vercel"}], ["invalid"]):
            with self.subTest(case=str(rows)[:40]):
                with self.assertRaises(RuntimeError):
                    self.decide(rows)

    def test_future_vercel_status_rejected(self):
        future = {**READY, "updated_at": (NOW + timedelta(minutes=6)).isoformat()}
        with self.assertRaisesRegex(RuntimeError, "clock tolerance"):
            self.decide([future])

    def test_invalid_token_or_sha_rejected_without_fetching(self):
        for token, sha in (("", SHA), ("test", "abc")):
            with self.assertRaises(RuntimeError):
                self.decide([], token=token, sha=sha)

    def test_workflow_blocks_browser_on_reused_ref_without_deployment(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        workflow = (root / ".github/workflows/promote-preview-candidate.yml").read_text()
        self.assertIn("name: Require READY Vercel evidence before reusing Preview ref", workflow)
        self.assertIn("run: python -m scripts.preview_reuse_guard", workflow)
        self.assertIn("steps.verify.outputs.promotion_action == 'reused'", workflow)
        self.assertIn("if: steps.resolve.outputs.applicable == 'true' && steps.verify.outputs.promotion_action == 'reused'", workflow)
        self.assertIn("REUSE_GUARD_OUTCOME: ${{ steps.reuse_guard.outcome }}", workflow)
        self.assertIn("blocked_reused_ref_without_vercel_ready", workflow)
        self.assertIn("Ensure exact Preview browser evidence", workflow)
        self.assertIn("if: always() && !cancelled()", workflow)


if __name__ == "__main__":
    unittest.main()
