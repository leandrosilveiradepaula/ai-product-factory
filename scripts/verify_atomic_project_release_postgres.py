#!/usr/bin/env python3
"""Isolated PostgreSQL 16 acceptance of observed human release reconciliation.

Never connects to production, calls a paid model, opens a PR or merges one.
Both the real migration and real PostgreSQL constraints execute against a
disposable loopback-only database provisioned by GitHub Actions.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict

DSN=os.environ.get("FACTORY_RELEASE_ATOMIC_TEST_DSN", "")
info=conninfo_to_dict(DSN)
if (os.environ.get("FACTORY_RELEASE_ATOMIC_TEST_ISOLATED")!="true"
    or info.get("host") not in ("127.0.0.1","localhost")
    or info.get("dbname")!="factory_release_atomic_test"):
    raise SystemExit("REFUSING_NON_ISOLATED_RELEASE_ATOMIC_DATABASE")

MIGRATION=(Path(__file__).resolve().parents[1]/
    "supabase/migrations/20261021090000_atomic_release_state_and_replay_outbox.sql").read_text()

ORIG="a"*40
MERGE="b"*40
MERGE2="c"*40
DOMAINS=(
    "security","observability_operations","test_strategy",
    "product_experience","documentation","functional_completeness",
)
SCHEMA="""
CREATE TABLE public.factory_projects(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 project_key text NOT NULL UNIQUE,
 name text NOT NULL DEFAULT 'Synthetic product',
 repository text NOT NULL DEFAULT 'owner/example',
 project_kind text NOT NULL DEFAULT 'greenfield',
 lifecycle_stage text NOT NULL DEFAULT 'implementation',
 manifest jsonb NOT NULL DEFAULT '{}'::jsonb,
 is_active boolean NOT NULL DEFAULT true,
 updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE public.factory_tasks(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 project_id uuid NOT NULL REFERENCES public.factory_projects(id),
 status text NOT NULL DEFAULT 'completed');
CREATE TABLE public.factory_runs(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 task_id uuid NOT NULL REFERENCES public.factory_tasks(id),
 status text NOT NULL,
 candidate_commit text,
 metadata jsonb NOT NULL DEFAULT '{}'::jsonb);
CREATE TABLE public.factory_release_reports(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 project_id uuid NOT NULL REFERENCES public.factory_projects(id),
 run_id uuid NOT NULL UNIQUE REFERENCES public.factory_runs(id),
 candidate_commit text NOT NULL,
 status text NOT NULL,
 report jsonb NOT NULL,
 rollback jsonb NOT NULL DEFAULT '{}'::jsonb,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE public.factory_project_state_snapshots(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 project_id uuid NOT NULL REFERENCES public.factory_projects(id),
 run_id uuid REFERENCES public.factory_runs(id),
 observed_stage text, summary text NOT NULL,
 evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
 gaps jsonb NOT NULL DEFAULT '[]'::jsonb,
 constraints jsonb NOT NULL DEFAULT '[]'::jsonb,
 source_status jsonb NOT NULL DEFAULT '{}'::jsonb,
 created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE public.factory_audit_events(
 id bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
 project_id uuid REFERENCES public.factory_projects(id),
 task_id uuid REFERENCES public.factory_tasks(id),
 run_id uuid REFERENCES public.factory_runs(id),
 actor_type text NOT NULL,
 actor_ref text,
 event_type text NOT NULL,
 payload jsonb NOT NULL DEFAULT '{}'::jsonb,
 created_at timestamptz NOT NULL DEFAULT now());
"""

with psycopg.connect(DSN,autocommit=True) as conn:
    for role in ("anon","authenticated","service_role"):
        conn.execute("CREATE ROLE "+role+" NOLOGIN")
    conn.execute(SCHEMA)
    conn.execute(MIGRATION)

    def one(sql,args=()):
        return conn.execute(sql,args).fetchone()[0]

    def count(table,where="",args=()):
        assert table in ("factory_project_state_snapshots","factory_audit_events",
                         "factory_release_reports")
        return one("SELECT count(*) FROM public."+table+(" WHERE "+where if where else ""),args)

    def project(key,kind="greenfield",manifest=None):
        return one(
            "INSERT INTO public.factory_projects(project_key,project_kind,manifest) "
            "VALUES (%s,%s,%s::jsonb) RETURNING id",
            (key,kind,json.dumps(manifest or {"preserve":"true",
                                              "autonomy":"read_only_verification",
                                              "current_task":"temporary",
                                              "runtime_readiness":{"current_scope":"read_only_verification","preview":"verified"}})),
        )

    def released_candidate(project_id,merge_sha=MERGE):
        tid=one("INSERT INTO public.factory_tasks(project_id) VALUES (%s) RETURNING id",(project_id,))
        rid=one("INSERT INTO public.factory_runs(task_id,status,candidate_commit) "
                "VALUES (%s,'merged',%s) RETURNING id",(tid,merge_sha))
        report={"product_readiness":{"status":"not_assessed","ready":False},
                "required_approvals":["human"],"customer_visible":False}
        rep=one("INSERT INTO public.factory_release_reports"
                "(project_id,run_id,candidate_commit,status,report)"
                " VALUES (%s,%s,%s,'ready_for_human_release',%s::jsonb)"
                " RETURNING id",(project_id,rid,ORIG,json.dumps(report)))
        return rid,rep

    def human_receipt(project_id,rid,merge_sha=MERGE):
        conn.execute("INSERT INTO public.factory_audit_events"
                     "(project_id,run_id,actor_type,actor_ref,event_type,payload)"
                     "VALUES (%s,%s,'system','github-observer','release.human_merge_observed',"
                     "%s::jsonb)",
                     (project_id,rid,json.dumps({"merge_sha":merge_sha,"automatic_merge":False})))

    def mark(rid,sha=MERGE):
        return one("SELECT public.factory_mark_release_report_released(%s,%s)",(rid,sha))

    def rows_after(after=0):
        return one("SELECT public.factory_pending_release_reconciliations_v1(%s,16)",(after,))

    def followup(rid,sha=MERGE):
        return {"scope":"current_product_after_release","status":"not_assessed",
                "ready":False,"reason_code":"global_readiness_not_assessed",
                "next_step":"global_product_readiness_audit",
                "release_run_id":str(rid),"merge_sha":sha,
                "report_verified":True,"pending_domains":list(DOMAINS),
                "candidate_assessed_domains":[]}

    def current_report(rid):
        return one("SELECT report FROM public.factory_release_reports WHERE run_id=%s",(rid,))

    def reconcile(pid,rid,sha=MERGE,report_override=None,followup_override=None):
        return one("SELECT public.factory_reconcile_observed_release_v1"
                   "(%s,%s,%s,%s::jsonb,%s::jsonb)",
                   (pid,rid,sha,
                    json.dumps(report_override if report_override is not None else current_report(rid)),
                    json.dumps(followup_override if followup_override is not None else followup(rid,sha))))

    def rejected(action,states=("PT409",)):
        try:
            action()
            raise AssertionError("an unauthorized or inconsistent release succeeded")
        except psycopg.Error as exc:
            assert exc.sqlstate in states,(exc.sqlstate,str(exc))

    # SECURITY INVOKER and exact service-role ACLs, including PUBLIC inheritance.
    signatures=(
      "factory_mark_release_report_released(uuid,text)",
      "factory_pending_release_reconciliations_v1(bigint,integer)",
      "factory_reconcile_observed_release_v1(uuid,uuid,text,jsonb,jsonb)",
      "factory_defer_release_reconciliation_v1(bigint)",
    )
    for signature in signatures:
        qualified="public."+signature
        acl=conn.execute(
            "SELECT NOT p.prosecdef,has_function_privilege('anon',p.oid,'EXECUTE'),"
            "has_function_privilege('authenticated',p.oid,'EXECUTE'),"
            "has_function_privilege('service_role',p.oid,'EXECUTE') "
            "FROM pg_proc p WHERE p.oid=%s::regprocedure",(qualified,)).fetchone()
        assert acl==(True,False,False,True),(signature,acl)

    # An accidental PR merge without an operator witness may not grant release.
    green=project("greenfield-with-observed-human-merge")
    rid,_=released_candidate(green)
    rejected(lambda: mark(rid))
    rejected(lambda: mark(rid,"f"*40))
    assert count("factory_audit_events","event_type='release.reconciliation_requested'")==0
    assert rows_after()==[]
    human_receipt(green,rid)
    marked=mark(rid)
    assert marked["status"]=="released" and not marked["idempotent"],marked
    assert mark(rid)["idempotent"]
    assert count("factory_audit_events","event_type='release.reconciliation_requested'")==1
    pending=rows_after()
    assert len(pending)==1 and pending[0]["run_id"]==str(rid)
    assert pending[0]["project_id"]==str(green)
    assert pending[0]["merge_sha"]==MERGE
    assert type(pending[0]["event_id"]) is int
    assert rows_after(pending[0]["event_id"])==[]

    # A bogus report, forged domains or release identity cannot promote.
    rejected(lambda: reconcile(green,rid,report_override={"merge_sha":MERGE}))
    rejected(lambda: reconcile(green,rid,"e"*40))
    corrupt=followup(rid)
    corrupt["ready"]=True
    rejected(lambda: reconcile(green,rid,followup_override=corrupt))
    corrupt=followup(rid)
    corrupt["pending_domains"]=["security","security"]
    rejected(lambda: reconcile(green,rid,followup_override=corrupt))
    assert one("SELECT lifecycle_stage FROM public.factory_projects WHERE id=%s",(green,))=="implementation"
    assert count("factory_project_state_snapshots")==0

    # The same SQL transaction writes project, exactly six gaps and ONE audit.
    result=reconcile(green,rid)
    assert result["lifecycle_stage"]=="operations" and not result["idempotent"],result
    assert result["pending_domains"]==6 and not result["product_ready"],result
    new=one("SELECT manifest FROM public.factory_projects WHERE id=%s",(green,))
    assert new["preserve"]=="true" and new["head_sha"]==MERGE
    assert new["reported_stage"]=="operations"
    assert new["last_release"]["run_id"]==str(rid)
    assert new["product_readiness_followup"]["pending_domains"]==list(DOMAINS)
    assert new["product_readiness_followup"]["ready"] is False
    assert "autonomy" not in new and "current_task" not in new
    assert "current_scope" not in new["runtime_readiness"]
    assert new["runtime_readiness"]["preview"]=="verified"
    snap=one("SELECT gaps FROM public.factory_project_state_snapshots WHERE run_id=%s",(rid,))
    assert [x["domain"] for x in snap]==list(DOMAINS),snap
    assert all(x["kind"]=="global_readiness_evidence_required" for x in snap)
    assert count("factory_project_state_snapshots","run_id=%s",(rid,))==1
    assert count("factory_audit_events","run_id=%s AND event_type='project.state.reconciled_after_release'",(rid,))==1
    assert rows_after()==[]
    assert reconcile(green,rid)["idempotent"] is True
    assert count("factory_project_state_snapshots","run_id=%s",(rid,))==1

    # Delivery for a wholly separate existing product is not mixed into green.
    existing=project("existing-with-release","existing")
    existing_run,_=released_candidate(existing)
    human_receipt(existing,existing_run)
    mark(existing_run)
    assert [row["run_id"] for row in rows_after()]==[str(existing_run)]
    assert reconcile(existing,existing_run)["pending_domains"]==6
    assert one("SELECT manifest->'last_release'->>'run_id' FROM public.factory_projects WHERE id=%s",
               (green,))==str(rid)

    # Simulate an unexpected snapshot database failure *after* computing the
    # project update. A single transaction rolls the project/audit back too.
    broken=project("snapshot-failure-does-not-promote")
    broken_run,_=released_candidate(broken)
    human_receipt(broken,broken_run)
    mark(broken_run)
    conn.execute("""
    CREATE OR REPLACE FUNCTION public.fixture_reject_snapshot()
    RETURNS trigger LANGUAGE plpgsql AS $fixture$
    BEGIN
      IF NEW.project_id::text=current_setting('fixture.bad_project',true) THEN
        RAISE EXCEPTION 'synthetic snapshot persistence failure'
          USING errcode='PT409';
      END IF;
      RETURN NEW;
    END
    $fixture$;
    CREATE TRIGGER fixture_snapshot_fails BEFORE INSERT
      ON public.factory_project_state_snapshots FOR EACH ROW
      EXECUTE FUNCTION public.fixture_reject_snapshot();
    """)
    conn.execute("SELECT set_config('fixture.bad_project',%s,false)",(str(broken),))
    rejected(lambda: reconcile(broken,broken_run))
    assert one("SELECT lifecycle_stage FROM public.factory_projects WHERE id=%s",(broken,))=="implementation"
    assert one("SELECT manifest->>'last_release' FROM public.factory_projects WHERE id=%s",(broken,)) is None
    assert count("factory_project_state_snapshots","run_id=%s",(broken_run,))==0
    assert count("factory_audit_events",
                 "run_id=%s AND event_type='project.state.reconciled_after_release'",(broken_run,))==0
    assert [row["run_id"] for row in rows_after()]==[str(broken_run)]
    conn.execute("DROP TRIGGER fixture_snapshot_fails ON public.factory_project_state_snapshots")
    assert reconcile(broken,broken_run)["pending_domains"]==6
    assert rows_after()==[]
    assert reconcile(broken,broken_run)["idempotent"] is True

    # Do not let a superseded but previously valid release overwrite a newer
    # observed release, even when the old outbox marker is still outstanding.
    reorder=project("out-of-order-release-protection")
    old_run,_=released_candidate(reorder)
    human_receipt(reorder,old_run)
    mark(old_run)
    conn.execute("UPDATE public.factory_release_reports SET updated_at=now()-interval '1 day' WHERE run_id=%s",(old_run,))
    new_run,_=released_candidate(reorder,MERGE2)
    human_receipt(reorder,new_run,MERGE2)
    mark(new_run,MERGE2)
    rejected(lambda: reconcile(reorder,old_run))
    assert reconcile(reorder,new_run,MERGE2)["pending_domains"]==6
    assert one("SELECT manifest->'last_release'->>'run_id' FROM public.factory_projects WHERE id=%s",
               (reorder,))==str(new_run)
    outstanding=rows_after()
    assert len(outstanding)==1 and outstanding[0]["run_id"]==str(old_run)
    assert count("factory_audit_events","run_id=%s AND event_type='release.reconciliation_requested'",(old_run,))==1
    marker=outstanding[0]["event_id"]
    parked=one("SELECT public.factory_defer_release_reconciliation_v1(%s)",(marker,))
    assert parked["status"]=="needs_review" and not parked["idempotent"]
    assert one("SELECT public.factory_defer_release_reconciliation_v1(%s)",(marker,))["idempotent"]
    assert rows_after()==[]
    assert count("factory_audit_events","run_id=%s AND event_type='release.reconciliation_needs_review'",(old_run,))==1
    rejected(lambda: one("SELECT public.factory_defer_release_reconciliation_v1(%s)",(marker+1000000,)))


print("FACTORY_ATOMIC_RELEASE_POSTGRES_PASS=1")
