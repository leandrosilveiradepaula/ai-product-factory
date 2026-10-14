"""A heartbeat is not proof that the native Factory workflow finished."""
import unittest
from datetime import datetime, timedelta, timezone

from ai_product_factory.github_scheduler_health import (
    GithubNativeScheduledRunReader, evaluate_native_scheduler_health, WORKFLOW_PATH,
)

NOW = datetime(2026, 10, 14, 20, 0, tzinfo=timezone.utc)


def sample(run_id, created, *, conclusion="success", status="completed"):
    return {
        "id": run_id, "created_at": created, "event": "schedule",
        "head_branch": "main", "path": WORKFLOW_PATH,
        "status": status, "conclusion": conclusion,
        "repository": {"full_name": "owner/factory"},
    }


class FakeGitHub:
    repository = "owner/factory"

    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def _call(self, method, path, *, query):
        self.calls.append((method, path, query))
        return {"workflow_runs": self.rows}


def observe(rows):
    client = FakeGitHub(rows)
    state = GithubNativeScheduledRunReader(client).read(now=NOW)
    assert client.calls == [(
        "GET", "/repos/owner/factory/actions/runs",
        {"event": "schedule", "per_page": "30"},
    )]
    return evaluate_native_scheduler_health(state)


class Tests(unittest.TestCase):
    def test_two_timely_completed_successes_are_healthy(self):
        self.assertEqual(observe([
            sample(2, "2026-10-14T19:47:00Z"),
            sample(1, "2026-10-14T19:17:00Z"),
        ]), ())

    def test_october_14_real_failure_is_not_cleared_by_two_heartbeats(self):
        alerts = observe([
            sample(38619635786, "2026-10-14T18:57:54Z", conclusion="failure"),
            sample(38617135076, "2026-10-14T18:40:24Z"),
        ])
        self.assertEqual([x.code for x in alerts], ["scheduler_pipeline"])
        self.assertIn("failure", alerts[0].message)

    def test_one_success_after_failure_does_not_reset_alert(self):
        alerts = observe([
            sample(3, "2026-10-14T19:47:00Z"),
            sample(2, "2026-10-14T19:17:00Z", conclusion="failure"),
        ])
        self.assertEqual(len(alerts), 1)

    def test_current_in_progress_is_not_confused_with_completed_failure(self):
        self.assertEqual(observe([
            sample(3, "2026-10-14T19:59:00Z", conclusion=None, status="in_progress"),
            sample(2, "2026-10-14T19:47:00Z"),
            sample(1, "2026-10-14T19:17:00Z"),
        ]), ())

    def test_one_completed_run_is_insufficient(self):
        self.assertIn("Fewer than two", observe([
            sample(1, "2026-10-14T19:47:00Z"),
        ])[0].message)

    def test_stale_success_pair_still_warns(self):
        self.assertEqual([x.code for x in observe([
            sample(2, "2026-10-14T17:47:00Z"),
            sample(1, "2026-10-14T17:17:00Z"),
        ])], ["scheduler_pipeline"])

    def test_success_pair_with_long_gap_still_warns(self):
        self.assertIn("too far apart", observe([
            sample(2, "2026-10-14T19:47:00Z"),
            sample(1, "2026-10-14T17:17:00Z"),
        ])[0].message)

    def test_skipped_native_workflow_is_not_success(self):
        self.assertEqual(len(observe([
            sample(2, "2026-10-14T19:47:00Z", conclusion="skipped"),
            sample(1, "2026-10-14T19:17:00Z"),
        ])), 1)

    def test_other_scheduled_workflow_does_not_count_as_factory(self):
        other = {**sample(3, "2026-10-14T19:57:00Z"), "path": ".github/workflows/other.yml"}
        self.assertEqual(observe([
            other, sample(2, "2026-10-14T19:47:00Z"),
            sample(1, "2026-10-14T19:17:00Z"),
        ]), ())

    def test_duplicate_id_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "duplicate ID"):
            observe([sample(1, "2026-10-14T19:47:00Z"),
                     sample(1, "2026-10-14T19:17:00Z")])

    def test_different_repo_or_non_native_event_fails_closed(self):
        for change in (
            {"event": "workflow_dispatch"},
            {"head_branch": "feature"},
            {"repository": {"full_name": "someone/other"}},
        ):
            with self.subTest(change=change):
                row = {**sample(2, "2026-10-14T19:47:00Z"), **change}
                with self.assertRaisesRegex(RuntimeError, "untrusted origin"):
                    observe([row, sample(1, "2026-10-14T19:17:00Z")])

    def test_invalid_timestamps_and_order_fail_closed(self):
        for bad in ("missing", "2026-10-14T19:47:00", "2026-10-14T20:30:00Z"):
            with self.subTest(bad=bad):
                with self.assertRaises(RuntimeError):
                    observe([sample(2, bad), sample(1, "2026-10-14T19:17:00Z")])
        with self.assertRaisesRegex(RuntimeError, "not sorted"):
            observe([sample(1, "2026-10-14T19:17:00Z"),
                     sample(2, "2026-10-14T19:47:00Z")])

    def test_unrecognized_run_status_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "unknown status"):
            observe([sample(2, "2026-10-14T19:47:00Z", status="mysterious"),
                     sample(1, "2026-10-14T19:17:00Z")])

    def test_truncated_or_invalid_inventory_is_not_success(self):
        class Malformed:
            repository = "owner/factory"
            def _call(self, method, path, *, query):
                return {"workflow_runs": "not a list"}
        with self.assertRaisesRegex(RuntimeError, "incomplete or malformed"):
            GithubNativeScheduledRunReader(Malformed()).read(now=NOW)

    def test_reader_does_not_modify_github(self):
        client = FakeGitHub([])
        GithubNativeScheduledRunReader(client).read(now=NOW)
        self.assertTrue(all(method == "GET" for method, *_ in client.calls))


if __name__ == "__main__":
    unittest.main()
