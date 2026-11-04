"""No paid model, no generic retry, no fabricated success for CRM209 native lane."""
from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ai_product_factory.crm209_native_ci_worker import (
    BRANCH, CS, GENERATION, PROJECT, REPO, REQUEST, SHA,
    NativeCheckpointGitHub, PaidModelForbidden, run_once,
)


class FakeGitHub:
    repository = REPO
    def __init__(self, drift=False):
        self.drift = drift
        self.calls = []
    def get_branch_sha(self, branch):
        self.calls.append(("get_branch_sha", branch))
        return "f" * 40 if self.drift else SHA
    def get_pull_request(self, pr):
        self.calls.append(("get_pull_request", pr))
        return SimpleNamespace(
            number=212,head_sha=SHA,state="open",merged=False,draft=False,
            head_ref="factory/journey-bb14e150-2c7e-423b-8e5d-e211dab6225c",
            base_ref="preview/crm209-delivery-v4",head_repository=REPO
        )
    def commit_files(self,*a,**k):
        self.calls.append(("commit_files",a,k))
        return "a"*40


class Access:
    def __init__(self):self.grants=[]
    def require_capabilities(self,project,capabilities):
        self.grants.append((project,capabilities))


class Store:
    def __init__(self):self.blocked=[]
    def block_work_unit(self,**kw):self.blocked.append(kw)


class Builder:
    def __init__(self,*,github,store,producer,execution_route):
        self.github=github
        self.store=store
        self.producer=producer
        self.execution_route=execution_route
    def execute(self,item):
        assert self.execution_route=="direct"
        self.github.commit_files(item.branch,{"test/contract-access.test.ts":"safe"})
        return SimpleNamespace(
            run_id=item.run_id,change_set_id=CS,work_unit_id=item.work_unit_id,
            branch=BRANCH,output_commit="a"*40,
            changed_files=("src/services/ContractService.ts","test/contract-access.test.ts")
        )


CLAIM={
    "status":"claimed","claimed":True,"paid_model_calls":0,
    "model_calls_allowed":False,"release_authorized":False,
    "repository":REPO,"project_key":PROJECT,"change_set_id":CS,
    "candidate_commit":SHA,"branch":BRANCH,"wave":5,
    "execution_generation":GENERATION,
    "run_id":"7a7a7a7a-0000-4000-8000-000000000001",
    "task_id":"7a7a7a7a-0000-4000-8000-000000000002",
    "work_unit_id":"7a7a7a7a-0000-4000-8000-000000000003",
    "title":"Verified native CI import","description":"No model",
}
VERIFIED={"status":"verified","run_id":CLAIM["run_id"],
          "model_calls_allowed":False,"release_authorized":False}


class NativeCIWorkerTests(unittest.TestCase):
    def test_model_producer_always_refuses_even_for_direct(self):
        with self.assertRaisesRegex(PermissionError,"refuses ALL paid"):
            PaidModelForbidden().produce(SimpleNamespace())

    @patch.dict(os.environ, {"FACTORY_CRM209_NATIVE_ENABLED":"false"}, clear=True)
    def test_disabled_is_inert_without_credentials(self):
        self.assertEqual(run_once(worker_id="nativeci-12345678")["status"],"disabled")

    def call(self,*,response=None,github=None,checkpoint=None,enabled=True):
        issued=[]
        access=Access()
        store=Store()
        github=github or FakeGitHub()
        def rpc(name,payload):
            issued.append((name,payload))
            if name=="factory_claim_crm209_native_ci_once":
                return CLAIM.copy() if response is None else response
            if name=="factory_assert_crm209_native_ci_claim":
                return VERIFIED.copy() if checkpoint is None else checkpoint
            raise AssertionError("unexpected RPC "+name)
        with patch.dict(os.environ,{
            "FACTORY_CRM209_NATIVE_ENABLED":"true" if enabled else "false",
            "FACTORY_GITHUB_TOKEN":"test-only-nonsecret-placeholder"
        }):
            result=run_once(
                worker_id="nativeci-12345678",rpc=rpc,
                github_factory=lambda **kw:github,
                store_factory=lambda:store,
                builder_factory=Builder,access_factory=lambda:access,
            )
        return result,issued,github,store,access

    def test_exact_claim_and_checkpoint_allows_one_native_commit(self):
        result,calls,gh,store,access=self.call()
        self.assertEqual(result["status"],"work_unit_completed")
        self.assertEqual(result["paid_model_calls"],0)
        self.assertIs(result["release_authorized"],False)
        self.assertEqual([name for name,_ in calls],[
            "factory_claim_crm209_native_ci_once",
            "factory_assert_crm209_native_ci_claim",
            "factory_assert_crm209_native_ci_claim",
        ])
        self.assertIn(("commit_files",),[c[:1] for c in gh.calls])
        self.assertFalse(store.blocked)
        self.assertEqual(access.grants[0][0],PROJECT)

    def test_unapplied_migration_is_not_reported_as_success(self):
        result,calls,gh,_,_=self.call(response={"status":"blocked_migration_not_applied"})
        self.assertEqual(result["status"],"blocked_migration_not_applied")
        self.assertEqual(result["claimed"],False)
        self.assertEqual(len(calls),1)
        self.assertFalse(any(c[0]=="commit_files" for c in gh.calls))

    def test_no_work_is_idempotent(self):
        result,calls,_,_,_=self.call(response={
            "status":"idle","claimed":False,"paid_model_calls":0,
            "release_authorized":False
        })
        self.assertEqual(result["status"],"idle")
        self.assertEqual(len(calls),1)

    def test_claim_tampering_fails_before_github_write(self):
        for key,value in (
            ("candidate_commit","b"*40),
            ("project_key","ai-product-factory"),
            ("branch","other"),
            ("paid_model_calls",1),
            ("model_calls_allowed",True),
            ("release_authorized",True),
            ("work_unit_id","not-a-uuid")
        ):
            with self.subTest(key=key):
                gh=FakeGitHub()
                with self.assertRaises(PermissionError):
                    self.call(response={**CLAIM,key:value},github=gh)
                self.assertFalse(any(c[0]=="commit_files" for c in gh.calls))

    def test_live_github_sha_drift_blocks_before_sql_claim(self):
        gh=FakeGitHub(drift=True)
        with self.assertRaisesRegex(PermissionError,"candidate has changed"):
            self.call(github=gh)
        self.assertFalse(any(c[0]=="commit_files" for c in gh.calls))

    def test_epoch_revocation_before_commit_fails_closed(self):
        gh=FakeGitHub()
        store=Store()
        calls=[]
        def rpc(name,payload):
            calls.append(name)
            if name=="factory_claim_crm209_native_ci_once":return CLAIM.copy()
            return {"status":"revoked"}
        with patch.dict(os.environ,{
            "FACTORY_CRM209_NATIVE_ENABLED":"true",
            "FACTORY_GITHUB_TOKEN":"test-only-nonsecret-placeholder"
        }):
            with self.assertRaises(PermissionError):
                run_once(worker_id="nativeci-12345678",rpc=rpc,
                         github_factory=lambda **kw:gh,
                         store_factory=lambda:store,
                         builder_factory=Builder,
                         access_factory=Access)
        self.assertFalse(any(c[0]=="commit_files" for c in gh.calls))
        self.assertEqual(len(store.blocked),1)

    def test_checkpoint_wrapper_refuses_write_when_verification_fails(self):
        gh=FakeGitHub()
        writes=NativeCheckpointGitHub(gh,lambda: (_ for _ in ()).throw(PermissionError("lease revoked")))
        with self.assertRaisesRegex(PermissionError,"lease revoked"):
            writes.commit_files("branch",{"file":"test"})
        self.assertFalse(gh.calls)


if __name__=="__main__":
    unittest.main()
