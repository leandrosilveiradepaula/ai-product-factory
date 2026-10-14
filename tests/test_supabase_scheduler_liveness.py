"""Read-only liveness alerts for missing GitHub scheduler wakes."""
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from ai_product_factory.supabase_scheduler_liveness import (
    SupabaseSchedulerLivenessReader, evaluate_scheduler_liveness
)

class Response:
    def __init__(self, payload): self.payload=payload
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self): return json.dumps(self.payload).encode()

NOW=datetime(2026,10,14,11,30,tzinfo=timezone.utc)
def probe(rows):
    with patch("urllib.request.urlopen",return_value=Response(rows)) as urlopen:
        state=SupabaseSchedulerLivenessReader(
            url="https://example.supabase.co",secret_key="sb_secret_unit"
        ).read(now=NOW)
    req=urlopen.call_args.args[0]
    assert req.get_method()=="GET"
    assert "schedule_probe.observed" in req.full_url
    return state

class Tests(unittest.TestCase):
    def test_recent_normal_cadence_no_alert(self):
        state=probe([
            {"created_at":"2026-10-14T11:17:00Z"},
            {"created_at":"2026-10-14T10:47:00Z"}
        ])
        self.assertEqual(evaluate_scheduler_liveness(state),())

    def test_old_latest_wake_generates_warning(self):
        state=probe([
            {"created_at":"2026-10-14T08:03:00Z"},
            {"created_at":"2026-10-14T07:42:00Z"}
        ])
        alerts=evaluate_scheduler_liveness(state)
        self.assertEqual([a.code for a in alerts],["scheduler_gap"])
        self.assertIn("207 minutes",alerts[0].message)

    def test_gap_visible_after_schedule_recovers(self):
        state=probe([
            {"created_at":"2026-10-14T11:20:00Z"},
            {"created_at":"2026-10-14T08:03:00Z"}
        ])
        self.assertIn("197 minutes",evaluate_scheduler_liveness(state)[0].message)

    def test_one_recent_bootstrap_wake_no_false_gap(self):
        state=probe([{"created_at":"2026-10-14T11:17:00Z"}])
        self.assertEqual(evaluate_scheduler_liveness(state),())

    def test_zero_wakes_is_not_silently_green(self):
        state=probe([])
        self.assertEqual(evaluate_scheduler_liveness(state)[0].code,"scheduler_gap")

    def test_malformed_response_fails_before_resolving_issue(self):
        with self.assertRaisesRegex(RuntimeError,"malformed rows"):
            probe([{"created_at":"2026-10-14T11:20:00Z"}, "bad"])

    def test_missing_timestamp_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError,"no valid timestamp"):
            probe([{"wrong":"field"}])

    def test_wrong_order_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError,"not sorted"):
            probe([{"created_at":"2026-10-14T08:03:00Z"},
                   {"created_at":"2026-10-14T11:17:00Z"}])

    def test_clock_skew_future_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError,"in the future"):
            probe([{"created_at":"2026-10-14T12:00:00Z"}])

    def test_null_second_record_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError,"malformed rows"):
            probe([{"created_at":"2026-10-14T11:17:00Z"},None])

if __name__=="__main__": unittest.main()
