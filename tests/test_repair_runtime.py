import unittest
from unittest.mock import MagicMock

from ai_product_factory.specialist_lane_queue import SpecialistLaneItem,SupabaseSpecialistLaneQueue


def item(role="security"):
    return SpecialistLaneItem(
        job_id="job",run_id="run",project_key="demo",repository="owner/repo",
        role=role,candidate_commit="abc",pr_number=12,issue_number=7,
        manifest={},acceptance_criteria=(),
    )


class RepairRuntimeTests(unittest.TestCase):
    def test_failed_security_lane_queues_bounded_repair(self):
        queue=SupabaseSpecialistLaneQueue.__new__(SupabaseSpecialistLaneQueue)
        queue._rpc=MagicMock(side_effect=[
            {"job_id":"job","status":"failed","run_status":"specialist_review_failed"},
            {"created":True,"repair_job_id":"repair","cycle":1,"max_cycles":3,"status":"repair_pending"},
        ])
        out=queue.complete(
            item("security"),status="failed",
            findings=[{"code":"security_definer","scope_keys":["supabase/migrations/x.sql"]}],
            evidence={"candidate_commit":"abc"},
        )
        self.assertEqual(out["run_status"],"repair_pending")
        self.assertTrue(out["repair"]["created"])
        self.assertEqual(queue._rpc.call_args_list[1].args[0],"factory_enqueue_repair_from_specialist")
        self.assertEqual(queue._rpc.call_args_list[1].args[1]["p_max_cycles"],3)

    def test_failed_operations_lane_never_auto_repairs(self):
        queue=SupabaseSpecialistLaneQueue.__new__(SupabaseSpecialistLaneQueue)
        queue._rpc=MagicMock(return_value={"job_id":"job","status":"failed","run_status":"specialist_review_failed"})
        out=queue.complete(
            item("operations"),status="failed",
            findings=[{"code":"unknown_cost","severity":"error"}],evidence={},
        )
        self.assertNotIn("repair",out)
        self.assertEqual(queue._rpc.call_count,1)

    def test_passed_security_lane_closes_integrated_repair(self):
        queue=SupabaseSpecialistLaneQueue.__new__(SupabaseSpecialistLaneQueue)
        queue._rpc=MagicMock(side_effect=[
            {"job_id":"job","status":"passed","run_status":"preview_ready"},
            {"updated":1,"status":"passed","candidate_commit":"abc"},
        ])
        out=queue.complete(item("security"),status="passed",findings=[],evidence={})
        self.assertEqual(out["repair_recheck"]["updated"],1)
        self.assertEqual(queue._rpc.call_args_list[1].args[0],"factory_close_repairs_after_specialist_pass")


if __name__=="__main__":
    unittest.main()
