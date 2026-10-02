from datetime import datetime, timedelta, timezone
import unittest

from scripts.vercel_preview_guard import evaluate_quota


NOW = datetime(2026, 10, 2, 18, 0, tzinfo=timezone.utc)


def snapshot(*, used=50, limit=100, quality="derived", age_hours=1):
    return {
        "used_value": used,
        "limit_value": limit,
        "quality": quality,
        "observed_at": (NOW - timedelta(hours=age_hours)).isoformat(),
    }


class VercelPreviewGuardTests(unittest.TestCase):
    def test_normal_attention_protection_and_blocked_thresholds(self):
        self.assertEqual(evaluate_quota(snapshot(used=69), now=NOW)["state"], "normal")
        self.assertEqual(evaluate_quota(snapshot(used=70), now=NOW)["state"], "attention")
        self.assertEqual(evaluate_quota(snapshot(used=85), now=NOW)["state"], "protection")
        blocked = evaluate_quota(snapshot(used=95), now=NOW)
        self.assertEqual(blocked["state"], "blocked")
        self.assertFalse(blocked["allowed"])

    def test_stale_snapshot_fails_closed(self):
        decision = evaluate_quota(snapshot(age_hours=9), now=NOW)
        self.assertEqual(decision["state"], "blocked_stale")
        self.assertFalse(decision["allowed"])

    def test_unknown_quality_fails_closed(self):
        decision = evaluate_quota(snapshot(quality="unknown"), now=NOW)
        self.assertEqual(decision["state"], "blocked_unknown")
        self.assertFalse(decision["allowed"])

    def test_missing_usage_fails_closed(self):
        decision = evaluate_quota(snapshot(used=None), now=NOW)
        self.assertEqual(decision["state"], "blocked_unknown")
        self.assertFalse(decision["allowed"])


if __name__ == "__main__":
    unittest.main()
