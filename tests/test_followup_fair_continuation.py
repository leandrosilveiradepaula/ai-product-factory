"""Continue autonomous CI/release followup past unrelated waits, fail-closed."""
import json
import unittest
from unittest.mock import Mock, patch

from ai_product_factory.bounded_continuation import (
    ContinuationBlocked, drain_waiting_followups,
)
from ai_product_factory.ci_followup_queue import SupabaseCIFollowupQueue
from ai_product_factory.release_followup_queue import SupabaseReleaseFollowupQueue


class TestFairFollowup(unittest.TestCase):
    def test_human_gate_does_not_starve_later_observed_merge(self):
        def consume(excluded):
            for row in (
                {"claimed":True,"status":"awaiting_release","run_id":"old"},
                {"claimed":True,"status":"merged","run_id":"new"},
            ):
                if row["run_id"] not in excluded:
                    return row
            return {"claimed":False,"status":"empty"}
        result=drain_waiting_followups(consume,max_items=3)
        self.assertEqual(result["processed"],1)
        self.assertEqual(result["observed_waiting"],1)
        self.assertEqual(result["items"],[{"id":"new","status":"merged"}])
        self.assertEqual(result["stop_reason"],"empty")

    def test_ci_pending_does_not_starve_next_ready_candidate(self):
        rows=[
            {"claimed":True,"status":"ci_triggered","run_id":"a"},
            {"claimed":True,"status":"specialist_review_pending","run_id":"b"},
            {"claimed":True,"status":"specialist_review_pending","run_id":"c"},
            {"claimed":True,"status":"specialist_review_pending","run_id":"d"},
        ]
        seen=[]
        def consume(excluded):
            seen.append(excluded)
            return next((x for x in rows if x["run_id"] not in excluded),{"claimed":False,"status":"empty"})
        result=drain_waiting_followups(consume,max_items=3)
        self.assertEqual(result["processed"],3)
        self.assertEqual(result["observed_waiting"],1)
        self.assertEqual(result["stop_reason"],"capacity")
        self.assertEqual(seen[1],("a",))
        self.assertEqual(seen[3],("a","b","c"))

    def test_only_waiting_never_claims_product_done_or_merges(self):
        calls=[]
        def consume(ignored):
            calls.append(ignored)
            if len(calls)<=3:
                return {"claimed":True,"status":"awaiting_release","run_id":str(len(calls))}
            return {"claimed":False,"status":"empty"}
        result=drain_waiting_followups(consume,max_items=3)
        self.assertEqual(result["status"],"waiting")
        self.assertEqual(result["processed"],0)
        self.assertEqual(result["observed_waiting"],3)
        self.assertEqual(len(calls),4)

    def test_same_durable_item_twice_is_error_not_infinite_loop(self):
        with self.assertRaisesRegex(ContinuationBlocked,"repeated"):
            drain_waiting_followups(
                lambda ignored:{"claimed":True,"status":"awaiting_release","run_id":"same"},
                max_items=3,
            )

    def test_invalid_bounds_payload_and_missing_identity_refused(self):
        f=Mock()
        for items,observations in ((0,8),(5,8),(1,9),(3,2),(True,8)):
            with self.subTest(items=items,observations=observations):
                with self.assertRaises(ValueError):
                    drain_waiting_followups(f,max_items=items,max_observations=observations)
        f.assert_not_called()
        for row in (None,{},{"claimed":1,"status":"waiting"},
                    {"claimed":True,"status":"merged"},
                    {"claimed":True,"status":"merged","run_id":"x","error":"no"},
                    {"claimed":True,"status":"","run_id":"x"}):
            with self.subTest(row=row),self.assertRaises(ContinuationBlocked):
                drain_waiting_followups(lambda _:row,max_items=1)

    def test_empty_returns_without_repeating_selection(self):
        f=Mock(return_value={"claimed":False,"status":"empty"})
        out=drain_waiting_followups(f,max_items=3)
        self.assertEqual(out["processed"],0)
        f.assert_called_once_with(())

    def test_read_only_ci_selector_skips_older_candidate(self):
        rows=[{"id":"one"},{"id":"two"},{"id":"three"}]
        queue=SupabaseCIFollowupQueue(url="https://x.supabase.co",secret_key="sb_secret_test")
        with patch.object(queue,"_get",return_value=rows) as get:
            with self.assertRaises(KeyError):
                queue.next_pending(exclude_run_ids=("one",))
        self.assertIn("limit=12",get.call_args.args[0])
        # The second item is selected, then its absent detail is correctly fail-closed.
        # Ensure no database write is introduced by this read-only selector.
        self.assertEqual(get.call_count,1)

    def test_release_selector_can_skip_waiting_first_record(self):
        rows=[{"id":"old"},{"id":"new"},{"id":"newest"}]
        queue=SupabaseReleaseFollowupQueue(url="https://x.supabase.co",secret_key="sb_secret_test")
        with patch.object(queue,"_get",return_value=rows) as get:
            with self.assertRaises(KeyError):
                queue.next_pending(exclude_run_ids=("old",))
        self.assertIn("limit=12",get.call_args.args[0])
        self.assertEqual(get.call_count,1)

    def test_queue_exclusions_are_bounded_and_rejected_before_http(self):
        for klass in (SupabaseCIFollowupQueue,SupabaseReleaseFollowupQueue):
            queue=klass(url="https://x.supabase.co",secret_key="sb_secret_test")
            with patch.object(queue,"_get") as get:
                for bad in ((None,),("a",)*9,["not-a-tuple"],("  ",)):
                    with self.subTest(queue=klass.__name__,bad=bad),self.assertRaises(ValueError):
                        queue.next_pending(exclude_run_ids=bad)
                get.assert_not_called()


if __name__=="__main__":
    unittest.main()
