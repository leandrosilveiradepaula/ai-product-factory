"""No weak witness may resume a failed Factory greenfield candidate."""
from __future__ import annotations
import copy
from types import SimpleNamespace
import unittest
from unittest import mock

from ai_product_factory.failed_preview_candidate import (
    reconcile_failed_preview_candidate,
    verify_browser_snapshot,
    BlockedCandidateRecoveryDenied,
)

OLD="41e26b1fbaa80d44ff0e43f4d019af8ce2226ea6"
NEW="9290634e647a381712b4b1b5bbd1ba0159969ff1"
FACTORY_SHA="b773d0869354ade2a37526057fb5db162566d5ed"
RUN="3e747d9d-2440-4e78-8db0-55461753954e"
CS="0bccb423-cacb-49fa-b238-c8baba27e372"
TASK="62fa220a-565e-4932-a05a-8c318add316d"
PROJECT="19f0f200-3777-46c6-969a-acf0d3426ff1"
REPO="leandrosilveiradepaula/dark-channel-studio"
BRANCH="factory/change-set-0bccb423"
URL="https://dark-channel-studio-git-facto-431794-leandros-projects-102e32ab.vercel.app"
BROWSER_RUN=44088733294
REQUEST="552a999f-eb5c-4009-996c-7ea0ec2c507b"
SNAPSHOT="2ebdda68-9daa-46b4-a194-8c742c4e9886"


def fixtures():
    return {
      "factory_runs":{"id":RUN,"task_id":TASK,"status":"failed","branch_name":BRANCH,
        "candidate_commit":OLD,"lease_owner":None,"lease_expires_at":None,
        "metadata":{"source":"change-set","change_set_id":CS,"execution_generation":"1"}},
      "factory_change_sets":{"id":CS,"project_id":PROJECT,"root_task_id":TASK,
        "release_run_id":RUN,"status":"ci_pending","branch_name":BRANCH,
        "candidate_commit":OLD,"lease_owner":None,"lease_expires_at":None,
        "metadata":{"integration_release_request":{"candidate_commit":OLD,
           "pr_number":2,"branch":BRANCH},
           "integration_epoch_receipt":{"candidate_commit":OLD,
           "project_id":PROJECT,"generation":1}}},
      "factory_projects":{"id":PROJECT,"project_kind":"greenfield",
        "repository":REPO,"is_active":True},
      "factory_tasks":{"id":TASK,"project_id":PROJECT,"status":"failed"},
      "factory_release_reports":{"run_id":RUN,"project_id":PROJECT,
        "status":"blocked","report":{"definition_of_done":{"missing":[
          {"key":"migration_validation","human_only":False},
          {"key":"human_release","human_only":True}]}}},
      "factory_evaluations":{"status":"failure","eval_type":"browser_e2e"},
      "factory_project_state_snapshots":{"id":SNAPSHOT,"project_id":PROJECT,
        "run_id":None,"observed_stage":"verification",
        "evidence":{"candidate_commit":NEW,"target_repository":REPO,
          "preview":{"url":URL,"status":"browser_verified","provider":"vercel",
                     "browser_verifier_run_id":BROWSER_RUN,
                     "verifier_factory_commit":FACTORY_SHA,"browser_request_id":REQUEST}},
        "source_status":{"github_target":"verified","vercel_preview":"resolved",
                         "browser_visual_validation":"success"}},
    }


class MockGithub:
    def __init__(self,target=True):
        self.target=target
        self.pr=SimpleNamespace(number=2,state="open",merged=False,draft=False,
            head_repository=REPO,head_ref=BRANCH,base_ref="main",head_sha=NEW)
        self.branch_sha=NEW
        self.comparison={"status":"ahead","behind_by":0,"ahead_by":4,
                         "files":["app/server.js","app/editorial.js"]}
        self.workflow={"id":BROWSER_RUN,"name":"Console evidence "+REQUEST,
            "event":"workflow_dispatch","head_sha":FACTORY_SHA,
            "head_branch":"main","status":"completed","conclusion":"success"}
        self.jobs={"total_count":1,"jobs":[{"name":"browser-evidence",
            "conclusion":"success","steps":[
              {"name":"Verify exact protected Preview","conclusion":"success"}]}]}
    def get_pull_request(self,number):return self.pr
    def get_branch_sha(self,branch):return self.branch_sha
    def compare_commits(self,old,new):return self.comparison
    def _call(self,method,path,query=None):
        return self.jobs if path.endswith("/jobs") else self.workflow


class MockStore:
    def __init__(self):self.calls=[]
    def _rpc(self,name,payload):
        self.calls.append((name,payload))
        return {"status":"ci_pending","run_id":RUN,
            "previous_commit":OLD,"candidate_commit":NEW,
            "release_authorized":False,"old_evidence_preserved":True}


class FailedPreviewCandidateTests(unittest.TestCase):
    def run_case(self,mutator=None,ci=None):
        data=fixtures()
        github=MockGithub()
        factory=MockGithub(False)
        store=MockStore()
        if mutator:mutator(data,github,factory)
        def read(path):
            for name,value in data.items():
                if path.startswith(name+"?"):
                    return [copy.deepcopy(value)]
            raise AssertionError("unexpected Control Plane read "+path)
        args={"run_id":RUN,"pr_number":2,"read":read,
              "github_factory":lambda repo:github,
              "factory_github":factory,"store":store,
              "ci_verifier":lambda gh,sha:ci or {
                  "source":"github_actions_checks","workflows":1,
                  "completed_native_checks":2}}
        return store,args

    def test_real_default_github_wiring_uses_both_repo_scoped_adapters(self):
        """Exercise production defaults instead of only injecting fake GitHub objects.

        The first protected owner workflow invocation reached this code and
        failed with NameError before validating the original run. Mock only
        network transport, not the factory function names or parameters.
        """
        store,args=self.run_case()
        args.pop("github_factory")
        args.pop("factory_github")
        repositories=[]
        def make_adapter(*,repository):
            repositories.append(repository)
            self.assertIn(repository,(REPO,"leandrosilveiradepaula/ai-product-factory"))
            return MockGithub(target=repository==REPO)
        with mock.patch(
            "ai_product_factory.failed_preview_candidate.GitHubRestAdapter",
            side_effect=make_adapter,
        ):
            result=reconcile_failed_preview_candidate(**args)
        self.assertEqual(result["status"],"ci_pending")
        self.assertEqual(repositories,[
            "leandrosilveiradepaula/ai-product-factory",REPO,
        ])
        self.assertEqual(len(store.calls),1)
        self.assertFalse(store.calls[0][1]["p_verified_evidence"]["release_authorized"])

    def test_exact_failed_preview_recovers_without_waiving_release(self):
        store,args=self.run_case()
        receipt=reconcile_failed_preview_candidate(**args)
        self.assertEqual(receipt["status"],"ci_pending")
        self.assertFalse(receipt["release_authorized"])
        self.assertEqual(store.calls[0][0],"factory_reconcile_failed_preview_candidate_v1")
        fields=store.calls[0][1]["p_verified_evidence"]
        self.assertEqual(fields["browser_snapshot_id"],SNAPSHOT)
        self.assertEqual(fields["old_sha"],OLD)
        self.assertEqual(fields["new_sha"],NEW)
        self.assertTrue(fields["new_specialist_approval_required"])
        self.assertTrue(fields["recheck_dod_required"])

    def test_fail_closed_on_source_and_target_drifts(self):
        cases=[
          lambda d,g,f:d["factory_runs"].update(status="preview_ready"),
          lambda d,g,f:d["factory_runs"]["metadata"].update(execution_generation="19"),
          lambda d,g,f:d["factory_change_sets"].update(candidate_commit="a"*40),
          lambda d,g,f:d["factory_release_reports"].update(status="released"),
          lambda d,g,f:d["factory_evaluations"].update(status="success"),
          lambda d,g,f:d["factory_projects"].update(project_kind="existing"),
          lambda d,g,f:d["factory_tasks"].update(status="queued"),
          lambda d,g,f:setattr(g.pr,"head_sha","f"*40),
          lambda d,g,f:setattr(g.pr,"draft",True),
          lambda d,g,f:g.comparison.update(behind_by=1),
          lambda d,g,f:g.comparison.update(files=["../secret"]),
          lambda d,g,f:g.comparison.update(files=["app/a","app/a"]),
          lambda d,g,f:d["factory_project_state_snapshots"]["evidence"].update(candidate_commit="a"*40),
          lambda d,g,f:d["factory_project_state_snapshots"]["source_status"].update(browser_visual_validation="failure"),
          lambda d,g,f:d["factory_project_state_snapshots"]["evidence"]["preview"].update(status="browser_failed"),
          lambda d,g,f:f.workflow.update(conclusion="failure"),
          lambda d,g,f:f.workflow.update(head_sha="f"*40),
          lambda d,g,f:f.jobs["jobs"][0]["steps"][0].update(conclusion="failure"),
        ]
        for mutate in cases:
            with self.subTest(mutator=str(mutate)):
                store,args=self.run_case(mutate)
                with self.assertRaises(BlockedCandidateRecoveryDenied):
                    reconcile_failed_preview_candidate(**args)
                self.assertEqual(store.calls,[])

    def test_incomplete_native_ci_blocks_recovery(self):
        for ci in [{"source":"github_actions_checks","workflows":1,"completed_native_checks":1},
                   {"source":"github_actions_statuses","workflows":1,"completed_native_checks":2}]:
            store,args=self.run_case(ci=ci)
            with self.assertRaises(BlockedCandidateRecoveryDenied):
                reconcile_failed_preview_candidate(**args)
            self.assertEqual(store.calls,[])

    def test_protected_procedure_not_public(self):
        from pathlib import Path
        path=Path(__file__).resolve().parents[1] / "supabase/migrations/20261117133000_failed_preview_candidate_recovery.sql"
        text=path.read_text()
        self.assertIn("security invoker set search_path=''",text)
        self.assertIn("to service_role",text)
        self.assertIn("from public,anon,authenticated",text)
        self.assertIn("old_evidence_preserved",text)
        self.assertIn("new_specialist_approval_required",text)
        self.assertIn("finished_at=null",text)
        self.assertIn("status=\'integrated\'",text)
        self.assertNotIn("status='merged'",text)
        self.assertNotIn("set status='released'",text)


if __name__=="__main__":
    unittest.main()
