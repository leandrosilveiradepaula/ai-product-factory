"""Deterministic negative contracts for release-blocked SHA recovery; no network."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from types import SimpleNamespace
import unittest

from ai_product_factory.blocked_release_candidate import (
    BlockedCandidateRecoveryDenied, exact_sha_ci_state,
    reconcile_blocked_release_candidate,
)
from ai_product_factory.github_loop import CIState

PREV="a"*40
NEXT="b"*40
RUN="11111111-1111-1111-1111-111111111111"
CS="22222222-2222-2222-2222-222222222222"
TASK="33333333-3333-3333-3333-333333333333"
PROJECT="44444444-4444-4444-4444-444444444444"
REPO="org/project"
BRANCH="factory/change-set-22222222"


class GitHub:
    def __init__(self):
        self.pr=SimpleNamespace(
            number=2,state="open",merged=False,draft=False,head_sha=NEXT,
            head_ref=BRANCH,head_repository=REPO,base_ref="main",
        )
        self.comparison={"status":"ahead","behind_by":0,"ahead_by":4,
                         "files":["README.md","src/domain/example.ts"]}
        self.branch=NEXT
        self.pr_calls=0

    def get_pull_request(self,pr):
        assert pr==2
        self.pr_calls+=1
        return deepcopy(self.pr)

    def compare_commits(self,a,b):
        assert a==PREV and b==NEXT
        return deepcopy(self.comparison)

    def get_branch_sha(self,branch):
        assert branch==BRANCH
        return self.branch


class Store:
    def __init__(self):
        self.calls=[]
        self.receipt={
            "status":"ci_pending","run_id":RUN,"previous_commit":PREV,
            "candidate_commit":NEXT,"release_authorized":False,
            "old_evidence_preserved":True,
            "new_specialist_approval_required":True,
        }

    def _rpc(self,name,payload):
        self.calls.append((name,deepcopy(payload)))
        return deepcopy(self.receipt)


class Fixture:
    def __init__(self):
        self.gh=GitHub()
        self.store=Store()
        self.ci={"source":"github_actions_checks",
                 "workflows":1,"completed_native_checks":2}
        self.rows={
            "factory_runs":[{
                "id":RUN,"task_id":TASK,"status":"release_policy_blocked",
                "branch_name":BRANCH,"candidate_commit":PREV,
                "metadata":{"source":"change-set","change_set_id":CS,
                            "execution_generation":1},
                "lease_owner":None,"lease_expires_at":None,
            }],
            "factory_change_sets":[{
                "id":CS,"project_id":PROJECT,"root_task_id":TASK,
                "release_run_id":RUN,"status":"ci_pending","branch_name":BRANCH,
                "candidate_commit":PREV,"metadata":{
                    "integration_release_request":{"pr_number":2,
                        "candidate_commit":PREV,"branch":BRANCH},
                    "integration_epoch_receipt":{"candidate_commit":PREV,
                        "project_id":PROJECT,"generation":1}},
                "lease_owner":None,"lease_expires_at":None,
            }],
            "factory_projects":[{
                "id":PROJECT,"project_kind":"greenfield",
                "repository":REPO,"is_active":True,
            }],
            "factory_release_reports":[{
                "run_id":RUN,"project_id":PROJECT,"status":"blocked",
                "candidate_commit":PREV,
                "report":{"release_state":"blocked",
                    "definition_of_done":{"missing":[
                        {"key":"migration_validation","human_only":False},
                        {"key":"rollback_analysis","human_only":False},
                        {"key":"human_release","human_only":True}
                    ]}},
            }],
        }

    def read(self,path):
        return deepcopy(self.rows[path.split("?",1)[0]])

    def run(self):
        return reconcile_blocked_release_candidate(
            run_id=RUN,pr_number=2,read=self.read,
            github_factory=lambda repository:self.gh,
            store=self.store,
            ci_verifier=lambda github,sha:self.ci,
        )


class ReconciliationTests(unittest.TestCase):
    def test_original_blocked_release_requeues_only_ci_on_exact_sha(self):
        f=Fixture()
        result=f.run()
        self.assertEqual(result["status"],"ci_pending")
        self.assertEqual(result["candidate_commit"],NEXT)
        self.assertFalse(result["release_authorized"])
        self.assertTrue(result["old_evidence_preserved"])
        self.assertTrue(result["new_specialist_approval_required"])
        self.assertEqual(f.gh.pr_calls,2)
        self.assertEqual(len(f.store.calls),1)
        name,args=f.store.calls[0]
        self.assertEqual(name,"factory_reconcile_policy_blocked_candidate_v1")
        self.assertEqual(args["p_previous_commit"],PREV)
        self.assertEqual(args["p_new_commit"],NEXT)
        self.assertEqual(args["p_verified_evidence"]["compare_status"],"ahead")
        self.assertTrue(args["p_verified_evidence"]["target_pr_ci_still_required"])
        self.assertNotIn("secret",str(args).lower())

    def test_only_explicit_run_and_pr_are_allowed(self):
        for run,pr in [("",2),("not-a-uuid",2),(RUN,0),(RUN,-1),(RUN,True),(RUN,"2")]:
            with self.subTest(run=run,pr=pr):
                f=Fixture()
                with self.assertRaises(BlockedCandidateRecoveryDenied):
                    reconcile_blocked_release_candidate(
                        run_id=run,pr_number=pr,read=f.read,
                        github_factory=lambda repository:f.gh,store=f.store,
                        ci_verifier=lambda gh,sha:f.ci)
                self.assertEqual(f.store.calls,[])

    def test_gate_status_and_exact_identity_must_match(self):
        changes=[
            ("factory_runs",lambda r:r.update(status="awaiting_release")),
            ("factory_runs",lambda r:r.update(status="ci_pending")),
            ("factory_runs",lambda r:r.update(lease_owner="worker")),
            ("factory_runs",lambda r:r["metadata"].update(source="demo")),
            ("factory_runs",lambda r:r["metadata"].update(change_set_id=PROJECT)),
            ("factory_runs",lambda r:r.update(candidate_commit=NEXT)),
            ("factory_change_sets",lambda r:r.update(status="completed")),
            ("factory_change_sets",lambda r:r.update(status="building")),
            ("factory_change_sets",lambda r:r.update(lease_expires_at="2026-11-16")),
            ("factory_change_sets",lambda r:r.update(candidate_commit=NEXT)),
            ("factory_change_sets",lambda r:r.update(release_run_id=PROJECT)),
            ("factory_change_sets",lambda r:r["metadata"]["integration_release_request"].update(pr_number=3)),
            ("factory_projects",lambda r:r.update(is_active=False)),
            ("factory_projects",lambda r:r.update(repository="attacker/project")),
            ("factory_release_reports",lambda r:r.update(status="released")),
            ("factory_release_reports",lambda r:r.update(candidate_commit=NEXT)),
            ("factory_release_reports",lambda r:r["report"].update(release_state="ready_for_human_release")),
            ("factory_release_reports",lambda r:r["report"]["definition_of_done"].update(missing=[
                {"key":"human_release","human_only":True}])),
        ]
        for table,change in changes:
            with self.subTest(table=table,change=change):
                f=Fixture();change(f.rows[table][0])
                with self.assertRaises(BlockedCandidateRecoveryDenied):
                    f.run()
                self.assertEqual(f.store.calls,[])

    def test_git_pr_ancestry_and_ci_attestation_are_fail_closed(self):
        mutations=[
            lambda f:setattr(f.gh.pr,"merged",True),
            lambda f:setattr(f.gh.pr,"draft",True),
            lambda f:setattr(f.gh.pr,"state","closed"),
            lambda f:setattr(f.gh.pr,"base_ref","preview/integration"),
            lambda f:setattr(f.gh.pr,"head_ref","main"),
            lambda f:setattr(f.gh.pr,"head_repository","attacker/repo"),
            lambda f:setattr(f.gh.pr,"head_sha",PREV),
            lambda f:setattr(f.gh,"branch",PREV),
            lambda f:f.gh.comparison.update(status="diverged"),
            lambda f:f.gh.comparison.update(behind_by=1),
            lambda f:f.gh.comparison.update(ahead_by=0),
            lambda f:f.gh.comparison.update(ahead_by=101),
            lambda f:f.gh.comparison.update(files=[]),
            lambda f:f.gh.comparison.update(files=["../secrets"]),
            lambda f:f.gh.comparison.update(files=["a"]*301),
            lambda f:f.ci.update(source="external_preview_status"),
            lambda f:f.ci.update(workflows=0),
            lambda f:f.ci.update(completed_native_checks=0),
        ]
        for change in mutations:
            with self.subTest(change=change):
                f=Fixture();change(f)
                with self.assertRaises(BlockedCandidateRecoveryDenied):
                    f.run()
                self.assertEqual(f.store.calls,[])

    def test_toctou_branch_move_before_privileged_write_is_blocked(self):
        f=Fixture()
        original=f.gh.get_pull_request
        def move(pr):
            row=original(pr)
            if f.gh.pr_calls==2:row.head_sha=PREV
            return row
        f.gh.get_pull_request=move
        with self.assertRaises(BlockedCandidateRecoveryDenied):
            f.run()
        self.assertEqual(f.store.calls,[])

    def test_no_fake_success_when_rpc_returns_inconsistent_receipt(self):
        f=Fixture()
        for changes in [{"status":"released"},{"release_authorized":True},
                        {"candidate_commit":PREV},{"new_specialist_approval_required":False},
                        {"old_evidence_preserved":False}]:
            f.store.calls=[]
            f.store.receipt={"status":"ci_pending","run_id":RUN,
                             "previous_commit":PREV,"candidate_commit":NEXT,
                             "release_authorized":False,"old_evidence_preserved":True,
                             "new_specialist_approval_required":True,**changes}
            with self.subTest(changes=changes):
                with self.assertRaises(BlockedCandidateRecoveryDenied):
                    f.run()

class CommitCITests(unittest.TestCase):
    def test_exact_sha_native_actions_suites_are_required(self):
        class GH:
            last_ci_workflow_runs=[{"status":"completed","conclusion":"success","check_suite_id":4}]
            def _check_runs_or_fine_grained_evidence(self,sha,branch):
                assert sha==NEXT and branch is None
                return "github_checks",[{"head_sha":NEXT,"status":"completed",
                   "conclusion":"success","check_suite":{"id":4}}],[]
            def _ci_state_from_fine_grained_evidence(self,rows,statuses):
                return CIState.SUCCESS
        result=exact_sha_ci_state(GH(),NEXT)
        self.assertEqual(result["completed_native_checks"],1)

    def test_pending_suite_and_failed_check_cannot_be_persisted(self):
        class GH:
            last_ci_workflow_runs=[{"status":"completed","conclusion":"success","check_suite_id":4}]
            failed=False
            def _check_runs_or_fine_grained_evidence(self,sha,branch):
                return "github_checks",[{"head_sha":NEXT,"status":"completed",
                   "conclusion":"failure" if self.failed else "success",
                   "check_suite":{"id":5}}],[]
            def _ci_state_from_fine_grained_evidence(self,rows,statuses):
                return CIState.SUCCESS
        g=GH()
        with self.assertRaises(BlockedCandidateRecoveryDenied):
            exact_sha_ci_state(g,NEXT)
        g.failed=True
        with self.assertRaises(BlockedCandidateRecoveryDenied):
            exact_sha_ci_state(g,NEXT)


if __name__=="__main__":
    unittest.main()
