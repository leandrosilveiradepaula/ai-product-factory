"""Prove stale routed epochs never initiate new deterministic external effects."""
import json
import unittest
import urllib.error
import uuid
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from ai_product_factory.followup_execution_epoch import run_followup_epoch
from ai_product_factory.project_followup_guard import (
    SupabaseProjectFollowupGuard, ProjectFollowupPaused, ProjectFollowupRevoked,
)
from ai_product_factory.ci_followup_queue import SupabaseCIFollowupQueue
from ai_product_factory.preview_followup_queue import SupabasePreviewFollowupQueue
from ai_product_factory.release_followup_queue import SupabaseReleaseFollowupQueue
from ai_product_factory.specialist_lane_queue import SupabaseSpecialistLaneQueue
from ai_product_factory.runtime_cli import _assert_project_followup, _next_authorized_preview, run_ci_once
from ai_product_factory.bounded_continuation import drain_waiting_followups

PID="123e4567-e89b-42d3-a456-426614174000"


class Response:
    def __init__(self, data):
        self.data=data
    def __enter__(self):
        return self
    def __exit__(self,*a):
        return False
    def read(self):
        return json.dumps(self.data).encode()


class DurableGenerationParsingTests(unittest.TestCase):
    def test_routed_claim_must_have_original_epoch(self):
        self.assertEqual(run_followup_epoch({"execution_route":"direct","metadata":{"execution_generation":7}}),(7,True))
        self.assertEqual(run_followup_epoch({"execution_route":"codex","metadata":{"execution_generation":2}}),(2,True))
        self.assertEqual(run_followup_epoch({"execution_route":"direct","metadata":{}}),(None,True))
        self.assertEqual(run_followup_epoch({"execution_route":"codex"}),(None,True))

    def test_legacy_nonrouted_work_uses_current_epoch_not_fabricated_receipt(self):
        self.assertEqual(run_followup_epoch({"metadata":{"source":"legacy"}}),(None,False))
        self.assertEqual(run_followup_epoch({"execution_route":None,"metadata":{"execution_generation":3}}),(3,True))

    def test_malformed_epoch_and_metadata_never_authorize(self):
        for value in (0,-1,True,"2",2.0,[],{},False):
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                run_followup_epoch({"execution_route":"direct","metadata":{"execution_generation":value}})
        for data in ({"execution_route":7},{"metadata":[]},None,[]):
            with self.subTest(data=data),self.assertRaises(RuntimeError):
                run_followup_epoch(data)


class CurrentEpochRpcTests(unittest.TestCase):
    def guard(self):
        return SupabaseProjectFollowupGuard(url="https://x.supabase.co",secret_key="sb_secret_dummy")
    def replies(self, *, generation=4, state="running", project_id=PID, active=True):
        return [Response([{"id":project_id,"is_active":active}]),
                Response([{"project_id":project_id,"state":state,"generation":generation}]),
                Response(None)]

    def test_exact_project_and_claim_generation_reach_privileged_epoch_rpc(self):
        with patch("urllib.request.urlopen",side_effect=self.replies()) as network:
            gen=self.guard().assert_running("crm-infodive",
                        expected_project_id=PID,expected_generation=4,require_generation=True)
        self.assertEqual(gen,4)
        self.assertEqual(network.call_count,3)
        rpc=network.call_args_list[2].args[0]
        self.assertTrue(rpc.full_url.endswith("rpc/factory_assert_project_execution_epoch"))
        self.assertEqual(rpc.method,"POST")
        self.assertEqual(json.loads(rpc.data),{"p_project_id":PID,"p_generation":4})

    def test_pause_resume_revokes_prior_claim_despite_current_running(self):
        with patch("urllib.request.urlopen",side_effect=self.replies(generation=5)) as network:
            with self.assertRaises(ProjectFollowupRevoked):
                self.guard().assert_running("crm-infodive",
                       expected_project_id=PID,expected_generation=4,require_generation=True)
        self.assertEqual(network.call_count,2)

    def test_claim_generation_missing_fails_before_network(self):
        with patch("urllib.request.urlopen") as network:
            with self.assertRaises(ProjectFollowupRevoked):
                self.guard().assert_running("crm-infodive",require_generation=True)
            network.assert_not_called()

    def test_false_project_id_never_uses_running_other_project(self):
        with patch("urllib.request.urlopen",side_effect=self.replies()) as network:
            with self.assertRaisesRegex(RuntimeError,"project identity mismatch"):
                self.guard().assert_running("crm-infodive",
                    expected_project_id=str(uuid.uuid4()),expected_generation=4)
        self.assertEqual(network.call_count,1)

    def test_legacy_nonrouted_still_pins_current_epoch_in_rpc(self):
        with patch("urllib.request.urlopen",side_effect=self.replies(generation=9)) as network:
            self.assertEqual(self.guard().assert_running("crm-infodive"),9)
        self.assertEqual(json.loads(network.call_args_list[2].args[0].data)["p_generation"],9)

    def test_pause_between_read_and_epoch_rpc_is_waiting_not_success(self):
        raced=urllib.error.HTTPError("https://x.supabase.co/rest/v1/rpc/factory_assert_project_execution_epoch",
                                      409,"revoked",{},{})
        with patch("urllib.request.urlopen",side_effect=self.replies()[:2]+[raced]) as network:
            with self.assertRaises(ProjectFollowupPaused):
                self.guard().assert_running("crm-infodive",expected_generation=4)
        self.assertEqual(network.call_count,3)

    def test_bad_expected_identity_and_epoch_are_denied_before_io(self):
        for kw in ({"expected_project_id":"not-a-uuid"},
                   {"expected_generation":0},
                   {"expected_generation":True},
                   {"require_generation":1}):
            with self.subTest(kw=kw),patch("urllib.request.urlopen") as network:
                with self.assertRaises(RuntimeError):self.guard().assert_running("crm-infodive",**kw)
                network.assert_not_called()


class DurableQueuePropagationTests(unittest.TestCase):
    def test_ci_queue_carries_project_id_and_original_generation(self):
        queue=SupabaseCIFollowupQueue(url="https://x.supabase.co",secret_key="sb_secret_dummy")
        rows=[
            [{"id":"r1","task_id":"t","execution_route":"direct","branch_name":"factory/t",
              "candidate_commit":"abc","metadata":{"execution_generation":5,"github_issue":{"number":7}}}],
            [{"project_id":PID}],
            [{"project_key":"crm-infodive","repository":"owner/repo"}],
            [{"metadata":{"pr":9,"head_sha":"abc"}}],
        ]
        with patch.object(queue,"_get",side_effect=rows):
            item=queue.next_pending()
        self.assertEqual((item.project_id,item.execution_generation,item.require_execution_generation),(PID,5,True))

    def test_legacy_missing_direct_receipt_is_flagged_not_assumed_current(self):
        queue=SupabaseCIFollowupQueue(url="https://x.supabase.co",secret_key="sb_secret_dummy")
        rows=[
            [{"id":"r1","task_id":"t","execution_route":"direct","branch_name":"factory/t",
              "candidate_commit":"abc","metadata":{"github_issue":{"number":7}}}],
            [{"project_id":PID}],
            [{"project_key":"crm-infodive","repository":"owner/repo"}],
            [{"metadata":{"pr":9,"head_sha":"abc"}}],
        ]
        with patch.object(queue,"_get",side_effect=rows):
            item=queue.next_pending()
        self.assertTrue(item.require_execution_generation)
        self.assertIsNone(item.execution_generation)

    def test_preview_queue_preserves_routed_epoch_behind_quality_gate(self):
        queue=SupabasePreviewFollowupQueue(url="https://x.supabase.co",secret_key="sb_secret_dummy")
        rows=[
            [{"id":"r2","task_id":"t","execution_route":"codex","branch_name":"factory/t",
              "candidate_commit":"abc","metadata":{"execution_generation":5,"github_issue":{"number":7}}}],
            [],[{"project_id":PID}],
            [{"project_key":"crm-infodive","repository":"owner/repo","manifest":{}}],
            [{"metadata":{"pr":9,"head_sha":"abc"}}],
            [{"status":"success","baseline_ref":"abc","result":{"passed":True}}],
        ]
        with patch.object(queue,"_get",side_effect=rows),patch("ai_product_factory.preview_followup_queue.validate_create_pr_candidate"):
            item=queue.next_pending()
        self.assertEqual((item.execution_generation,item.project_id),(5,PID))
        self.assertTrue(item.require_execution_generation)

    def test_release_metadata_kept_for_observation_without_reclaim(self):
        queue=SupabaseReleaseFollowupQueue(url="https://x.supabase.co",secret_key="sb_secret_dummy")
        rows=[
            [{"id":"r3","task_id":"t","execution_route":"direct","branch_name":"factory/t",
              "candidate_commit":"abc","metadata":{"execution_generation":5,"github_issue":{"number":7}}}],
            [{"project_id":PID,"risk":{}}],
            [{"project_key":"crm-infodive","repository":"owner/repo"}],
            [],
            [{"metadata":{"pr":9,"head_sha":"abc"}}],
        ]
        with patch.object(queue,"_get",side_effect=rows):
            item=queue.next_pending()
        self.assertEqual(item.execution_generation,5)
        self.assertTrue(item.require_execution_generation)

    def test_specialist_claim_is_bound_to_original_run_and_task_project(self):
        queue=SupabaseSpecialistLaneQueue(url="https://x.supabase.co",secret_key="sb_secret_dummy")
        response={"job_id":"job","run_id":"r4","project_key":"crm-infodive",
                  "repository":"owner/repo","candidate_commit":"abc","role":"qa","manifest":{}}
        rows=[
            [{"metadata":{"pr":9,"head_sha":"abc"}}],
            [{"task_id":"t","execution_route":"direct","metadata":{"execution_generation":5}}],
            [{"project_id":PID,"acceptance_criteria":["x"]}],
        ]
        with patch.object(queue,"_rpc",return_value=response),patch.object(queue,"_get",side_effect=rows),patch("ai_product_factory.specialist_lane_queue.validate_create_pr_candidate"):
            item=queue.claim("qa","worker")
        self.assertEqual(item.project_id,PID)
        self.assertEqual(item.execution_generation,5)
        self.assertTrue(item.require_execution_generation)


class RuntimeGenerationFenceTests(unittest.TestCase):
    def item(self):
        return SimpleNamespace(run_id="r1",job_id="j1",project_key="crm-infodive",
               project_id=PID,pr_number=9,repository="owner/repo",
               execution_generation=4,require_execution_generation=True)
    def test_effectful_worker_pins_original_epoch(self):
        with patch("ai_product_factory.runtime_cli.SupabaseProjectFollowupGuard",autospec=True) as guard:
            _assert_project_followup(self.item())
        guard.return_value.assert_running.assert_called_once_with(
            "crm-infodive",expected_project_id=PID,
            expected_generation=4,require_generation=True,
        )

    def test_human_merge_observation_revalidates_running_but_does_not_reclaim(self):
        with patch("ai_product_factory.runtime_cli.SupabaseProjectFollowupGuard",autospec=True) as guard:
            _assert_project_followup(self.item(),human_merge_observation=True)
        guard.return_value.assert_running.assert_called_once_with(
            "crm-infodive",expected_project_id=PID,
            expected_generation=None,require_generation=False,
        )

    def test_revoked_ci_item_never_reads_github_or_dispatches(self):
        with patch("ai_product_factory.runtime_cli.SupabaseCIFollowupQueue") as queue, \
             patch("ai_product_factory.runtime_cli.SupabaseProjectFollowupGuard",autospec=True) as guard, \
             patch("ai_product_factory.runtime_cli.GitHubRestAdapter") as github:
            queue.return_value.next_pending.return_value=self.item()
            guard.return_value.assert_running.side_effect=ProjectFollowupRevoked("project_execution_epoch_revoked")
            result=run_ci_once()
        self.assertEqual(result["status"],"project_execution_epoch_revoked")
        github.assert_not_called()

    def test_revoked_preview_is_skipped_for_unrelated_active_project(self):
        queue=MagicMock()
        first=self.item()
        second=SimpleNamespace(**{**vars(first),"run_id":"r2","project_key":"other"})
        queue.next_pending.side_effect=[first,second]
        with patch("ai_product_factory.runtime_cli._assert_project_followup",
                   side_effect=[ProjectFollowupRevoked("project_execution_epoch_revoked"),6]):
            item,waiting=_next_authorized_preview(queue)
        self.assertEqual(item.run_id,"r2")
        self.assertIsNone(waiting)
        queue.next_pending.assert_any_call(exclude_run_ids=("r1",))

    def test_revoked_only_candidate_is_waiting_not_finished(self):
        queue=MagicMock()
        queue.next_pending.side_effect=[self.item(),None]
        with patch("ai_product_factory.runtime_cli._assert_project_followup",
                   side_effect=ProjectFollowupRevoked("project_execution_epoch_revoked")):
            item,waiting=_next_authorized_preview(queue)
        self.assertIsNone(item)
        self.assertEqual(waiting["status"],"project_execution_epoch_revoked")
        result=drain_waiting_followups(lambda ignored:
            {"claimed":True,"status":"project_execution_epoch_revoked","run_id":"r1"}
            if not ignored else {"claimed":False,"status":"empty"},max_items=1)
        self.assertEqual(result["processed"],0)
        self.assertEqual(result["observed_waiting"],1)


if __name__=="__main__":
    unittest.main()
