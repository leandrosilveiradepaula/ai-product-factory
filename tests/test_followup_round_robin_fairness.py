"""Fair scheduling across independent wakes without replay or paid calls."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ai_product_factory.bounded_continuation import (
    ContinuationBlocked, drain_fair_waiting_followups,
)
from ai_product_factory.followup_fair_cursor import SupabaseFollowupFairCursor
from ai_product_factory.followup_active_project_query import active_project_followup_query
from ai_product_factory.runtime_cli import run_ci_once, run_release_once


class Cursor:
    def __init__(self, offset=0):
        self.offset=offset
        self.reservations=[]
    def read_offset(self, lane):
        return self.offset
    def reserve_next(self, lane, offset):
        self.reservations.append((lane,offset))
        self.offset=offset


def worker(rows):
    def once(ignored,offset):
        for row in rows[offset:offset+12]:
            if row["run_id"] not in ignored:
                return row
        return {"claimed":False,"status":"empty"}
    return once


class FairContinuationTests(unittest.TestCase):
    def test_eight_ci_waits_cannot_permanently_mask_ninth(self):
        rows=[{"claimed":True,"status":"wait_dispatched_ci","run_id":str(n)} for n in range(8)]
        rows.append({"claimed":True,"status":"specialist_review_pending","run_id":"ninth"})
        cursor=Cursor()
        first=drain_fair_waiting_followups(worker(rows),lane="ci",cursor=cursor)
        self.assertEqual((first["processed"],first["observed_waiting"]),(0,8))
        second=drain_fair_waiting_followups(worker(rows),lane="ci",cursor=cursor)
        self.assertEqual(second["items"],[{"id":"ninth","status":"specialist_review_pending"}])
        self.assertEqual(second["fair_scan_start"],8)

    def test_drift_is_waiting_and_merge_is_observed_only(self):
        rows=[{"claimed":True,"status":"candidate_drift_blocked","run_id":str(n)} for n in range(8)]
        rows.append({"claimed":True,"status":"merged","run_id":"later"})
        cursor=Cursor()
        self.assertEqual(drain_fair_waiting_followups(worker(rows),lane="release",cursor=cursor)["processed"],0)
        self.assertEqual(drain_fair_waiting_followups(worker(rows),lane="release",cursor=cursor)["items"][0]["id"],"later")

    def test_queue_shrink_wraps_during_same_wake(self):
        cursor=Cursor(16)
        result=drain_fair_waiting_followups(
            worker([{"claimed":True,"status":"merged","run_id":"first"}]),
            lane="release",cursor=cursor)
        self.assertEqual(result["processed"],1)
        self.assertTrue(result["fair_scan_wrapped"])
        self.assertEqual(cursor.reservations,[("release",24),("release",8)])

    def test_cursor_failure_prevents_worker(self):
        cursor=Cursor()
        cursor.reserve_next=Mock(side_effect=RuntimeError("audit unavailable"))
        once=Mock()
        with self.assertRaisesRegex(RuntimeError,"audit unavailable"):
            drain_fair_waiting_followups(once,lane="ci",cursor=cursor)
        once.assert_not_called()

    def test_invalid_cursor_and_window_fail_closed(self):
        for offset in (-1,1000001,True):
            with self.subTest(offset=offset),self.assertRaises(ContinuationBlocked):
                drain_fair_waiting_followups(Mock(),lane="ci",cursor=Cursor(offset))
        for offset in (-1,1000001,True,1.5):
            with self.subTest(offset=offset),self.assertRaises(ValueError):
                active_project_followup_query(status="ci_pending",limit=1,offset=offset)
        self.assertIn("&offset=16",active_project_followup_query(status="ci_pending",limit=12,offset=16))

    def test_ci_drift_returns_waiting_receipt_without_writes(self):
        item=SimpleNamespace(project_key="platform",project_id="123e4567-e89b-42d3-a456-426614174000",
                             run_id="run",pr_number=3,repository="owner/repo",
                             candidate_commit="a"*40,change_set_id=None)
        with patch("ai_product_factory.runtime_cli.SupabaseCIFollowupQueue") as queue, \
             patch("ai_product_factory.runtime_cli._assert_project_followup"), \
             patch("ai_product_factory.runtime_cli.GitHubRestAdapter") as github, \
             patch("ai_product_factory.runtime_cli.SupabaseDeliveryStore") as store:
            queue.return_value.next_pending.return_value=item
            github.return_value.get_pull_request.return_value=SimpleNamespace(head_sha="b"*40)
            result=run_ci_once()
        self.assertEqual(result["status"],"candidate_drift_blocked")
        self.assertTrue(result["claimed"])
        store.assert_not_called()

    def test_release_drift_does_not_mutate_or_merge(self):
        item=SimpleNamespace(project_key="platform",project_id="123e4567-e89b-42d3-a456-426614174000",
                             run_id="run",pr_number=3,repository="owner/repo",candidate_commit="a"*40)
        with patch("ai_product_factory.runtime_cli.SupabaseReleaseFollowupQueue") as queue, \
             patch("ai_product_factory.runtime_cli._assert_project_followup"), \
             patch("ai_product_factory.runtime_cli.GitHubRestAdapter") as github, \
             patch("ai_product_factory.runtime_cli.SupabaseDeliveryStore") as store:
            queue.return_value.next_pending.return_value=item
            github.return_value.get_pull_request.return_value=SimpleNamespace(head_sha="b"*40)
            result=run_release_once()
        self.assertEqual(result["status"],"candidate_drift_blocked")
        self.assertTrue(result["claimed"])
        store.assert_not_called()


class AuditCursorTests(unittest.TestCase):
    def cursor(self):
        return SupabaseFollowupFairCursor(url="https://x.supabase.co",secret_key="sb_secret_test")

    class Response:
        def __init__(self,data): self.data=data
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def read(self): return json.dumps(self.data).encode()

    def test_empty_history_starts_at_zero(self):
        with patch("urllib.request.urlopen",return_value=self.Response([])):
            self.assertEqual(self.cursor().read_offset("ci"),0)

    def test_event_has_lane_scoped_durable_receipt(self):
        with patch("urllib.request.urlopen",return_value=self.Response([
            {"id":42,"payload":{"version":1,"lane":"release","next_offset":24}}
        ])):
            self.assertEqual(self.cursor().read_offset("release"),24)
        with patch("urllib.request.urlopen",return_value=self.Response([])) as network:
            self.cursor().reserve_next("ci",16)
        request=network.call_args.args[0]
        self.assertEqual(request.method,"POST")
        event=json.loads(request.data)
        self.assertEqual(event["event_type"],"followup.fair_scan_reserved")
        self.assertEqual(event["payload"],{"version":1,"lane":"ci","next_offset":16})

    def test_bad_history_and_invalid_reservation_fail_closed(self):
        for payload in ({"version":1,"lane":"ci","next_offset":17},
                        {"version":1,"lane":"ci","next_offset":True},
                        {"version":1,"lane":"release","next_offset":8}):
            with self.subTest(payload=payload),patch("urllib.request.urlopen",return_value=self.Response([{"id":1,"payload":payload}])):
                with self.assertRaises(RuntimeError):
                    self.cursor().read_offset("ci")
        with patch("urllib.request.urlopen") as network:
            with self.assertRaises(ValueError):self.cursor().reserve_next("ci",7)
            with self.assertRaises(ValueError):self.cursor().reserve_next("invalid",8)
            network.assert_not_called()


if __name__=="__main__":
    unittest.main()
