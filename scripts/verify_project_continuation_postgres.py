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
CREATE TABLE public.factory_tasks (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), project_id uuid NOT NULL REFERENCES public.factory_projects(id),
 parent_task_id uuid REFERENCES public.factory_tasks(id), external_key text,
 title text NOT NULL, description text, status text NOT NULL DEFAULT 'queued',
 complexity text NOT NULL DEFAULT 'medium', risk jsonb NOT NULL DEFAULT '{}'::jsonb,
 acceptance_criteria jsonb NOT NULL DEFAULT '[]'::jsonb, depends_on jsonb NOT NULL DEFAULT '[]'::jsonb,
 created_at timestamptz NOT NULL DEFAULT now()
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

if __name__=="__main__":
    require_isolated()
    unittest.main()
