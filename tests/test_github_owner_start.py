"""Offline GitHub OWNER Start identity, dispatch and broker fences.

No real GitHub/Supabase POST and no paid calls during this test suite.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ai_product_factory.github_owner_start import (
    FACTORY_REPO, ISSUE_NUMBER, OWNER_ID, OWNER_LOGIN, REPO_ID,
    OwnerStartBlocked, enqueue_owner_start, main,
    parse_owner_start_event, request_uuid,
)

ROOT = Path(__file__).resolve().parents[1]
ENVS = {
    "GITHUB_EVENT_NAME": "issue_comment",
    "GITHUB_REPOSITORY": FACTORY_REPO,
    "GITHUB_REF": "refs/heads/main",
    "GITHUB_ACTOR": OWNER_LOGIN,
    "SUPABASE_URL": "https://test.supabase.invalid/functions/v1/factory-runtime-control-plane",
    "SUPABASE_SECRET_KEY": "sb_secret_fake-unit-test-token",
    "GITHUB_TOKEN": "test-gh-token",
}
COMMENT_ID = 6223772
BODY = "/factory-start crm-infodive\nReconciliar issue #24 e corrigir apenas lacunas reais no CRM."


def event(*, body=BODY, comment_id=COMMENT_ID):
    owner = {"id": OWNER_ID, "login": OWNER_LOGIN}
    return {
        "action": "created",
        "repository": {
            "id": REPO_ID, "full_name": FACTORY_REPO,
            "owner": {"id": OWNER_ID, "login": OWNER_LOGIN},
        },
        "issue": {"number": ISSUE_NUMBER, "state": "open"},
        "comment": {
            "id": comment_id, "body": body, "author_association": "OWNER",
            "user": dict(owner),
        },
        "sender": dict(owner),
    }


class OwnerStartIdentityTests(unittest.TestCase):
    def test_exact_owner_issue_command_parses_with_provenance(self):
        c=parse_owner_start_event(event(),ENVS)
        self.assertEqual(c.project_key,"crm-infodive")
        self.assertEqual(c.request,"Reconciliar issue #24 e corrigir apenas lacunas reais no CRM.")
        self.assertEqual(c.actor_id,OWNER_ID)
        self.assertEqual(c.issue_number,ISSUE_NUMBER)
        self.assertEqual(c.request_id,request_uuid(ISSUE_NUMBER,COMMENT_ID))
        self.assertEqual(request_uuid(ISSUE_NUMBER,COMMENT_ID),
                         request_uuid(ISSUE_NUMBER,COMMENT_ID))
        self.assertNotEqual(request_uuid(ISSUE_NUMBER,COMMENT_ID),
                            request_uuid(ISSUE_NUMBER,COMMENT_ID+1))

    def test_event_rejects_unauthorized_identity_and_wrong_issue(self):
        mutations = (
            lambda e: e.update(action="edited"),
            lambda e: e["repository"].update(id=REPO_ID+1),
            lambda e: e["repository"].update(full_name="attacker/factory"),
            lambda e: e["repository"]["owner"].update(id=OWNER_ID+1),
            lambda e: e["issue"].update(number=713),
            lambda e: e["issue"].update(state="closed"),
            lambda e: e["issue"].update(pull_request={}),
            lambda e: e["comment"].update(author_association="MEMBER"),
            lambda e: e["comment"].update(id=False),
            lambda e: e["comment"]["user"].update(id=0),
            lambda e: e["comment"]["user"].update(login="attacker"),
            lambda e: e["sender"].update(id=0),
            lambda e: e["sender"].update(login="attacker"),
        )
        for mutate in mutations:
            with self.subTest(mutation=repr(mutate)):
                e=event()
                mutate(e)
                with self.assertRaises(OwnerStartBlocked):
                    parse_owner_start_event(e,ENVS)
        for key, value in (
            ("GITHUB_EVENT_NAME","workflow_dispatch"),
            ("GITHUB_REPOSITORY","attacker/factory"),
            ("GITHUB_REF","refs/heads/untrusted"),
            ("GITHUB_ACTOR","attacker"),
        ):
            with self.subTest(key=key):
                with self.assertRaises(OwnerStartBlocked):
                    parse_owner_start_event(event(),{**ENVS,key:value})

    def test_command_requires_anchored_header_and_real_bounded_request(self):
        invalid = (
            "/factory-wake crm-infodive\nfix",
            "/factory-start CRM\nfix",
            "/factory-start crm-infodive",
            "/factory-start crm-infodive\n",
            "/factory-start crm-infodive extra\nfix",
            "prefix /factory-start crm-infodive\nfix",
            "/factory-start crm-infodive\n" + "x"*6001,
            "/factory-start crm-infodive\ncontains\x00secret",
            "/factory-start crm-infodive\ncontains\x1bescape",
        )
        for body in invalid:
            with self.subTest(prefix=body[:45]):
                with self.assertRaises(OwnerStartBlocked):
                    parse_owner_start_event(event(body=body),ENVS)
        multiline="/factory-start crm-infodive\r\nParágrafo um.\r\n\r\nParágrafo dois."
        c=parse_owner_start_event(event(body=multiline),ENVS)
        self.assertEqual(c.request,"Parágrafo um.\n\nParágrafo dois.")
        self.assertEqual(len(parse_owner_start_event(
            event(body="/factory-start crm-infodive\n"+"y"*6000),ENVS).request),6000)


class OwnerStartRpcTests(unittest.TestCase):
    def command(self):
        return parse_owner_start_event(event(),ENVS)

    def rpc_receipt(self, *, created=True):
        d={
            "project_id":"e2ea3201-e9a3-489f-bf14-916aecc7de09",
            "task_id":"55b70b81-1903-4c54-9375-4085b75796ad",
            "run_id":"632d59cc-d9be-4949-ab73-cfc0dfdce8d6",
            "request_id":request_uuid(ISSUE_NUMBER,COMMENT_ID),
            "created":created,"source":"github-owner",
        }
        if created:d["generation"]=6
        return d

    def test_committed_new_request_dispatches_only_one_local_workflow(self):
        calls=[]
        def fake(url, body, headers):
            calls.append((url,body,headers))
            return (200,self.rpc_receipt()) if len(calls)==1 else (204,None)
        result=enqueue_owner_start(self.command(),ENVS,post=fake)
        self.assertEqual(result["status"],"enqueued")
        self.assertEqual(result["wake"],"requested")
        self.assertEqual(result["created"],True)
        self.assertEqual(result["paid_calls"],0)
        self.assertFalse(result["ready_for_production"])
        self.assertEqual(len(calls),2)
        self.assertTrue(calls[0][0].endswith(
            "/rest/v1/rpc/factory_enqueue_github_owner_continuation_v1"))
        self.assertEqual(calls[0][1]["p_request"],self.command().request)
        self.assertEqual(calls[0][1]["p_comment_id"],COMMENT_ID)
        self.assertEqual(calls[0][1]["p_actor_id"],OWNER_ID)
        self.assertEqual(calls[0][1]["p_issue_number"],ISSUE_NUMBER)
        self.assertEqual(calls[1][1],{"ref":"main","inputs":{
            "project_key":"crm-infodive","run_direct":"true",
        }})
        self.assertTrue(calls[1][0].endswith(
            "/actions/workflows/autonomous-runner.yml/dispatches"))
        self.assertNotIn("Authorization",calls[0][2])
        self.assertEqual(calls[0][2]["apikey"],ENVS["SUPABASE_SECRET_KEY"])
        self.assertTrue(calls[1][2]["Authorization"].startswith("Bearer "))

    def test_idempotent_replay_does_not_dispatch_or_double_enqueue(self):
        calls=[]
        def fake(url, body, headers):
            calls.append(url)
            return 200,self.rpc_receipt(created=False)
        result=enqueue_owner_start(self.command(),ENVS,post=fake)
        self.assertEqual(result["status"],"replayed")
        self.assertEqual(result["wake"],"not_needed")
        self.assertEqual(len(calls),1)

    def test_v2_intake_wakes_existing_resolver_without_claiming_an_unbound_source(self):
        calls=[]
        env={**ENVS,"FACTORY_JOURNEY_DELIVERY_BINDING_V2":"true"}
        def fake(url, body, headers):
            calls.append((url,body))
            return 200,{
                "project_id":"e2ea3201-e9a3-489f-bf14-916aecc7de09",
                "journey_id":"61bc7a1f-dcab-4616-9ce7-1ff28a0aa915",
                "request_id":request_uuid(ISSUE_NUMBER,COMMENT_ID),"created":True,
                "source":"github-owner","state":"awaiting_source",
            }
        result=enqueue_owner_start(self.command(),env,post=fake)
        self.assertEqual(result["status"],"intake_wake_unavailable")
        self.assertEqual(result["wake"],"failed")
        self.assertEqual(result["paid_calls"],0)
        self.assertEqual(len(calls),2)
        self.assertTrue(calls[1][0].endswith("/actions/workflows/autonomous-runner.yml/dispatches"))
        self.assertTrue(calls[0][0].endswith("/rest/v1/rpc/factory_enqueue_journey_intake_v2"))
        self.assertEqual(calls[0][1]["p_request_id"],request_uuid(ISSUE_NUMBER,COMMENT_ID))

    def test_wake_failure_keeps_durable_run_not_misreports_complete(self):
        def fake(url, body, headers):
            if url.endswith("dispatches"):return 403,None
            return 200,self.rpc_receipt()
        result=enqueue_owner_start(self.command(),ENVS,post=fake)
        self.assertEqual(result["status"],"enqueued_wake_unavailable")
        self.assertEqual(result["wake"],"failed")
        self.assertTrue(result["created"])
        result=enqueue_owner_start(self.command(),{**ENVS,"GITHUB_TOKEN":""},
                                   post=lambda u,b,h:(200,self.rpc_receipt()))
        self.assertEqual(result["wake"],"failed")

    def test_missing_rpc_or_admission_block_prevents_dispatch(self):
        from urllib.error import HTTPError
        for status,reason in ((404,"owner_start_migration_not_applied"),
                              (409,"control_plane_admission_blocked"),
                              (403,"control_plane_admission_blocked")):
            calls=[]
            def fake(url,body,headers):
                calls.append(url)
                raise HTTPError(url,status,"denied",None,None)
            with self.subTest(status=status):
                with self.assertRaises(OwnerStartBlocked) as ex:
                    enqueue_owner_start(self.command(),ENVS,post=fake)
                self.assertEqual(ex.exception.code,reason)
                self.assertEqual(len(calls),1)

    def test_wrong_uuid_source_idempotency_or_generation_blocks_without_wake(self):
        mutations=(
            lambda r:r.update(source="factory-console"),
            lambda r:r.update(request_id="a"*36),
            lambda r:r.update(project_id="not-uuid"),
            lambda r:r.update(created="true"),
            lambda r:r.update(generation=0),
            lambda r:r.update(run_id=r["task_id"]),
        )
        for mutate in mutations:
            r=self.rpc_receipt()
            mutate(r)
            calls=[]
            with self.subTest(mutation=repr(mutate)):
                with self.assertRaises(OwnerStartBlocked) as exc:
                    enqueue_owner_start(
                        self.command(),ENVS,
                        post=lambda u,b,h:(calls.append(u) or 200,r),
                    )
                self.assertEqual(exc.exception.code,"invalid_control_plane_receipt")
                self.assertEqual(len(calls),1)

    def test_no_supabase_secret_fails_before_network(self):
        with self.assertRaises(OwnerStartBlocked) as e:
            enqueue_owner_start(self.command(),
                                {**ENVS,"SUPABASE_SECRET_KEY":"",
                                 "SUPABASE_SERVICE_ROLE_KEY":""},
                                post=lambda u,b,h: self.fail("network called"))
        self.assertEqual(e.exception.code,"control_plane_unavailable")

    def test_main_never_echoes_prompt_or_token_on_untrusted_event(self):
        e=event(body="/factory-start crm-infodive\nsecret customer password")
        e["comment"]["user"]["id"]=0
        with tempfile.TemporaryDirectory() as tmp:
            ev=Path(tmp)/"event.json"
            receipt=Path(tmp)/"receipt.json"
            ev.write_text(json.dumps(e))
            with patch.dict("os.environ",ENVS,clear=True):
                with patch("sys.stdout",new_callable=__import__("io").StringIO) as out:
                    exit_code=main(["--event-path",str(ev),"--mode","enqueue",
                                    "--output",str(receipt)])
            self.assertEqual(exit_code,2)
            self.assertEqual(json.loads(receipt.read_text())["reason"],"invalid_event_identity")
            self.assertNotIn("password",out.getvalue())
            self.assertNotIn("sb_secret_",out.getvalue())


class OwnerStartWorkflowContractTests(unittest.TestCase):
    def test_entrypoint_never_wakes_scheduler_from_untrusted_comment(self):
        workflow=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
        job=workflow.split("\n  owner-start:\n",1)[1]
        for invariant in (
            "github.event_name == 'issue_comment'",
            "github.event.action == 'created'",
            "github.event.issue.number == 1055",
            "github.event.comment.author_association == 'OWNER'",
            "github.actor == github.event.comment.user.login",
            "github.event.comment.user.id == 256917842",
            "github.event.repository.id == 1387883686",
            "startsWith(github.event.comment.body, '/factory-start ')",
            "needs: schedule-probe",
            "always()",
            "environment: openai-api",
            "actions: write",
            "id-token: write",
            "persist-credentials: false",
            "Authenticate exact GitHub owner command before OIDC",
            "uses: ./.github/actions/control-plane-oidc",
            "--mode enqueue",
            "upload-artifact",
            "if-no-files-found: warn",
        ):
            self.assertIn(invariant,job)
        self.assertLess(job.index("--mode validate"),
                        job.index("uses: ./.github/actions/control-plane-oidc"))
        owner_start_source=(ROOT/"src/ai_product_factory/github_owner_start.py").read_text()
        self.assertIn('"run_direct": "true"',owner_start_source)
        for forbidden in (
            "OPENAI_API_KEY","CODEX_ACCESS_TOKEN","FACTORY_GITHUB_TOKEN",
            "VERCEL_TOKEN","issues: write","contents: write",
            "gh pr merge","--mode direct","--mode product","--mode codex",
            "pull_request_target",
        ):
            self.assertNotIn(forbidden,job)
        self.assertIn("github.event.comment.body == '/factory-wake'",workflow)
        self.assertNotIn("startsWith(github.event.comment.body, '/factory-start ')",workflow.split("\n  schedule-probe:\n",1)[1].split("\n  github-access-preflight:\n",1)[0])

    def test_broker_restricts_mutation_to_exact_signed_owner_event(self):
        broker=(ROOT/"supabase/functions/factory-runtime-control-plane/index.ts").read_text()
        trigger='if(suffix==="/rest/v1/rpc/factory_enqueue_github_owner_continuation_v1")'
        self.assertIn(trigger,broker)
        gated=broker.split(trigger,1)[1].split('const headers=supabaseHeaders',1)[0]
        for clause in (
            'req.method!=="POST"',
            'requestUrl.search',
            'String(identity.event_name||"")!=="issue_comment"',
            'String(identity.workflow_ref||"")!==TRUSTED_BACKUP_WORKFLOW_REF',
            'String(identity.actor_id||"")!==EXPECTED.repository_owner_id',
            '"github_owner_start_oidc_required"',
        ):
            self.assertIn(clause,gated)


    def test_owner_greenfield_migration_requires_exact_original_console_origin(self):
        sql=(ROOT/"supabase/migrations/20261023214000_factory_greenfield_owner_continuation.sql").read_text()
        for required in (
            "factory_enqueue_github_owner_continuation_v1",
            "verified greenfield intake provenance required",
            "greenfield bootstrap not uniquely completed",
            "greenfield atomic Console intake receipts incomplete",
            "greenfield attachment ownership mismatch",
            "another active project cycle exists",
            "FOR UPDATE",
            "FOR SHARE",
            "SECURITY INVOKER",
            "FROM PUBLIC,anon,authenticated",
            "TO service_role",
        ):
            self.assertIn(required,sql)
        self.assertNotIn("SECURITY DEFINER",sql)
        self.assertNotIn("'human','factory-console',",sql)

    def test_sql_rpc_is_new_service_only_not_console_alias(self):
        sql=(ROOT/"supabase/migrations/20261022211500_factory_github_owner_continuation.sql").read_text()
        for clause in (
            "CREATE OR REPLACE FUNCTION public.factory_enqueue_github_owner_continuation_v1",
            "SECURITY INVOKER",
            "SET search_path TO ''",
            "FOR UPDATE",
            "FOR SHARE",
            "v_request_id := pg_catalog.md5",
            "project.continuation.requested",
            "project.reconciliation.enqueued",
            "'github-owner'",
            "'execution_generation',v_generation",
            "FROM PUBLIC,anon,authenticated",
            "TO service_role",
        ):
            self.assertIn(clause,sql)
        self.assertNotIn("SECURITY DEFINER",sql)
        self.assertNotIn("'human','factory-console'",sql)
        self.assertNotIn("DROP TABLE",sql)


if __name__ == "__main__":
    unittest.main()
