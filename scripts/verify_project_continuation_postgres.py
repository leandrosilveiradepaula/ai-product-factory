#!/usr/bin/env python3
"""Isolated PostgreSQL concurrency test using the exact versioned Factory migration."""
from __future__ import annotations
import os
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.types.json import Jsonb

ROOT=Path(__file__).resolve().parents[1]
MIG=ROOT/"supabase/migrations/20261014160500_atomic_project_continuation.sql"
OWNER_MIG=ROOT/"supabase/migrations/20261022211500_factory_github_owner_continuation.sql"
RESUME_MIG=ROOT/"supabase/migrations/20261023023000_resume_product_planning_checkpoint.sql"
DSN=os.environ.get("FACTORY_CONTINUATION_PG_TEST_DSN","")

def require_isolated():
    if os.environ.get("FACTORY_CONTINUATION_PG_TEST_ISOLATED")!="true":
        raise RuntimeError("isolated PostgreSQL opt-in missing")
    cfg=conninfo_to_dict(DSN)
    if cfg.get("host") not in ("localhost","127.0.0.1","::1"):
        raise RuntimeError("refusing remote PostgreSQL")
    if cfg.get("dbname")!="factory_continuation_test":
        raise RuntimeError("refusing non-dedicated database")

SETUP="""
CREATE ROLE service_role NOLOGIN;
CREATE ROLE anon NOLOGIN;
CREATE ROLE authenticated NOLOGIN;
CREATE TABLE public.factory_projects (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), project_key text NOT NULL UNIQUE,
 project_kind text NOT NULL DEFAULT 'existing',
 manifest jsonb NOT NULL DEFAULT '{}'::jsonb, is_active boolean NOT NULL DEFAULT true,
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE public.factory_project_execution_controls (
 project_id uuid PRIMARY KEY REFERENCES public.factory_projects(id),
 state text NOT NULL DEFAULT 'running',
 generation bigint NOT NULL DEFAULT 6
);
CREATE TABLE public.factory_tasks (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), project_id uuid NOT NULL REFERENCES public.factory_projects(id),
 parent_task_id uuid REFERENCES public.factory_tasks(id), external_key text,
 title text NOT NULL, description text, status text NOT NULL DEFAULT 'queued',
 complexity text NOT NULL DEFAULT 'medium', risk jsonb NOT NULL DEFAULT '{}'::jsonb,
 acceptance_criteria jsonb NOT NULL DEFAULT '[]'::jsonb, depends_on jsonb NOT NULL DEFAULT '[]'::jsonb,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE public.factory_runs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), task_id uuid NOT NULL REFERENCES public.factory_tasks(id),
 status text NOT NULL DEFAULT 'created',execution_route text,metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE public.factory_tool_usage (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, run_id uuid REFERENCES public.factory_runs(id),
 tool_family text NOT NULL,operation text,usage_units numeric,estimated_cost numeric,
 metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE public.factory_project_state_snapshots (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 project_id uuid NOT NULL REFERENCES public.factory_projects(id),
 run_id uuid REFERENCES public.factory_runs(id),
 observed_stage text, summary text NOT NULL,
 evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
 gaps jsonb NOT NULL DEFAULT '[]'::jsonb,
 constraints jsonb NOT NULL DEFAULT '[]'::jsonb,
 source_status jsonb NOT NULL DEFAULT '{}'::jsonb,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE public.factory_audit_events (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,project_id uuid REFERENCES public.factory_projects(id),
 run_id uuid REFERENCES public.factory_runs(id), task_id uuid REFERENCES public.factory_tasks(id),
 actor_type text NOT NULL,actor_ref text,event_type text NOT NULL,
 payload jsonb NOT NULL DEFAULT '{}'::jsonb,created_at timestamptz NOT NULL DEFAULT now()
);
"""

def make_project():
    key="case-"+uuid.uuid4().hex[:22]
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute("insert into public.factory_projects(project_key) values (%s) returning id",(key,))
        ident=cur.fetchone()[0]
    return key,ident

def submit(key,req,request_id):
    with psycopg.connect(DSN) as conn,conn.cursor() as cur:
        cur.execute("select public.factory_enqueue_project_continuation(%s,%s,%s,%s)",
                    (key,req,request_id,0))
        return cur.fetchone()[0]


def owner_submit(key, req, comment_id=55550, *, issue=1055, actor_id=256917842,
                 actor_login="leandrosilveiradepaula"):
    with psycopg.connect(DSN) as conn,conn.cursor() as cur:
        cur.execute(
            "select public.factory_enqueue_github_owner_continuation_v1(%s,%s,%s,%s,%s,%s)",
            (key,req,comment_id,issue,actor_id,actor_login),
        )
        return cur.fetchone()[0]

def make_owner_project(*, project_kind="existing", state="running", generation=6):
    key,pid=make_project()
    with psycopg.connect(DSN) as conn,conn.cursor() as cur:
        cur.execute(
            "update public.factory_projects set project_kind=%s where id=%s",
            (project_kind,pid),
        )
        cur.execute(
            "insert into public.factory_project_execution_controls"
            "(project_id,state,generation) values (%s,%s,%s)",
            (pid,state,generation),
        )
    return key,pid


def make_paid_checkpoint(*, state="running", generation=6, fail_reason=None):
    """Create a real persisted stage lineage without making paid model calls."""
    key,pid=make_owner_project(state=state,generation=generation)
    admission=owner_submit(key,"Corrigir a issue CRM #24",comment_id=880098)
    run_id=admission["run_id"]
    task_id=admission["task_id"]
    failure=fail_reason or "reserved provider cost exceeds remaining budget"
    gap={
        "gaps":[{"id":"crm-ui","source":"current codebase"}],
        "recommended_next_work":[{"work":"fix automation condition editor"}],
        "_evidence":{"provider_ref":"already-metered-provider-call"},
    }
    with psycopg.connect(DSN) as conn,conn.cursor() as cur:
        cur.execute(
            "update public.factory_runs set status='failed', "
            "metadata=metadata||%s where id=%s",
            (Jsonb({"error":failure,"execution_generation":6}),run_id),
        )
        cur.execute(
            "update public.factory_tasks set status='failed' where id=%s",
            (task_id,),
        )
        cur.execute(
            "insert into public.factory_project_state_snapshots("
            "project_id,run_id,observed_stage,summary,evidence,gaps,constraints,source_status)"
            "values(%s,%s,'repository','Live candidate inspected',%s,%s,%s,%s) returning id",
            (pid,run_id,
             Jsonb([{"sha":"a"*40}]),Jsonb([]),Jsonb([]),
             Jsonb({"github":"verified"})),
        )
        snap_id=cur.fetchone()[0]
        cur.execute(
            "update public.factory_projects set manifest=manifest||"
            "jsonb_build_object('gap_analysis',%s::jsonb) where id=%s",
            (Jsonb(gap),pid),
        )
        for stage in ("reconciliation","gap_analysis"):
            cur.execute(
                "insert into public.factory_audit_events("
                "project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)"
                "values(%s,%s,%s,'system','runtime-worker','run.stage.recorded',%s)",
                (pid,task_id,run_id,Jsonb({"stage":stage,"status":"completed"})),
            )
            payload={"stage":stage,"created_tasks":0,"human_gate_id":None,
                     "snapshot_id":str(snap_id) if stage=="reconciliation" else None}
            cur.execute(
                "insert into public.factory_audit_events("
                "project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)"
                "values(%s,%s,%s,'system','runtime-worker','product.stage.persisted',%s)",
                (pid,task_id,run_id,Jsonb(payload)),
            )
        cur.execute(
            "insert into public.factory_audit_events("
            "project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)"
            "values(%s,%s,%s,'system','runtime-worker','run.stage.recorded',%s)",
            (pid,task_id,run_id,Jsonb({"stage":"planning","status":"failed"})),
        )
    return dict(key=key,project_id=pid,task_id=task_id,
                run_id=run_id,snapshot_id=snap_id,gap=gap)

def resume_planning(source_id, *, comment_id=778872, issue=1055,
                    actor_id=256917842, actor_login="leandrosilveiradepaula"):
    with psycopg.connect(DSN) as conn,conn.cursor() as cur:
        cur.execute(
            "select public.factory_resume_failed_product_planning_v1(%s,%s,%s,%s,%s)",
            (source_id,comment_id,issue,actor_id,actor_login),
        )
        return cur.fetchone()[0]

def bootstrap(key):
    with psycopg.connect(DSN) as conn,conn.cursor() as cur:
        cur.execute("select public.factory_enqueue_project_bootstrap(%s)",(key,))
        return cur.fetchone()[0]

def counts(project_id):
    with psycopg.connect(DSN) as conn,conn.cursor() as cur:
        cur.execute("select count(*) from public.factory_tasks where project_id=%s",(project_id,))
        tasks=cur.fetchone()[0]
        cur.execute("select count(*) from public.factory_audit_events where project_id=%s",(project_id,))
        audit=cur.fetchone()[0]
        return tasks,audit

class ContinuationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require_isolated()
        with psycopg.connect(DSN,autocommit=True) as conn:
            conn.execute(SETUP)
            conn.execute(MIG.read_text())
            conn.execute(OWNER_MIG.read_text())
            conn.execute(RESUME_MIG.read_text())

    def test_same_request_concurrent_retries_share_one_run(self):
        key,pid=make_project()
        req_id=uuid.uuid4()
        barrier=Barrier(2)
        def worker():
            barrier.wait()
            return submit(key,"atualizar backlog",req_id)
        with ThreadPoolExecutor(max_workers=2) as executor:
            a,b=list(executor.map(lambda _:worker(),range(2)))
        self.assertEqual(a["run_id"],b["run_id"])
        self.assertEqual(sorted([a["created"],b["created"]]),[False,True])
        self.assertEqual(counts(pid),(1,2))
        self.assertEqual(submit(key,"atualizar backlog",req_id)["created"],False)
        with self.assertRaisesRegex(Exception,"different content"):
            submit(key,"outra solicitação",req_id)

    def test_competing_different_requests_rejects_second_without_overwrite(self):
        key,pid=make_project()
        barrier=Barrier(2)
        def worker(n):
            barrier.wait()
            try:return submit(key,"pedido "+str(n),uuid.uuid4())
            except psycopg.Error as error:return str(error)
        with ThreadPoolExecutor(max_workers=2) as executor:
            a,b=list(executor.map(worker,[1,2]))
        ok=[v for v in (a,b) if isinstance(v,dict)]
        blocked=[v for v in (a,b) if isinstance(v,str)]
        self.assertEqual(len(ok),1)
        self.assertEqual(len(blocked),1)
        self.assertIn("another active project cycle exists",blocked[0])
        self.assertEqual(counts(pid),(1,2))

    def test_old_queued_child_of_completed_parent_does_not_block(self):
        key,pid=make_project()
        with psycopg.connect(DSN) as conn,conn.cursor() as cur:
            cur.execute("insert into public.factory_tasks(project_id,title,status) values (%s,'old root','completed') returning id",(pid,))
            parent=cur.fetchone()[0]
            cur.execute("insert into public.factory_tasks(project_id,parent_task_id,title,status) values (%s,%s,'historical child','queued')",(pid,parent))
        result=submit(key,"novo ciclo",uuid.uuid4())
        self.assertTrue(result["created"])
        self.assertEqual(counts(pid)[0],3)

    def test_active_root_blocks_even_after_historical_child(self):
        key,pid=make_project()
        with psycopg.connect(DSN) as conn,conn.cursor() as cur:
            cur.execute("insert into public.factory_tasks(project_id,title,status) values (%s,'active','queued')",(pid,))
        with self.assertRaisesRegex(psycopg.Error,"another active project cycle"):
            submit(key,"novo ciclo",uuid.uuid4())
        self.assertEqual(counts(pid),(1,0))

    def test_audit_write_failure_rolls_back_manifest_task_and_run(self):
        key,pid=make_project()
        with psycopg.connect(DSN,autocommit=True) as conn:
            conn.execute("alter table public.factory_audit_events add constraint reject_reconciliation check (event_type<>'project.reconciliation.enqueued')")
        try:
            with self.assertRaises(psycopg.Error):
                submit(key,"atomic rollback",uuid.uuid4())
            self.assertEqual(counts(pid),(0,0))
            with psycopg.connect(DSN) as conn,conn.cursor() as cur:
                cur.execute("select manifest from public.factory_projects where id=%s",(pid,))
                self.assertEqual(cur.fetchone()[0],{})
        finally:
            with psycopg.connect(DSN,autocommit=True) as conn:
                conn.execute("alter table public.factory_audit_events drop constraint reject_reconciliation")

    def test_original_bootstrap_also_serializes(self):
        key,pid=make_project()
        barrier=Barrier(2)
        def worker():
            barrier.wait()
            return bootstrap(key)
        with ThreadPoolExecutor(max_workers=2) as executor:
            a,b=list(executor.map(lambda _:worker(),range(2)))
        self.assertEqual(a["run_id"],b["run_id"])
        self.assertEqual(sorted([a["created"],b["created"]]),[False,True])
        self.assertEqual(counts(pid),(1,1))

    def test_grants_server_only(self):
        with psycopg.connect(DSN) as conn,conn.cursor() as cur:
            cur.execute("select has_function_privilege('anon','public.factory_enqueue_project_continuation(text,text,uuid,integer)','EXECUTE'),has_function_privilege('authenticated','public.factory_enqueue_project_continuation(text,text,uuid,integer)','EXECUTE'),has_function_privilege('service_role','public.factory_enqueue_project_continuation(text,text,uuid,integer)','EXECUTE')")
            self.assertEqual(cur.fetchone(),(False,False,True))


    def test_github_owner_start_writes_atomic_true_provenance_not_console(self):
        import hashlib
        from uuid import UUID
        def request_uuid(issue_number, comment_id):
            digest=hashlib.md5(
                f"factory-owner-start-v1:{issue_number}:{comment_id}".encode("ascii")
            ).hexdigest()
            return str(UUID(hex=digest))
        key,pid=make_owner_project()
        receipt=owner_submit(key,"Corrigir issue #24 no CRM",124456)
        self.assertTrue(receipt["created"])
        self.assertEqual(receipt["source"],"github-owner")
        self.assertEqual(receipt["request_id"],request_uuid(1055,124456))
        self.assertEqual(receipt["generation"],6)
        self.assertEqual(counts(pid),(1,2))
        with psycopg.connect(DSN) as conn,conn.cursor() as cur:
            cur.execute(
                "select metadata from public.factory_runs where id=%s",
                (receipt["run_id"],),
            )
            metadata=cur.fetchone()[0]
            self.assertEqual(metadata["source"],"github-owner")
            self.assertEqual(metadata["execution_generation"],6)
            origin=metadata["continuation_request"]["github"]
            self.assertEqual(origin["comment_id"],124456)
            self.assertEqual(origin["actor_id"],256917842)
            self.assertEqual(origin["issue_number"],1055)
            cur.execute(
                "select actor_type,actor_ref,event_type,payload "
                "from public.factory_audit_events where project_id=%s order by id",
                (pid,),
            )
            events=cur.fetchall()
            self.assertEqual([(e[0],e[1],e[2]) for e in events],[
                ("human","github-owner","project.continuation.requested"),
                ("system","github-owner","project.reconciliation.enqueued"),
            ])
            self.assertEqual(events[0][3]["github"],origin)
            cur.execute(
                "select estimated_cost from public.factory_tool_usage where run_id=%s",
                (receipt["run_id"],),
            )
            self.assertEqual(float(cur.fetchone()[0]),0)
            cur.execute("select manifest from public.factory_projects where id=%s",(pid,))
            self.assertEqual(cur.fetchone()[0]["continuation_request"]["source"],"github-owner")

    def test_owner_event_replay_is_idempotent_even_after_pause_or_completion(self):
        key,pid=make_owner_project()
        barrier=Barrier(2)
        def worker():
            barrier.wait()
            return owner_submit(key,"Reconciliar issue #24",9988722)
        with ThreadPoolExecutor(max_workers=2) as executor:
            a,b=list(executor.map(lambda _:worker(),range(2)))
        self.assertEqual(a["run_id"],b["run_id"])
        self.assertEqual(sorted([a["created"],b["created"]]),[False,True])
        with psycopg.connect(DSN) as conn,conn.cursor() as cur:
            cur.execute("update public.factory_project_execution_controls set state='paused' where project_id=%s",(pid,))
            cur.execute("update public.factory_tasks set status='completed' where project_id=%s",(pid,))
        self.assertFalse(owner_submit(key,"Reconciliar issue #24",9988722)["created"])
        self.assertEqual(counts(pid),(1,2))
        with self.assertRaisesRegex(psycopg.Error,"replay mismatch"):
            owner_submit(key,"Alterado via comentario editado",9988722)

    def test_simultaneous_distinct_owner_commands_cannot_admit_two_cycles(self):
        key,pid=make_owner_project()
        barrier=Barrier(2)
        def worker(i):
            barrier.wait()
            try:return owner_submit(key,f"pedido owner {i}",50000+i)
            except psycopg.Error as e:return str(e)
        with ThreadPoolExecutor(max_workers=2) as pool:
            a,b=list(pool.map(worker,[1,2]))
        self.assertEqual(sum(isinstance(x,dict) for x in (a,b)),1)
        self.assertEqual(sum("another active project cycle exists" in x
                             for x in (a,b) if isinstance(x,str)),1)
        self.assertEqual(counts(pid),(1,2))

    def test_owner_start_rejects_invalid_actors_projects_and_paused_state(self):
        cases=[
            dict(issue=1056),dict(actor_id=123),dict(actor_login="attacker"),
        ]
        for arguments in cases:
            key,pid=make_owner_project()
            with self.assertRaisesRegex(psycopg.Error,"invalid GitHub owner continuation"):
                owner_submit(key,"real request",4444,**arguments)
            self.assertEqual(counts(pid),(0,0))
        for kind,state in (("greenfield","running"),("existing","paused"),
                           ("existing","stopped"),("existing","draft")):
            key,pid=make_owner_project(project_kind=kind,state=state)
            with self.assertRaises(psycopg.Error):
                owner_submit(key,"new scope",3344)
            self.assertEqual(counts(pid),(0,0))

    def test_owner_start_respects_console_cycle_and_historical_orphan(self):
        key,pid=make_owner_project()
        old=submit(key,"console already active",uuid.uuid4())
        self.assertTrue(old["created"])
        with self.assertRaisesRegex(psycopg.Error,"another active project cycle exists"):
            owner_submit(key,"same project different channel",445522)
        self.assertEqual(counts(pid),(1,2))
        key,pid=make_owner_project()
        with psycopg.connect(DSN) as conn,conn.cursor() as cur:
            cur.execute("insert into public.factory_tasks(project_id,title,status) values (%s,'legacy root','completed') returning id",(pid,))
            parent=cur.fetchone()[0]
            cur.execute("insert into public.factory_tasks(project_id,parent_task_id,title,status) values (%s,%s,'old child','queued')",(pid,parent))
        self.assertTrue(owner_submit(key,"a new real scoped request",446699)["created"])
        self.assertEqual(counts(pid),(3,2))

    def test_owner_start_rollback_if_audit_fails(self):
        key,pid=make_owner_project()
        with psycopg.connect(DSN,autocommit=True) as conn:
            conn.execute(
                "alter table public.factory_audit_events add constraint "
                "reject_owner_audit check (actor_ref<>'github-owner') NOT VALID"
            )
        try:
            with self.assertRaises(psycopg.Error):
                owner_submit(key,"atomic github owner start",88899)
            self.assertEqual(counts(pid),(0,0))
            with psycopg.connect(DSN) as conn,conn.cursor() as cur:
                cur.execute("select manifest from public.factory_projects where id=%s",(pid,))
                self.assertEqual(cur.fetchone()[0],{})
        finally:
            with psycopg.connect(DSN,autocommit=True) as conn:
                conn.execute("alter table public.factory_audit_events drop constraint reject_owner_audit")

    def test_new_owner_rpc_is_security_invoker_and_only_service_role(self):
        signature=(
            "public.factory_enqueue_github_owner_continuation_v1"
            "(text,text,bigint,integer,bigint,text)"
        )
        with psycopg.connect(DSN) as conn,conn.cursor() as cur:
            cur.execute(
                "select has_function_privilege('anon',%s,'EXECUTE'),"
                "has_function_privilege('authenticated',%s,'EXECUTE'),"
                "has_function_privilege('service_role',%s,'EXECUTE')",
                (signature,signature,signature),
            )
            self.assertEqual(cur.fetchone(),(False,False,True))
            cur.execute("select prosecdef from pg_proc where oid=%s::regprocedure",(signature,))
            self.assertFalse(cur.fetchone()[0])


    def test_resume_real_checkpoint_runs_only_planning_without_repeating_paid_stages(self):
        x=make_paid_checkpoint()
        res=resume_planning(x["run_id"])
        self.assertTrue(res["created"])
        self.assertEqual(res["source_run_id"],str(x["run_id"]))
        self.assertEqual(res["stages"],["planning"])
        self.assertEqual(res["generation"],6)
        self.assertNotEqual(res["run_id"],str(x["run_id"]))
        with psycopg.connect(DSN) as conn,conn.cursor() as cur:
            cur.execute("select status,metadata from public.factory_runs where id=%s",(res["run_id"],))
            status,md=cur.fetchone()
            self.assertEqual(status,"queued")
            self.assertEqual(md["stages"],["planning"])
            self.assertNotIn("reconciliation",md["stages"])
            self.assertNotIn("gap_analysis",md["stages"])
            self.assertNotIn("error",md)
            self.assertEqual(md["execution_generation"],6)
            self.assertNotIn("retry_of",md)
            cp=md["resume_checkpoint"]
            self.assertEqual(cp["source_run_id"],str(x["run_id"]))
            self.assertEqual(cp["snapshot_id"],str(x["snapshot_id"]))
            self.assertEqual(cp["gap_analysis"],x["gap"])
            self.assertEqual(cp["reconciliation"]["summary"],"Live candidate inspected")
            self.assertEqual(cp["reconciliation"]["evidence"],[{"sha":"a"*40}])
            cur.execute("select status from public.factory_tasks where id=%s",(x["task_id"],))
            self.assertEqual(cur.fetchone()[0],"queued")
            cur.execute("select status from public.factory_runs where id=%s",(x["run_id"],))
            self.assertEqual(cur.fetchone()[0],"failed")
            cur.execute("select event_type,payload from public.factory_audit_events where run_id=%s",(res["run_id"],))
            rows=cur.fetchall()
            self.assertEqual([z[0] for z in rows],[
                "product.planning.resume.requested","product.planning.resume_queued",
            ])
            self.assertEqual(rows[0][1]["source_run_id"],str(x["run_id"]))
            self.assertEqual(rows[0][1]["comment_id"],778872)
            self.assertEqual(rows[1][1]["paid_calls"],0)
            cur.execute("select count(*) from public.factory_tool_usage where run_id=%s",(res["run_id"],))
            self.assertEqual(cur.fetchone()[0],0)

    def test_resume_concurrent_requests_are_idempotent(self):
        x=make_paid_checkpoint()
        barrier=Barrier(2)
        def worker():
            barrier.wait()
            return resume_planning(x["run_id"])
        with ThreadPoolExecutor(max_workers=2) as pool:
            first,second=list(pool.map(lambda _:worker(),range(2)))
        self.assertEqual(first["run_id"],second["run_id"])
        self.assertEqual(sorted([first["created"],second["created"]]),[False,True])
        with psycopg.connect(DSN) as conn,conn.cursor() as cur:
            cur.execute("select count(*) from public.factory_runs where task_id=%s",(x["task_id"],))
            self.assertEqual(cur.fetchone()[0],2)
            cur.execute("select count(*) from public.factory_audit_events where run_id=%s",(first["run_id"],))
            self.assertEqual(cur.fetchone()[0],2)

    def test_resume_rejects_wrong_source_generation_and_project_control(self):
        for state,generation in (("paused",6),("stopped",6),("running",7)):
            x=make_paid_checkpoint()
            with psycopg.connect(DSN) as conn:
                conn.execute(
                    "update public.factory_project_execution_controls set "
                    "state=%s,generation=%s where project_id=%s",
                    (state,generation,x["project_id"]),
                )
            with self.subTest(state=state,generation=generation):
                with self.assertRaises(psycopg.Error):
                    resume_planning(x["run_id"])

    def test_resume_rejects_non_budget_failure(self):
        x=make_paid_checkpoint(fail_reason="provider responded with invalid JSON")
        with self.assertRaisesRegex(psycopg.Error,"source is not eligible"):
            resume_planning(x["run_id"])

    def test_resume_rejects_missing_snapshot_and_tampered_stage_audit(self):
        for change in ("snapshot","stage","source_run","unrelated_write"):
            x=make_paid_checkpoint()
            with psycopg.connect(DSN) as conn,conn.cursor() as cur:
                if change=="snapshot":
                    cur.execute("delete from public.factory_project_state_snapshots where id=%s",(x["snapshot_id"],))
                elif change=="stage":
                    cur.execute("delete from public.factory_audit_events "
                                "where run_id=%s and event_type='product.stage.persisted' "
                                "and payload->>'stage'='gap_analysis'",(x["run_id"],))
                elif change=="source_run":
                    cur.execute("update public.factory_runs set metadata="
                                "jsonb_set(metadata,'{execution_generation}','4'::jsonb)"
                                "where id=%s",(x["run_id"],))
                else:
                    cur.execute("insert into public.factory_audit_events("
                                "project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)"
                                "values(%s,%s,%s,'system','runtime-worker','product.stage.persisted',%s)",
                                (x["project_id"],x["task_id"],x["run_id"],
                                 Jsonb({"stage":"gap_analysis","snapshot_id":None})))
            with self.subTest(change=change):
                with self.assertRaises(psycopg.Error):
                    resume_planning(x["run_id"])
            with psycopg.connect(DSN) as conn,conn.cursor() as cur:
                cur.execute("select count(*) from public.factory_runs where task_id=%s",(x["task_id"],))
                self.assertEqual(cur.fetchone()[0],1)

    def test_resume_rejects_live_other_root_cycle(self):
        x=make_paid_checkpoint()
        with psycopg.connect(DSN) as conn,conn.cursor() as cur:
            cur.execute(
                "insert into public.factory_tasks(project_id,title,status)"
                "values(%s,'other active root','queued')",
                (x["project_id"],),
            )
        with self.assertRaisesRegex(psycopg.Error,"another current cycle"):
            resume_planning(x["run_id"])

    def test_resume_failure_on_audit_insert_rolls_back_task_and_run(self):
        x=make_paid_checkpoint()
        with psycopg.connect(DSN,autocommit=True) as conn:
            conn.execute(
                "alter table public.factory_audit_events add constraint "
                "deny_planning_resume check (event_type<>'product.planning.resume_queued') NOT VALID"
            )
        try:
            with self.assertRaises(psycopg.Error):
                resume_planning(x["run_id"])
            with psycopg.connect(DSN) as conn,conn.cursor() as cur:
                cur.execute("select status from public.factory_tasks where id=%s",(x["task_id"],))
                self.assertEqual(cur.fetchone()[0],"failed")
                cur.execute("select count(*) from public.factory_runs where task_id=%s",(x["task_id"],))
                self.assertEqual(cur.fetchone()[0],1)
        finally:
            with psycopg.connect(DSN,autocommit=True) as conn:
                conn.execute("alter table public.factory_audit_events drop constraint deny_planning_resume")


    def test_resume_denies_wrong_owner_and_wrong_issue(self):
        x=make_paid_checkpoint()
        for params in ({"actor_id":7},{"issue":713},{"actor_login":"attacker"},{"comment_id":0}):
            with self.subTest(params=params):
                with self.assertRaisesRegex(psycopg.Error,"invalid GitHub owner resume authority"):
                    resume_planning(x["run_id"],**params)
        with psycopg.connect(DSN) as conn,conn.cursor() as cur:
            cur.execute("select count(*) from factory_runs where task_id=%s",(x["task_id"],))
            self.assertEqual(cur.fetchone()[0],1)

    def test_resume_rpc_invoker_and_service_role_only(self):
        signature="public.factory_resume_failed_product_planning_v1(uuid,bigint,integer,bigint,text)"
        with psycopg.connect(DSN) as conn,conn.cursor() as cur:
            cur.execute(
                "select has_function_privilege('anon',%s,'EXECUTE'),"
                "has_function_privilege('authenticated',%s,'EXECUTE'),"
                "has_function_privilege('service_role',%s,'EXECUTE')",
                (signature,signature,signature),
            )
            self.assertEqual(cur.fetchone(),(False,False,True))
            cur.execute("select prosecdef from pg_proc where oid=%s::regprocedure",(signature,))
            self.assertFalse(cur.fetchone()[0])


if __name__=="__main__":
    require_isolated()
    unittest.main()
