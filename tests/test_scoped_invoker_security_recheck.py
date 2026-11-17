"""Offline adversarial evidence for current-SHA invoker/RLS Security re-review."""
from __future__ import annotations
import copy
import unittest
from unittest import mock
from types import SimpleNamespace
from ai_product_factory.architecture_guardian import GuardianReport
from ai_product_factory.blocked_release_candidate import BlockedCandidateRecoveryDenied
from ai_product_factory.scoped_invoker_security_recheck import (
    requeue_verified_invoker_review,
)

RUN="11111111-1111-4111-8111-111111111111"
CS="22222222-2222-4222-8222-222222222222"
PROJECT="33333333-3333-4333-8333-333333333333"
TASK="44444444-4444-4444-8444-444444444444"
JOB="55555555-5555-4555-8555-555555555555"
SHA="a"*40
FACTORY_SHA="b"*40
REPO="fixture-owner/fixture-product"
BRANCH="factory/change-set-22222222"


def snapshot():
    return {
      "factory_runs":{"id":RUN,"task_id":TASK,"status":"specialist_review_failed",
        "candidate_commit":SHA,"branch_name":BRANCH,"lease_owner":None,
        "lease_expires_at":None,
        "metadata":{"source":"change-set","change_set_id":CS,"execution_generation":"1"}},
      "factory_change_sets":{"id":CS,"project_id":PROJECT,"root_task_id":TASK,
        "status":"blocked","release_run_id":None,"candidate_commit":SHA,
        "integration_branch":BRANCH,"lease_owner":None,"lease_expires_at":None,
        "metadata":{"integration_release_request":{"pr_number":17,
                 "candidate_commit":SHA,"branch":BRANCH}}},
      "factory_projects":{"id":PROJECT,"project_kind":"greenfield",
        "is_active":True,"repository":REPO},
      "factory_specialist_lane_jobs":[
          {"id":JOB,"role":"security","status":"failed","required":True,
           "candidate_commit":SHA,"lease_expires_at":None,
           "findings":[{"code":"permissive_public_grant","severity":"error",
             "kind":"database_security","source":"architecture_guardian_v1",
             "path":"supabase/migrations/strict_rpc.sql"}]},
          {"id":"66666666-6666-4666-8666-666666666666","role":"qa",
           "status":"passed","required":True,"candidate_commit":SHA},
          {"id":"77777777-7777-4777-8777-777777777777","role":"operations",
           "status":"passed","required":True,"candidate_commit":SHA},
      ],
    }


class TargetGitHub:
    def __init__(self):
        self.pr=SimpleNamespace(number=17,state="open",merged=False,draft=False,
            head_sha=SHA,head_ref=BRANCH,head_repository=REPO,base_ref="main")
        self.rows=({"filename":"supabase/migrations/strict_rpc.sql",
            "status":"added","patch":"+grant execute on function public.a(uuid) to authenticated;",
            "additions":1,"deletions":0},)
    def get_pull_request(self,number):return self.pr
    def get_pull_request_file_details(self,number):return self.rows
    def get_branch_sha(self,branch):return SHA


class FactoryGitHub:
    def __init__(self):self.sha=FACTORY_SHA;self.passed=True
    def get_branch_sha(self,branch):return self.sha
    def _call(self,method,path,query=None):
        return {"workflow_runs":[{"name":"validate","event":"push",
          "head_sha":self.sha,"status":"completed",
          "conclusion":"success" if self.passed else "failure"}]}


class Store:
    def __init__(self):self.calls=[]
    def _rpc(self,name,args):
        self.calls.append((name,args))
        return {"status":"specialist_review_pending","run_id":RUN,
          "candidate_commit":SHA,"security_job_id":JOB,
          "previous_failure_preserved":True,"release_authorized":False}


class CurrentShaInvokerRecheckTests(unittest.TestCase):
    def scenario(self,change=None,report=None):
        data=snapshot(); target=TargetGitHub(); factory=FactoryGitHub(); store=Store()
        if change:change(data,target,factory)
        def read(path):
            for table,value in data.items():
                if path.startswith(table+"?"):
                    return copy.deepcopy(value if isinstance(value,list) else [value])
            raise AssertionError("unexpected Control Plane read")
        verdict=report or GuardianReport((),{"scanner":"architecture_guardian_v1",
            "files_reviewed":1,"blocking_findings":0,"unreviewable_paths":[]})
        args={"run_id":RUN,"pr_number":17,"read":read,
            "github_factory":lambda repository:target,"factory_github":factory,
            "store":store,"scan":lambda rows:verdict,
            "ci_verifier":lambda gh,sha:{"source":"github_actions_checks",
                   "completed_native_checks":2,"workflows":1}}
        return store,args

    def test_real_review_is_queued_not_marked_passed(self):
        store,args=self.scenario()
        receipt=requeue_verified_invoker_review(**args)
        self.assertEqual(receipt["status"],"specialist_review_pending")
        self.assertFalse(receipt["release_authorized"])
        self.assertEqual(len(store.calls),1)
        name,payload=store.calls[0]
        self.assertEqual(name,"factory_requeue_verified_invoker_security_once_v1")
        self.assertEqual(payload["p_security_job_id"],JOB)
        proof=payload["p_verified_proof"]
        self.assertEqual(proof["blockers"],"0")
        self.assertEqual(proof["candidate_commit"],SHA)
        self.assertEqual(proof["native_ci_state"],"success")
        self.assertFalse(proof["release_authorized"])
        self.assertFalse(proof["model_called"])
        self.assertEqual(len(proof["diff_sha256"]),64)

    def test_actual_default_github_constructors_are_covered(self):
        # A preceding B4 runner failed only in the non-injected constructor.
        store,args=self.scenario()
        args.pop("github_factory")
        args.pop("factory_github")
        target=TargetGitHub()
        factory=FactoryGitHub()
        actual=[]
        def construct(*,repository):
            actual.append(repository)
            return factory if repository=="leandrosilveiradepaula/ai-product-factory" else target
        with mock.patch("ai_product_factory.scoped_invoker_security_recheck.GitHubRestAdapter",
                        side_effect=construct):
            result=requeue_verified_invoker_review(**args)
        self.assertEqual(result["status"],"specialist_review_pending")
        self.assertEqual(actual,["leandrosilveiradepaula/ai-product-factory",REPO])
        self.assertEqual(len(store.calls),1)

    def test_forged_or_drifted_origin_cannot_requeue(self):
        def unreviewable(d,g,f):g.rows=({"filename":"x.sql","patch":""},)
        cases=[
          lambda d,g,f:d["factory_runs"].update(status="preview_ready"),
          lambda d,g,f:d["factory_runs"].update(candidate_commit="f"*40),
          lambda d,g,f:d["factory_change_sets"].update(status="ci_pending"),
          lambda d,g,f:d["factory_change_sets"]["metadata"]["integration_release_request"].update(pr_number=19),
          lambda d,g,f:d["factory_projects"].update(project_kind="existing"),
          lambda d,g,f:d["factory_specialist_lane_jobs"][0].update(status="passed"),
          lambda d,g,f:d["factory_specialist_lane_jobs"][0]["findings"][0].update(code="supabase_secret"),
          lambda d,g,f:d["factory_specialist_lane_jobs"][0]["findings"][0].update(severity="critical"),
          lambda d,g,f:d["factory_specialist_lane_jobs"][1].update(status="failed"),
          lambda d,g,f:setattr(g.pr,"merged",True),
          lambda d,g,f:setattr(g.pr,"head_sha","e"*40),
          lambda d,g,f:setattr(g,"rows",()),
          unreviewable,
          lambda d,g,f:setattr(f,"passed",False),
          lambda d,g,f:setattr(f,"sha","bad"),
        ]
        for change in cases:
            with self.subTest(change=str(change)):
                store,args=self.scenario(change)
                with self.assertRaises(BlockedCandidateRecoveryDenied):
                    requeue_verified_invoker_review(**args)
                self.assertEqual(store.calls,[])

    def test_scanner_downgrade_cannot_promote_old_failed_review(self):
        for report in (
            GuardianReport(({"severity":"error","code":"permissive_public_grant"},),
                           {"scanner":"architecture_guardian_v1",
                            "files_reviewed":1,"blocking_findings":1,
                            "unreviewable_paths":[]}),
            GuardianReport((),{"scanner":"untrusted_guardian_v1",
                              "files_reviewed":1,"blocking_findings":0,
                              "unreviewable_paths":[]}),
            GuardianReport((),{"scanner":"architecture_guardian_v1",
                              "files_reviewed":1,"blocking_findings":0,
                              "unreviewable_paths":["x.sql"]}),
        ):
            store,args=self.scenario(report=report)
            with self.assertRaises(BlockedCandidateRecoveryDenied):
                requeue_verified_invoker_review(**args)
            self.assertEqual(store.calls,[])

    def test_protected_schema_fences_and_historical_failure(self):
        from pathlib import Path
        path=Path(__file__).resolve().parents[1]/"supabase/migrations/20261117154000_verified_invoker_security_recheck.sql"
        sql=path.read_text()
        self.assertIn("security invoker set search_path=''",sql)
        self.assertIn("to service_role",sql)
        self.assertIn("from public,anon,authenticated",sql)
        self.assertIn("specialist.auth_invoker_recheck.queued",sql)
        self.assertIn("original_findings",sql)
        self.assertNotIn("set status='passed'",sql)
        self.assertNotIn("set status='released'",sql)


if __name__=="__main__":
    unittest.main()
