import copy
import unittest
from unittest.mock import MagicMock
from ai_product_factory.planning_replay_guard import find_same_source_empty_planning
from ai_product_factory.runtime_worker import WorkItem
from ai_product_factory.supabase_runtime_queue import SupabaseRuntimeQueue

SHA="a"*40
NEW_SHA="b"*40
RUN="11111111-1111-4111-8111-111111111111"
TASK="22222222-2222-4222-8222-222222222222"
ORIGIN={"source_run_id":"33333333-3333-4333-8333-333333333333",
        "snapshot_id":"44444444-4444-4444-8444-444444444444",
        "request_id":"req-original","generation":6}
REQUEST={"id":"req-original","source":"github-owner","summary":"current approved request"}
TYPED={"reason_code":"planning_non_actionable","observed_model_response":True,
       "tasks_count":0,"decisions_count":0,"implementation_completed":False,
       "requires_scope_reconciliation":True,"assessed_commit":SHA}

def prior():
    return {"id":"55555555-5555-4555-8555-555555555555","task_id":TASK,"status":"failed",
        "metadata":{
            "execution_generation":6,"continuation_request_id":"req-original",
            "continuation_request":copy.deepcopy(REQUEST),
            "error":"planning has no actionable tasks or decisions",
            "resume_checkpoint":{"schema":"checkpointed_product_planning_v1",
                "source_run_id":ORIGIN["source_run_id"],
                "snapshot_id":ORIGIN["snapshot_id"],
                "request_id":ORIGIN["request_id"],"source_generation":6},
            "stage_evidence":{"planning":{"status":"failed","output":copy.deepcopy(TYPED)}}}}

def assess(rows, *, sha=SHA, request=REQUEST, origin=ORIGIN):
    return find_same_source_empty_planning(
        rows,current_run_id=RUN,task_id=TASK,origin=origin,
        current_commit=sha,current_request=request)

class ReplayTests(unittest.TestCase):
    def test_exact_prior_empty_receipt_blocks_paid_replay(self):
        self.assertTrue(assess([prior()]))

    def test_changed_sha_request_snapshot_epoch_all_allow_new_work(self):
        self.assertFalse(assess([prior()],sha=NEW_SHA))
        self.assertFalse(assess([prior()],request={**REQUEST,"summary":"new scope"}))
        self.assertFalse(assess([prior()],origin={**ORIGIN,"snapshot_id":"another"}))
        self.assertFalse(assess([prior()],origin={**ORIGIN,"generation":7}))

    def test_historical_empty_without_full_receipt_cannot_prove_no_work(self):
        for key in ("stage_evidence","resume_checkpoint","error","continuation_request"):
            row=prior()
            row["metadata"].pop(key)
            with self.subTest(key=key): self.assertFalse(assess([row]))
        row=prior();row["metadata"]["stage_evidence"]["planning"]["output"]["observed_model_response"]="true"
        self.assertFalse(assess([row]))
        row=prior();row["metadata"]["stage_evidence"]["planning"]["output"]["assessed_commit"]=NEW_SHA
        self.assertFalse(assess([row]))

    def test_malformed_rows_and_unbounded_scan_fail_closed(self):
        with self.assertRaisesRegex(RuntimeError,"malformed"):
            assess([{"id":"x","task_id":"other","status":"failed","metadata":{}}])
        with self.assertRaises(ValueError): assess([prior()]*41)
        with self.assertRaises(ValueError): assess([prior()],sha="not-a-sha")

    def test_claim_rejected_before_paid_model_using_fixed_reason(self):
        queue=object.__new__(SupabaseRuntimeQueue)
        context={"_verified_resume_prior_stages":{"reconciliation":{},"gap_analysis":{}},
            "_verified_resume_origin":ORIGIN,
            "current_state_facts":{"live_candidate":{"sha":SHA}},
            "manifest":{"continuation_request":REQUEST}}
        queue._rpc=MagicMock(side_effect=lambda name,payload:
            {"run_id":RUN,"task_id":TASK,"project_id":"p","project_key":"crm-infodive",
             "stages":["planning"],"context":{},"execution_generation":6}
            if name=="factory_claim_next_run" else None)
        queue._planning_resume_context=MagicMock(return_value=context)
        queue._live_candidate_context=MagicMock(return_value=context)
        queue._get=MagicMock(return_value=[prior()])
        queue.fail=MagicMock()
        with self.assertRaisesRegex(PermissionError,"planning resume provenance invalid"):
            queue.claim_next("w1")
        queue.fail.assert_called_once()
        self.assertEqual(queue.fail.call_args.args[1],
                         "planning_resume_no_current_eligible_work_same_sha")
        queue._get.assert_called_once()

    def test_source_move_does_not_block_claim(self):
        queue=object.__new__(SupabaseRuntimeQueue)
        context={"_verified_resume_prior_stages":{"reconciliation":{},"gap_analysis":{}},
            "_verified_resume_origin":ORIGIN,
            "current_state_facts":{"live_candidate":{"sha":NEW_SHA}},
            "manifest":{"continuation_request":REQUEST}}
        queue._rpc=lambda name,payload: {
            "run_id":RUN,"task_id":TASK,"project_id":"p","project_key":"crm-infodive",
            "stages":["planning"],"context":{},"execution_generation":6
        } if name=="factory_claim_next_run" else None
        queue._planning_resume_context=lambda *args:context
        queue._live_candidate_context=lambda *args:context
        queue._get=lambda path:[prior()]
        item=queue.claim_next("w1")
        self.assertEqual(item.run_id,RUN)

    def test_nonactionable_receipt_has_only_typed_fields_plus_verified_sha(self):
        q=object.__new__(SupabaseRuntimeQueue)
        q._rpc=MagicMock()
        q.assert_execution_epoch=MagicMock()
        item=WorkItem(RUN,TASK,"p","crm-infodive",("planning",),
           {"current_state_facts":{"live_candidate":{"sha":SHA}}})
        q.record_non_actionable_planning(item)
        output=q._rpc.call_args.args[1]["p_output"]
        self.assertEqual(output["assessed_commit"],SHA)
        self.assertEqual(output["reason_code"],"planning_non_actionable")
        unverified=WorkItem(RUN,TASK,"p","crm-infodive",("planning",),
            {"current_state_facts":{"live_candidate":{"sha":"floating"}}})
        q.record_non_actionable_planning(unverified)
        self.assertNotIn("assessed_commit",q._rpc.call_args.args[1]["p_output"])

if __name__=="__main__": unittest.main()
