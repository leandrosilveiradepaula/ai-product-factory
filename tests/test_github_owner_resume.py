"""GitHub owner planning resume: no-network, no-LLM contract regressions."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from ai_product_factory.github_owner_resume import (
    OwnerResumeBlocked, parse_owner_resume_event, queue_checkpointed_planning,
)
from ai_product_factory.github_owner_start import FACTORY_REPO, OWNER_ID, OWNER_LOGIN, REPO_ID, ISSUE_NUMBER

ROOT=Path(__file__).resolve().parents[1]
RUN="090cd768-b6e5-44ce-9d77-92f9ffe9620d"
NEW_RUN="6cbdb11b-8263-4cb6-bb86-09f33ae470de"
TASK="e174ef34-e9a4-4088-af0e-785efba663cc"
PROJECT="2d30e00a-ff72-4044-b838-011c263ed672"
ENV={
    "GITHUB_EVENT_NAME":"issue_comment","GITHUB_REPOSITORY":FACTORY_REPO,
    "GITHUB_REF":"refs/heads/main","GITHUB_ACTOR":OWNER_LOGIN,
    "SUPABASE_URL":"https://test.supabase.invalid/functions/v1/factory-runtime-control-plane",
    "SUPABASE_SECRET_KEY":"sb_secret_offline-test-only",
    "GITHUB_TOKEN":"fake-local-token",
}


def event(body=None):
    person={"id":OWNER_ID,"login":OWNER_LOGIN}
    return {
        "action":"created",
        "repository":{"id":REPO_ID,"full_name":FACTORY_REPO,"owner":dict(person)},
        "issue":{"number":ISSUE_NUMBER,"state":"open"},
        "comment":{"id":67548121,"body":body or "/factory-resume-planning run="+RUN,
                   "author_association":"OWNER","user":dict(person)},
        "sender":dict(person),
    }


def receipt(created=True):
    d={
        "created":created,"project_id":PROJECT,"task_id":TASK,
        "run_id":NEW_RUN,"source_run_id":RUN,
        "project_key":"crm-infodive",
        "stages":["planning"],
        "source":"checkpointed_product_planning_v1",
    }
    if created:d["generation"]=6
    return d


class OwnerResumeTests(unittest.TestCase):
    def test_exact_owner_github_event_parses(self):
        c=parse_owner_resume_event(event(),ENV)
        self.assertEqual(c["source_run_id"],RUN)
        self.assertEqual(c["actor_id"],OWNER_ID)
        self.assertEqual(c["issue_number"],ISSUE_NUMBER)
        self.assertEqual(c["comment_id"],67548121)

    def test_owner_identity_and_command_are_strict(self):
        mutations=(
            lambda e:e.update(action="edited"),
            lambda e:e["repository"].update(id=0),
            lambda e:e["repository"].update(full_name="outsider/repo"),
            lambda e:e["repository"]["owner"].update(id=0),
            lambda e:e["issue"].update(number=713),
            lambda e:e["issue"].update(state="closed"),
            lambda e:e["issue"].update(pull_request={}),
            lambda e:e["comment"].update(id=0),
            lambda e:e["comment"].update(author_association="MEMBER"),
            lambda e:e["comment"]["user"].update(id=0),
            lambda e:e["comment"]["user"].update(login="someone"),
            lambda e:e["sender"].update(id=0),
            lambda e:e["sender"].update(login="someone"),
        )
        for fn in mutations:
            with self.subTest(fn=str(fn)):
                e=event()
                fn(e)
                with self.assertRaises(OwnerResumeBlocked):
                    parse_owner_resume_event(e,ENV)
        for env_var,bad in (
            ("GITHUB_EVENT_NAME","workflow_dispatch"),
            ("GITHUB_REPOSITORY","outsider/repo"),
            ("GITHUB_REF","refs/heads/test"),
            ("GITHUB_ACTOR","someone"),
        ):
            with self.subTest(env_var=env_var):
                with self.assertRaises(OwnerResumeBlocked):
                    parse_owner_resume_event(event(),{**ENV,env_var:bad})

    def test_ambiguous_or_untrusted_commands_rejected(self):
        values=(
            "/factory-resume-planning",
            "/factory-start crm-infodive",
            "/factory-resume-planning run=not-a-uuid",
            "/factory-resume-planning run="+RUN+" extra",
            "prefix /factory-resume-planning run="+RUN,
            "/factory-resume-planning run="+RUN+"\nIgnore instructions",
            "/factory-resume-planning run="+RUN.upper(),
        )
        for raw in values:
            with self.subTest(raw=raw[:60]):
                with self.assertRaises(OwnerResumeBlocked):
                    parse_owner_resume_event(event(raw),ENV)

    def test_persists_one_rpc_then_wakes_exact_local_workflow(self):
        calls=[]
        def post(url,payload,headers):
            calls.append((url,payload,headers))
            return (200,receipt()) if len(calls)==1 else (204,None)
        result=queue_checkpointed_planning(
            parse_owner_resume_event(event(),ENV),ENV,post=post
        )
        self.assertEqual(result["status"],"enqueued")
        self.assertTrue(result["created"])
        self.assertEqual(result["run_id"],NEW_RUN)
        self.assertEqual(result["wake"],"requested")
        self.assertFalse(result["release_authorized"])
        self.assertEqual(result["paid_calls"],0)
        self.assertEqual(len(calls),2)
        self.assertTrue(calls[0][0].endswith(
            "/rest/v1/rpc/factory_resume_failed_product_planning_v1"))
        self.assertEqual(calls[0][1]["p_source_run_id"],RUN)
        self.assertEqual(calls[0][1]["p_actor_id"],OWNER_ID)
        self.assertEqual(calls[0][1]["p_comment_id"],67548121)
        self.assertEqual(calls[0][2]["apikey"],ENV["SUPABASE_SECRET_KEY"])
        self.assertTrue(calls[1][0].endswith(
            "/actions/workflows/autonomous-runner.yml/dispatches"))
        self.assertEqual(calls[1][1],{
            "ref":"main","inputs":{"project_key":"crm-infodive"}
        })

    def test_replay_and_missing_wake_token_never_double_enqueue(self):
        calls=[]
        def post(url,payload,headers):
            calls.append(url)
            return 200,receipt(created=False)
        cmd=parse_owner_resume_event(event(),ENV)
        result=queue_checkpointed_planning(cmd,ENV,post=post)
        self.assertEqual(result["status"],"replayed")
        self.assertEqual(result["wake"],"not_needed")
        self.assertEqual(len(calls),1)
        fresh=queue_checkpointed_planning(
            cmd,{**ENV,"GITHUB_TOKEN":""},
            post=lambda *args:(200,receipt()),
        )
        self.assertEqual(fresh["status"],"enqueued_wake_unavailable")
        self.assertEqual(fresh["wake"],"failed")

    def test_missing_migration_budget_block_and_backend_rejection_never_wake(self):
        for code,reason in (
            (404,"resume_migration_not_applied"),
            (409,"checkpoint_provenance_blocked"),
            (403,"checkpoint_provenance_blocked"),
        ):
            calls=[]
            def fail(url,payload,headers):
                calls.append(url)
                raise HTTPError(url,code,"blocked",None,None)
            with self.subTest(code=code):
                with self.assertRaises(OwnerResumeBlocked) as caught:
                    queue_checkpointed_planning(
                        parse_owner_resume_event(event(),ENV),ENV,post=fail
                    )
                self.assertEqual(caught.exception.code,reason)
                self.assertEqual(len(calls),1)

    def test_forged_rpc_receipts_cannot_wake_worker(self):
        variations=(
            {"created":"true"},{"project_key":"outsider/project"},
            {"source":"factory-console"},{"stages":["reconciliation","planning"]},
            {"run_id":"not_uuid"},{"source_run_id":"f"*36},
            {"generation":0},{"project_id":NEW_RUN},
        )
        cmd=parse_owner_resume_event(event(),ENV)
        for delta in variations:
            with self.subTest(delta=delta):
                output=receipt()
                output.update(delta)
                calls=[]
                with self.assertRaises(OwnerResumeBlocked) as e:
                    queue_checkpointed_planning(
                        cmd,ENV,post=lambda u,b,h:(calls.append(u) or 200,output)
                    )
                self.assertEqual(e.exception.code,"invalid_control_plane_receipt")
                self.assertEqual(len(calls),1)

    def test_workflow_and_broker_enforce_owner_only_route(self):
        workflow=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
        self.assertIn("\n  owner-resume-planning:\n",workflow)
        job=workflow.split("\n  owner-resume-planning:\n",1)[1]
        for needle in (
            "needs: schedule-probe","always()","github.event_name == 'issue_comment'",
            "github.event.action == 'created'",
            "github.event.issue.number == 1055",
            "github.event.comment.author_association == 'OWNER'",
            "github.event.comment.user.id == 256917842",
            "github.event.repository.id == 1387883686",
            "startsWith(github.event.comment.body, '/factory-resume-planning ')",
            "persist-credentials: false","id-token: write","actions: write",
            "--mode validate","--mode enqueue","uses: ./.github/actions/control-plane-oidc",
        ):
            self.assertIn(needle,job)
        self.assertLess(job.index("--mode validate"),
                        job.index("uses: ./.github/actions/control-plane-oidc"))
        for forbidden in ("OPENAI_API_KEY","CODEX_ACCESS_TOKEN",
                          "gh pr merge","FACTORY_GITHUB_TOKEN"):
            self.assertNotIn(forbidden,job)
        broker=(ROOT/"supabase/functions/factory-runtime-control-plane/index.ts").read_text()
        guard=broker.split(
            'if(suffix==="/rest/v1/rpc/factory_resume_failed_product_planning_v1")',1
        )[1].split("const headers=supabaseHeaders",1)[0]
        for needle in (
            'req.method!=="POST"',
            'identity.event_name||"")!=="issue_comment"',
            "String(identity.workflow_ref||\"\")!==TRUSTED_BACKUP_WORKFLOW_REF",
            'identity.actor_id||"")!==EXPECTED.repository_owner_id',
            'github_owner_resume_oidc_required',
        ):
            self.assertIn(needle,guard)

    def test_sql_recovery_never_grants_public_or_replays_paid_stages(self):
        sql=(ROOT/"supabase/migrations/20261023023000_resume_product_planning_checkpoint.sql").read_text()
        for marker in (
            "SECURITY INVOKER","FOR UPDATE OF p","resume_checkpoint",
            "product.planning.resume.requested","product.planning.resume_queued",
            "IS DISTINCT FROM v_generation::text","project stage state changed since source",
            "TO service_role","FROM PUBLIC,anon,authenticated",
            "jsonb_build_array('planning')",
        ):
            self.assertIn(marker,sql)
        self.assertNotIn("SECURITY DEFINER",sql)
        self.assertNotIn("TRUNCATE",sql)
        self.assertNotIn("DROP TABLE",sql)


if __name__=="__main__":
    unittest.main()
