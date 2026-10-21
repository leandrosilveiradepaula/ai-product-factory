import unittest
from unittest.mock import MagicMock

from ai_product_factory.specialist_lane_queue import SpecialistLaneItem,SupabaseSpecialistLaneQueue


def item(role="security"):
    return SpecialistLaneItem(
        job_id="job",run_id="run",project_key="demo",repository="owner/repo",
        role=role,candidate_commit="abc",pr_number=12,issue_number=7,
        manifest={},acceptance_criteria=(),
        claim_token="123e4567-e89b-42d3-a456-426614174099",
    )


class RepairRuntimeTests(unittest.TestCase):
    def test_failed_security_lane_commits_one_atomic_repair_rpc(self):
        queue=SupabaseSpecialistLaneQueue.__new__(SupabaseSpecialistLaneQueue)
        queue._rpc=MagicMock(return_value={
            "job_id":"job","status":"failed","run_status":"repair_pending",
            "post_review_applied":True,
            "traceability_recorded":True,
            "traceability":{"requirements_linked":0,"dod_checks_linked":0},
            "repair":{"created":True,"repair_job_id":"repair","cycle":1,"max_cycles":3},
            "repair_recheck":None,
        })
        findings=[{"code":"security_definer","scope_keys":["supabase/migrations/x.sql"]}]
        out=queue.complete(item("security"),status="failed",findings=findings,evidence={"candidate_commit":"abc"})
        self.assertEqual(out["run_status"],"repair_pending")
        self.assertTrue(out["repair"]["created"])
        queue._rpc.assert_called_once()
        name,payload=queue._rpc.call_args.args
        self.assertEqual(name,"factory_complete_specialist_lane_with_trace")
        self.assertEqual(payload["p_findings"],findings)
        self.assertNotEqual(payload["p_evidence"]["_factory_claim_token"],None)

    def test_operations_never_attempts_auto_repair(self):
        queue=SupabaseSpecialistLaneQueue.__new__(SupabaseSpecialistLaneQueue)
        queue._rpc=MagicMock(return_value={
            "job_id":"job","status":"failed","run_status":"specialist_review_failed",
            "post_review_applied":True,
            "traceability_recorded":True,
            "traceability":{"requirements_linked":0,"dod_checks_linked":0},"repair":None,"repair_recheck":None,
        })
        out=queue.complete(item("operations"),status="failed",
                           findings=[{"code":"unknown_cost","severity":"error"}],evidence={})
        self.assertIsNone(out["repair"])
        queue._rpc.assert_called_once()

    def test_passed_security_commits_atomic_recheck(self):
        queue=SupabaseSpecialistLaneQueue.__new__(SupabaseSpecialistLaneQueue)
        queue._rpc=MagicMock(return_value={
            "job_id":"job","status":"passed","run_status":"preview_ready",
            "post_review_applied":True,
            "traceability_recorded":True,
            "traceability":{"requirements_linked":0,"dod_checks_linked":0},"repair":None,
            "repair_recheck":{"updated":1,"status":"passed","candidate_commit":"abc"},
        })
        out=queue.complete(item("security"),status="passed",findings=[],evidence={})
        self.assertEqual(out["repair_recheck"]["updated"],1)
        queue._rpc.assert_called_once()

    def test_old_half_committed_completion_is_not_silently_accepted(self):
        queue=SupabaseSpecialistLaneQueue.__new__(SupabaseSpecialistLaneQueue)
        queue._rpc=MagicMock(return_value={
            "job_id":"job","status":"failed","run_status":"specialist_review_failed"
        })
        with self.assertRaisesRegex(RuntimeError,"atomic post-review"):
            queue.complete(item("security"),status="failed",findings=[{"code":"missing"}],evidence={})
        queue._rpc.assert_called_once()


if __name__=="__main__":
    unittest.main()
