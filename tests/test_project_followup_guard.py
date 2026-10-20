"""Executable operator-state fences across all non-model external followups."""
import json
import unittest
import urllib.error
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock,patch

from ai_product_factory.project_followup_guard import (
    SupabaseProjectFollowupGuard, ProjectFollowupPaused,
)
from ai_product_factory.runtime_cli import (
    _next_authorized_preview, run_ci_once, run_preview_once,
    run_preview_probe_once, run_release_once, run_specialist_once,
)
from ai_product_factory.bounded_continuation import drain_waiting_followups

PID="123e4567-e89b-42d3-a456-426614174000"

class Response:
    def __init__(self,row):self.row=row
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self):return json.dumps(self.row).encode()

class ProjectFollowupGuardTests(unittest.TestCase):
    def checkpoint(self, state="running", generation=1, *, active=True, project_id=PID):
        values=[
            Response([{"id":project_id,"is_active":active}]),
            Response([{"project_id":project_id,"state":state,"generation":generation}]),
            Response(None),
        ]
        cfg={"url":"https://x.supabase.co","secret_key":"sb_secret_test"}
        guard=SupabaseProjectFollowupGuard(**cfg)
        with patch("urllib.request.urlopen",side_effect=values) as call:
            try:
                result=guard.assert_running("crm-infodive")
            except Exception as exc:
                return exc,call.call_args_list
        return result,call.call_args_list

    def test_running_projects_use_exact_project_id_and_server_side_rpc(self):
        result,requests=self.checkpoint()
        self.assertEqual(result,1)
        self.assertEqual(len(requests),3)
        self.assertIn("project_key=eq.crm-infodive",requests[0].args[0].full_url)
        self.assertIn("project_id=eq."+PID,requests[1].args[0].full_url)
        self.assertTrue(requests[2].args[0].full_url.endswith("rpc/factory_assert_project_running"))
        self.assertEqual(requests[2].args[0].method,"POST")
        self.assertIn(PID,requests[2].args[0].data.decode())

    def test_known_disallowed_states_are_waiting_without_rpc(self):
        for state in ("draft","pausing","paused","stopping","stopped"):
            with self.subTest(state=state):
                value,calls=self.checkpoint(state)
                self.assertIsInstance(value,ProjectFollowupPaused)
                self.assertEqual(len(calls),2)
        value,calls=self.checkpoint(active=False)
        self.assertIsInstance(value,ProjectFollowupPaused)
        self.assertEqual(len(calls),1)

    def test_unknown_generation_and_identity_never_authorize_rpc(self):
        for generation in (0,-1,None,True,"1"):
            value,calls=self.checkpoint(generation=generation)
            self.assertIsInstance(value,ProjectFollowupPaused)
            self.assertEqual(len(calls),2)
        for state in ("other","RUNNING",None):
            value,calls=self.checkpoint(state)
            self.assertIsInstance(value,RuntimeError)
            self.assertEqual(len(calls),2)
        for pid in ("bad",""):
            value,calls=self.checkpoint(project_id=pid)
            self.assertIsInstance(value,RuntimeError)
            self.assertEqual(len(calls),1)

    def test_invalid_project_key_never_reaches_network(self):
        guard=SupabaseProjectFollowupGuard(url="https://x.supabase.co",secret_key="sb_secret_test")
        for value in ("", "Company/Prod","../foo","foo?query=1",None,1):
            with self.subTest(value=value),patch("urllib.request.urlopen") as net:
                with self.assertRaises(RuntimeError):guard.assert_running(value)
                net.assert_not_called()

    def test_denied_or_unreachable_checkpoint_fails_without_leaking_payload(self):
        guard=SupabaseProjectFollowupGuard(url="https://x.supabase.co",secret_key="sb_secret_test")
        denied=urllib.error.HTTPError("https://x.supabase.co/private",403,"secret error",{},None)
        with patch("urllib.request.urlopen",side_effect=denied):
            with self.assertRaisesRegex(RuntimeError,"checkpoint unavailable") as err:
                guard.assert_running("crm-infodive")
        self.assertNotIn("sb_secret_test",str(err.exception))
        with patch("urllib.request.urlopen",side_effect=urllib.error.URLError("credential leaked")):
            with self.assertRaisesRegex(RuntimeError,"checkpoint unavailable") as err:
                guard.assert_running("crm-infodive")
        self.assertNotIn("credential leaked",str(err.exception))

    def test_race_pause_during_rpc_returns_waiting_not_runner_error(self):
        guard=SupabaseProjectFollowupGuard(url="https://x.supabase.co",secret_key="sb_secret_test")
        raced=urllib.error.HTTPError("https://x.supabase.co/rest/v1/rpc/factory_assert_project_running",
                                     409,"PT409 operator paused",{},None)
        with patch("urllib.request.urlopen",side_effect=[
            Response([{"id":PID,"is_active":True}]),
            Response([{"project_id":PID,"state":"running","generation":1}]),
            raced,
        ]) as calls:
            with self.assertRaises(ProjectFollowupPaused):
                guard.assert_running("crm-infodive")
        self.assertEqual(calls.call_count,3)

    def test_project_control_mismatch_is_fail_closed(self):
        guard=SupabaseProjectFollowupGuard(url="https://x.supabase.co",secret_key="sb_secret_test")
        with patch("urllib.request.urlopen",side_effect=[
            Response([{"id":PID,"is_active":True}]),
            Response([{"project_id":str(uuid.uuid4()),"state":"running","generation":5}]),
        ]) as call:
            with self.assertRaisesRegex(RuntimeError,"identity mismatch"):
                guard.assert_running("crm-infodive")
        self.assertEqual(call.call_count,2)

class FollowupPauseIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.item=SimpleNamespace(
            run_id="run-1",job_id="lane-1",project_id=PID,project_key="crm-infodive",
            repository="owner/repo",pr_number=25,candidate_commit="a"*40,
        )

    def test_ci_preview_and_release_do_not_use_github_when_paused(self):
        functions=(
            ("ci",run_ci_once,"SupabaseCIFollowupQueue"),
            ("preview",run_preview_once,"SupabasePreviewFollowupQueue"),
            ("preview_probe",run_preview_probe_once,"SupabasePreviewFollowupQueue"),
            ("release",run_release_once,"SupabaseReleaseFollowupQueue"),
        )
        for label,runner,queue_type in functions:
            with self.subTest(label=label), \
                 patch("ai_product_factory.runtime_cli."+queue_type) as queue, \
                 patch("ai_product_factory.runtime_cli.SupabaseProjectFollowupGuard",autospec=True) as gate, \
                 patch("ai_product_factory.runtime_cli.GitHubRestAdapter") as github, \
                 patch("ai_product_factory.runtime_cli.SupabaseDeliveryStore") as store:
                queue.return_value.next_pending.side_effect=[self.item,None] if label.startswith("preview") else None
                if not label.startswith("preview"):queue.return_value.next_pending.return_value=self.item
                gate.return_value.assert_running.side_effect=ProjectFollowupPaused("project_control_waiting")
                out=runner()
                self.assertEqual(out["status"],"project_control_waiting")
                self.assertEqual(out["run_id"],"run-1")
                github.assert_not_called()
                store.assert_not_called()

    def test_specialist_pause_after_claim_does_not_persist_evaluation(self):
        with patch("ai_product_factory.runtime_cli.SupabaseSpecialistLaneQueue") as queue, \
             patch("ai_product_factory.runtime_cli.SupabaseProjectFollowupGuard",autospec=True) as gate, \
             patch("ai_product_factory.runtime_cli.GitHubRestAdapter") as github, \
             patch("ai_product_factory.runtime_cli.SupabaseTraceabilityStore") as trace:
            queue.return_value.claim.return_value=self.item
            gate.return_value.assert_running.side_effect=ProjectFollowupPaused("project_control_waiting")
            out=run_specialist_once("qa","worker")
            self.assertEqual(out["status"],"project_control_waiting")
            queue.return_value.complete.assert_not_called()
            github.assert_not_called()
            trace.assert_not_called()

    def test_preview_lookahead_skips_paused_project_without_masquerading_as_empty(self):
        older=SimpleNamespace(**{**vars(self.item),"run_id":"old","project_key":"stopped-project"})
        newer=SimpleNamespace(**{**vars(self.item),"run_id":"new","project_key":"active-project"})
        queue=MagicMock()
        queue.next_pending.side_effect=[older,newer]
        with patch("ai_product_factory.runtime_cli.SupabaseProjectFollowupGuard",autospec=True) as gate:
            gate.return_value.assert_running.side_effect=[
                ProjectFollowupPaused("project_control_waiting"),3,
            ]
            item,wait=_next_authorized_preview(queue)
        self.assertIsNone(wait)
        self.assertEqual(item.run_id,"new")
        self.assertEqual(queue.next_pending.call_count,2)
        queue.next_pending.assert_any_call(exclude_run_ids=("old",))

    def test_ci_fair_continuation_observes_paused_then_processes_other_run(self):
        items=iter((
            {"claimed":True,"status":"project_control_waiting","run_id":"paused"},
            {"claimed":True,"status":"specialist_review_pending","run_id":"running"},
            {"claimed":False,"status":"empty"},
        ))
        results=drain_waiting_followups(lambda ignored:next(items),max_items=2)
        self.assertEqual(results["observed_waiting"],1)
        self.assertEqual(results["processed"],1)
        self.assertEqual(results["waiting"],[{"id":"paused","status":"project_control_waiting"}])
        self.assertEqual(results["items"],[{"id":"running","status":"specialist_review_pending"}])

if __name__=="__main__":
    unittest.main()
