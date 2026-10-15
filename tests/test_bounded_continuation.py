"""Safety and progress regressions for autonomous no-model continuation."""
import unittest
from unittest.mock import Mock

from ai_product_factory.bounded_continuation import (
    ContinuationBlocked, drain_deterministic_lane,
)


class BoundedContinuationTests(unittest.TestCase):
    def test_drains_multiple_distinct_integrations_before_first_empty(self):
        once=Mock(side_effect=[
            {"claimed":True,"status":"integrated","change_set_id":"cs1"},
            {"claimed":True,"status":"integrated","change_set_id":"cs2"},
            {"claimed":False,"status":"empty"},
            {"claimed":True,"status":"integrated","change_set_id":"cs3"},
        ])
        result=drain_deterministic_lane(once,max_items=4,identity="change_set_id")
        self.assertEqual(result["processed"],2)
        self.assertEqual(result["stop_reason"],"empty")
        self.assertEqual(once.call_count,3)

    def test_specialist_lane_is_bounded_even_with_unending_queue(self):
        called=0
        def one():
            nonlocal called
            called+=1
            return {"claimed":True,"status":"completed","job_id":f"job{called}"}
        result=drain_deterministic_lane(one,max_items=3,identity="job_id")
        self.assertEqual(result["processed"],3)
        self.assertEqual(result["stop_reason"],"capacity")
        self.assertEqual(called,3)

    def test_ci_wait_and_unmerged_release_never_spin(self):
        for waiting in ("ci_triggered","wait_ci","awaiting_release","blocked","release_policy_blocked"):
            with self.subTest(waiting=waiting):
                once=Mock(return_value={"claimed":True,"status":waiting,"run_id":"run1"})
                out=drain_deterministic_lane(once,max_items=4)
                self.assertEqual(out["processed"],1)
                self.assertEqual(out["stop_reason"],waiting)
                once.assert_called_once()

    def test_duplicate_run_or_job_fails_closed(self):
        for identity in ("run_id","job_id","change_set_id"):
            with self.subTest(identity=identity):
                once=Mock(return_value={"claimed":True,"status":"completed",identity:"same"})
                with self.assertRaisesRegex(ContinuationBlocked,"repeated"):
                    drain_deterministic_lane(once,max_items=4,identity=identity)
                self.assertEqual(once.call_count,2)

    def test_bad_claim_missing_id_error_or_status_never_appears_successful(self):
        cases=[
            None,{},{"claimed":1,"status":"completed"},
            {"claimed":True,"status":"completed"},
            {"claimed":True,"status":"completed","run_id":"a","error":"upstream"},
            {"claimed":True,"status":"","run_id":"a"},
        ]
        for item in cases:
            with self.subTest(item=item),self.assertRaises(ContinuationBlocked):
                drain_deterministic_lane(lambda:item,max_items=2)

    def test_empty_queue_does_not_invoke_other_stages(self):
        once=Mock(return_value={"claimed":False,"status":"empty"})
        self.assertEqual(drain_deterministic_lane(once,max_items=4)["processed"],0)
        once.assert_called_once()

    def test_bad_bounds_and_non_allowlisted_identity_rejected_before_worker(self):
        once=Mock()
        for value in (0,5,-1,True,1.0):
            with self.subTest(value=value),self.assertRaises(ValueError):
                drain_deterministic_lane(once,max_items=value)
        with self.assertRaises(ValueError):
            drain_deterministic_lane(once,identity="PR")
        once.assert_not_called()

    def test_release_can_observe_distinct_human_merges_but_cannot_execute_merge(self):
        calls=iter([
            {"claimed":True,"status":"merged","run_id":"r1"},
            {"claimed":True,"status":"merged","run_id":"r2"},
            {"claimed":False,"status":"empty"},
        ])
        result=drain_deterministic_lane(lambda:next(calls),max_items=4)
        self.assertEqual([i["id"] for i in result["items"]],["r1","r2"])
        # Any actual human merge is still observed by run_release_once, not here.


if __name__=="__main__":
    unittest.main()
