"""Negative contracts for exact-SHA, owner-gated security repair settlement."""
import unittest
from copy import deepcopy
from types import SimpleNamespace

from ai_product_factory.blocked_release_candidate import BlockedCandidateRecoveryDenied
from ai_product_factory.verified_security_repair import settle_verified_security_repair

OLD="a"*40
NEW="b"*40
RUN="11111111-1111-1111-1111-111111111111"
CHANGE_SET="22222222-2222-2222-2222-222222222222"
PROJECT="33333333-3333-3333-3333-333333333333"
TASK="44444444-4444-4444-4444-444444444444"
REPAIR="55555555-5555-5555-5555-555555555555"
UNIT="66666666-6666-6666-6666-666666666666"
BLOCKED="77777777-7777-7777-7777-777777777777"
PATH="src/a.test.ts"
BRANCH="factory/change-set-22222222"
REPO="owner/studio"


class FakeGithub:
    def __init__(self):
        self.pr=SimpleNamespace(head_sha=NEW,state="open",merged=False,draft=False,
          number=2,base_ref="main",head_repository=REPO,head_ref=BRANCH)
        self.comparison={"status":"ahead","ahead_by":1,"behind_by":0,"files":[PATH]}
        self.branch=NEW
        self.calls=0
        self.file="const invalid='sb_'+'secret_unacceptable';"

    def get_pull_request(self,number):
        assert number==2
        self.calls+=1
        return deepcopy(self.pr)
    def get_branch_sha(self,branch):
        assert branch==BRANCH
        return self.branch
    def compare_commits(self,old,new):
        assert (old,new)==(OLD,NEW)
        return deepcopy(self.comparison)
    def get_file_text(self,path,ref):
        assert (path,ref)==(PATH,NEW)
        return self.file
    def get_pull_request_file_details(self,number):
        return [{"filename":PATH,"status":"modified",
                "patch":"+ const invalid='sb_'+'secret_unacceptable';"}]


class FakeStore:
    def __init__(self):
        self.calls=[]
    def _rpc(self,name,data):
        self.calls.append((name,deepcopy(data)))
        return {"status":"ci_pending","run_id":RUN,"repair_id":REPAIR,
                "candidate_commit":NEW,"release_authorized":False,
                "old_evidence_preserved":True,"new_specialist_review_required":True}


class Fixture:
    def __init__(self):
        self.github=FakeGithub()
        self.store=FakeStore()
        self.ci={"source":"github_actions_checks","workflows":1,"completed_native_checks":2}
        self.tables={
          "factory_runs":[{"id":RUN,"task_id":TASK,"status":"specialist_review_failed",
             "candidate_commit":OLD,"branch_name":BRANCH,
             "metadata":{"source":"change-set","change_set_id":CHANGE_SET},
             "lease_owner":None,"lease_expires_at":None}],
          "factory_change_sets":[{"id":CHANGE_SET,"project_id":PROJECT,
             "root_task_id":TASK,"release_run_id":None,"status":"blocked",
             "candidate_commit":OLD,"integration_branch":BRANCH,
             "current_wave":10,"lease_owner":None,"lease_expires_at":None,
             "metadata":{"blocker":{
                 "type":"implementation_preflight_error",
                 "reason":"PermissionError: editable repository context contains redacted secret: "+PATH,
                 "run_id":BLOCKED,"work_unit_id":UNIT},
               "integration_release_request":{"pr_number":2,
                 "candidate_commit":OLD,"branch":BRANCH}}}],
          "factory_projects":[{"id":PROJECT,"repository":REPO,
             "project_kind":"greenfield","is_active":True}],
          "factory_repair_jobs":[{"id":REPAIR,"source_run_id":RUN,
             "source_role":"security","status":"queued","change_set_id":CHANGE_SET,
             "project_id":PROJECT,"candidate_commit":OLD,"cycle":1,
             "work_unit_id":UNIT,"task_id":"88888888-8888-8888-8888-888888888888",
             "write_scopes":[PATH],"finding":{"path":PATH,"code":"supabase_secret",
               "kind":"secret_scan"}}],
          "factory_change_set_work_units":[{"id":UNIT,
             "task_id":"88888888-8888-8888-8888-888888888888",
             "run_id":BLOCKED,"status":"blocked","base_commit":OLD,
             "output_commit":None}],
        }
    def read(self,path):
        return deepcopy(self.tables[path.split("?",1)[0]])
    def run(self,run_id=RUN,pr_number=2):
        return settle_verified_security_repair(
            run_id=run_id,pr_number=pr_number,
            read=self.read,github_factory=lambda repo:self.github,
            store=self.store,ci_verifier=lambda gh,sha:self.ci)


class SettlementTests(unittest.TestCase):
    def test_exact_sha_repair_returns_ci_pending_without_release(self):
        f=Fixture()
        got=f.run()
        self.assertEqual(got["status"],"ci_pending")
        self.assertFalse(got["release_authorized"])
        self.assertEqual(f.github.calls,2)
        self.assertEqual(len(f.store.calls),1)
        name,data=f.store.calls[0]
        self.assertEqual(name,"factory_settle_verified_blocked_security_repair_v1")
        self.assertEqual(data["p_old_sha"],OLD)
        self.assertEqual(data["p_new_sha"],NEW)
        self.assertEqual(data["p_verified_evidence"]["changed_files"],[PATH])
        self.assertEqual(data["p_verified_evidence"]["security_secret_scan"],"clean")
        self.assertFalse(data["p_verified_evidence"]["release_authorized"])

    def test_bad_run_or_pr_is_denied_before_network(self):
        for run,pr in (("",2),("not-uuid",2),(RUN,0),(RUN,True),(RUN,"2")):
            with self.subTest(run=run,pr=pr):
                f=Fixture()
                with self.assertRaises(BlockedCandidateRecoveryDenied):
                    f.run(run,pr)
                self.assertEqual(f.store.calls,[])

    def test_control_plane_status_and_source_errors_are_denied(self):
        cases=[
          ("factory_runs",lambda r:r.update(status="awaiting_release")),
          ("factory_runs",lambda r:r.update(candidate_commit=NEW)),
          ("factory_runs",lambda r:r.update(lease_owner="worker")),
          ("factory_change_sets",lambda r:r.update(status="ci_pending")),
          ("factory_change_sets",lambda r:r.update(release_run_id=RUN)),
          ("factory_change_sets",lambda r:r.update(candidate_commit=NEW)),
          ("factory_change_sets",lambda r:r["metadata"]["blocker"].update(type="unrelated")),
          ("factory_projects",lambda r:r.update(project_kind="existing")),
          ("factory_projects",lambda r:r.update(is_active=False)),
          ("factory_repair_jobs",lambda r:r.update(status="passed")),
          ("factory_repair_jobs",lambda r:r.update(source_role="qa")),
          ("factory_repair_jobs",lambda r:r.update(write_scopes=["src/other.ts"])),
          ("factory_repair_jobs",lambda r:r["finding"].update(code="random")),
          ("factory_change_set_work_units",lambda r:r.update(status="integrated")),
        ]
        for table,change in cases:
            with self.subTest(table=table,change=change):
                f=Fixture();change(f.tables[table][0])
                with self.assertRaises(BlockedCandidateRecoveryDenied):
                    f.run()
                self.assertEqual(f.store.calls,[])

    def test_github_pr_and_exact_sha_checks_fail_closed(self):
        changes=[
          lambda f:setattr(f.github.pr,"merged",True),
          lambda f:setattr(f.github.pr,"draft",True),
          lambda f:setattr(f.github.pr,"base_ref","preview"),
          lambda f:setattr(f.github.pr,"head_repository","attacker/project"),
          lambda f:setattr(f.github.pr,"head_ref","main"),
          lambda f:setattr(f.github,"branch",OLD),
          lambda f:f.github.comparison.update(status="diverged"),
          lambda f:f.github.comparison.update(ahead_by=2),
          lambda f:f.github.comparison.update(files=["src/other.ts"]),
          lambda f:setattr(f.github,"file","sb_secret_"+"verylongrealisticsecretmaterialvalue000"),
          lambda f:f.ci.update(completed_native_checks=0),
          lambda f:f.ci.update(source="unchecked_url"),
        ]
        for change in changes:
            with self.subTest(change=change):
                f=Fixture();change(f)
                with self.assertRaises(BlockedCandidateRecoveryDenied):
                    f.run()
                self.assertEqual(f.store.calls,[])

    def test_pr_drift_during_review_is_denied(self):
        f=Fixture()
        original=f.github.get_pull_request
        def changed(number):
            pr=original(number)
            if f.github.calls>=2:
                pr.head_sha=OLD
            return pr
        f.github.get_pull_request=changed
        with self.assertRaises(BlockedCandidateRecoveryDenied):
            f.run()
        self.assertEqual(f.store.calls,[])

    def test_bad_rpc_receipt_is_never_reported_as_success(self):
        f=Fixture()
        f.store._rpc=lambda name,data:{
            "status":"released","run_id":RUN,"repair_id":REPAIR,
            "candidate_commit":NEW,"release_authorized":True,
            "old_evidence_preserved":False,
            "new_specialist_review_required":False}
        with self.assertRaises(BlockedCandidateRecoveryDenied):
            f.run()


if __name__=="__main__":
    unittest.main()
