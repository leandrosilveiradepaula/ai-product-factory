"""Deterministic proof that specialist claims bind the candidate branch."""
import unittest
from unittest.mock import MagicMock,patch

from ai_product_factory.specialist_lane_queue import SupabaseSpecialistLaneQueue


class SpecialistClaimBranchBindingTests(unittest.TestCase):
    def claim(self,branch):
        queue=object.__new__(SupabaseSpecialistLaneQueue)
        queue._rpc=MagicMock(return_value={
            "job_id":"job-1","run_id":"run-1","project_key":"project",
            "repository":"owner/repo","role":"security",
            "candidate_commit":"a"*40,"execution_generation":2,
            "claim_token":"00000000-0000-4000-8000-000000000001",
            "manifest":{"preview":{"required":False,"reason":"backend"}},
        })
        received=[]
        def fake_get(query):
            received.append(query)
            if query.startswith("factory_tool_usage?"):
                return [{"metadata":{"pr":7,"head_sha":"a"*40}}]
            if query.startswith("factory_runs?"):
                return [{"task_id":"task-1","execution_route":"direct",
                         "branch_name":branch,"metadata":{"github_issue":{"number":4}}}]
            if query.startswith("factory_tasks?"):
                return [{"project_id":"project-id","acceptance_criteria":["works"]}]
            raise AssertionError(f"unexpected read: {query}")
        queue._get=fake_get
        with patch("ai_product_factory.specialist_lane_queue.run_followup_epoch",
                   return_value=(2,True)),patch(
                   "ai_product_factory.specialist_lane_queue.validate_create_pr_candidate"):
            result=queue.claim("security","worker")
        return result,received

    def test_branch_is_bound_to_durable_run_and_not_inferred_from_pr(self):
        item,reads=self.claim("factory/integration-a")
        self.assertEqual(item.branch,"factory/integration-a")
        self.assertEqual(item.repository,"owner/repo")
        self.assertTrue(any("branch_name" in query for query in reads))

    def test_missing_or_unsafe_branch_is_rejected_before_review(self):
        for branch in (None,"","main","master","/absolute","../escape",
                       "factory//ambiguous","factory/has space","factory\\unsafe"):
            with self.subTest(branch=branch):
                with self.assertRaisesRegex(RuntimeError,"verified nonproduction branch"):
                    self.claim(branch)


if __name__=="__main__":
    unittest.main()
