#!/usr/bin/env python3
"""Disposable PostgreSQL test for operator-controlled recovery and resumption.

The test rejects any non-local/non-test DSN. It performs no API calls, no
external actions and no production mutations; test data are synthetic.
"""
import os
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict

dsn = os.environ.get("FACTORY_RECOVERY_CONTROL_TEST_DSN", "")
config = conninfo_to_dict(dsn)
if (
    os.environ.get("FACTORY_RECOVERY_CONTROL_TEST_ISOLATED") != "true"
    or config.get("host") not in ("127.0.0.1", "localhost")
    or config.get("dbname") != "factory_recovery_control_test"
):
    raise SystemExit("REFUSING_NON_ISOLATED_RECOVERY_TEST_DATABASE")

root = Path(__file__).resolve().parents[1]
migration = (root / "supabase/migrations/20261020194500_fence_recovery_manual_project_control.sql").read_text()
schema = """
CREATE TABLE public.factory_projects(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),project_key text NOT NULL UNIQUE,
 is_active bool NOT NULL DEFAULT true);
CREATE TABLE public.factory_project_execution_controls(
 project_id uuid PRIMARY KEY REFERENCES public.factory_projects(id),
 state text NOT NULL,generation int NOT NULL);
CREATE TABLE public.factory_tasks(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 project_id uuid NOT NULL REFERENCES public.factory_projects(id),
 parent_task_id uuid,external_key text,title text NOT NULL DEFAULT 'test',
 description text DEFAULT '',status text NOT NULL,
 complexity text DEFAULT 'medium',risk jsonb DEFAULT '{}'::jsonb,
 acceptance_criteria jsonb DEFAULT '[]'::jsonb,
 depends_on jsonb DEFAULT '[]'::jsonb,
 required_capabilities jsonb DEFAULT '[]'::jsonb,
 scope_keys jsonb DEFAULT '[]'::jsonb,
 updated_at timestamptz DEFAULT now(),created_at timestamptz DEFAULT now());
CREATE TABLE public.factory_runs(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),task_id uuid REFERENCES public.factory_tasks(id),
 status text NOT NULL,execution_route text,metadata jsonb DEFAULT '{}'::jsonb,
 attempt_count int DEFAULT 0,lease_owner text,
 lease_expires_at timestamptz,created_at timestamptz DEFAULT now(),
 finished_at timestamptz,source_commit text,candidate_commit text,
 branch_name text,last_error text);
CREATE TABLE public.factory_change_sets(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),project_id uuid REFERENCES public.factory_projects(id),
 status text NOT NULL,lease_owner text,lease_expires_at timestamptz,
 updated_at timestamptz DEFAULT now(),attempt_count int DEFAULT 0,
 metadata jsonb DEFAULT '{}'::jsonb);
CREATE TABLE public.factory_change_set_work_units(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),task_id uuid REFERENCES public.factory_tasks(id),
 run_id uuid REFERENCES public.factory_runs(id),
 change_set_id uuid REFERENCES public.factory_change_sets(id),
 status text NOT NULL,updated_at timestamptz DEFAULT now());
CREATE TABLE public.factory_specialist_lane_jobs(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 project_id uuid REFERENCES public.factory_projects(id),
 run_id uuid REFERENCES public.factory_runs(id),
 status text NOT NULL,lease_owner text,
 lease_expires_at timestamptz,attempt_count int DEFAULT 0,
 completed_at timestamptz,updated_at timestamptz DEFAULT now(),
 required boolean NOT NULL DEFAULT true,
 findings jsonb NOT NULL DEFAULT '[]'::jsonb);
CREATE TABLE public.factory_audit_events(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 project_id uuid,task_id uuid,run_id uuid,actor_type text,
 actor_ref text,event_type text,payload jsonb);
"""

with psycopg.connect(dsn, autocommit=True) as conn:
    conn.execute(schema)
    conn.execute(migration)
    def single(sql, args=()):
        return conn.execute(sql, args).fetchone()[0]
    def project(key, state, generation=1):
        pid = single("INSERT INTO public.factory_projects(project_key) VALUES (%s) RETURNING id", (key,))
        conn.execute("INSERT INTO public.factory_project_execution_controls VALUES (%s,%s,%s)",(pid,state,generation))
        return pid
    def task(project_id, status):
        return single("INSERT INTO public.factory_tasks(project_id,status) VALUES (%s,%s) RETURNING id",(project_id,status))
    def run(task_id, status, *, expired=False, metadata=None, attempts=0):
        return single(
            """INSERT INTO public.factory_runs(task_id,status,attempt_count,lease_expires_at,metadata)
               VALUES (%s,%s,%s,CASE WHEN %s THEN now()-interval '3 hours' ELSE NULL END,%s::jsonb)
               RETURNING id""",
            (task_id,status,attempts,expired,metadata or "{}"),
        )
    paused=project("project-paused","paused")
    running=project("project-running","running")
    stopped=project("project-stopped","stopped")
    for key in (paused,stopped):
        try:
            conn.execute("SELECT public.factory_assert_project_running(%s)",(key,))
            raise AssertionError("inactive state authorized by project assertion")
        except psycopg.Error as e:
            assert e.sqlstate=="PT409",(e.sqlstate,str(e))
    conn.execute("SELECT public.factory_assert_project_running(%s)",(running,))

    # Expired run recovery must NEVER requeue or terminal-fail a paused run.
    tp=task(paused,"implementing")
    tr=task(running,"implementing")
    rp=run(tp,"implementing",expired=True)
    rr=run(tr,"implementing",expired=True)
    output=single("SELECT public.factory_recover_expired_runs(3)")
    assert output["requeued"]==1 and output["failed"]==0,output
    assert single("SELECT status FROM public.factory_runs WHERE id=%s",(rp,))=="implementing"
    assert single("SELECT status FROM public.factory_runs WHERE id=%s",(rr,))=="queued"

    # Bulk Change Set recovery fences both queued work units and integrators.
    paused_cs=single("INSERT INTO public.factory_change_sets(project_id,status,lease_expires_at) VALUES (%s,'integrating',now()-interval '3 hours') RETURNING id",(paused,))
    running_cs=single("INSERT INTO public.factory_change_sets(project_id,status,lease_expires_at) VALUES (%s,'integrating',now()-interval '3 hours') RETURNING id",(running,))
    conn.execute("UPDATE public.factory_runs SET status='queued' WHERE id=%s",(rp,))  # isolated fixture
    up=single("INSERT INTO public.factory_change_set_work_units(task_id,run_id,change_set_id,status) VALUES (%s,%s,%s,'running') RETURNING id",(tp,rp,paused_cs))
    ur=single("INSERT INTO public.factory_change_set_work_units(task_id,run_id,change_set_id,status) VALUES (%s,%s,%s,'running') RETURNING id",(tr,rr,running_cs))
    changes=single("SELECT public.factory_recover_change_sets(3)")
    assert changes["work_units_requeued"]==1 and changes["integrations_requeued"]==1,changes
    assert single("SELECT status FROM public.factory_change_set_work_units WHERE id=%s",(up,))=="running"
    assert single("SELECT status FROM public.factory_change_set_work_units WHERE id=%s",(ur,))=="queued"
    assert single("SELECT status FROM public.factory_change_sets WHERE id=%s",(paused_cs,))=="integrating"
    assert single("SELECT status FROM public.factory_change_sets WHERE id=%s",(running_cs,))=="building"

    # Specialist lease recovery cannot revive paused lanes.
    jp=single("""INSERT INTO public.factory_specialist_lane_jobs(project_id,run_id,status,lease_expires_at)
                 VALUES (%s,%s,'claimed',now()-interval '3 hours') RETURNING id""",(paused,rp))
    jr=single("""INSERT INTO public.factory_specialist_lane_jobs(project_id,run_id,status,lease_expires_at)
                 VALUES (%s,%s,'claimed',now()-interval '3 hours') RETURNING id""",(running,rr))
    specialist=single("SELECT public.factory_recover_specialist_lanes(3)")
    assert specialist["requeued"]==1 and specialist["blocked"]==0,specialist
    assert single("SELECT status FROM public.factory_specialist_lane_jobs WHERE id=%s",(jp,))=="claimed"
    assert single("SELECT status FROM public.factory_specialist_lane_jobs WHERE id=%s",(jr,))=="queued"

    # Completed human decisions materialize only for running projects.
    valid='{"decision_only":true,"decision_outcome":"approved","resume_plan":{"external_key":"recovery-e2e","title":"Continue safely"}}'
    dp=run(task(paused,"completed"),"completed",metadata=valid)
    dr=run(task(running,"completed"),"completed",metadata=valid)
    decisions=single("SELECT public.factory_resume_resolved_decisions()")
    assert decisions["created"]==1 and decisions["blocked"]==0,decisions
    assert single("SELECT count(*) FROM public.factory_tasks WHERE project_id=%s AND external_key='recovery-e2e'",(paused,))==0
    assert single("SELECT count(*) FROM public.factory_tasks WHERE project_id=%s AND external_key='recovery-e2e'",(running,))==1
    assert single("SELECT metadata->>'resume_plan_status' FROM public.factory_runs WHERE id=%s",(dp,)) is None
    assert single("SELECT metadata->>'resume_plan_status' FROM public.factory_runs WHERE id=%s",(dr,))=="materialized"

    # Explicit retry must respect pause, and restore eligible work once running.
    fail_tp=task(paused,"failed")
    fail_tr=task(running,"failed")
    retry_paused=run(fail_tp,"failed")
    retry_running=run(fail_tr,"failed")
    try:
        conn.execute("SELECT public.factory_retry_failed_run(%s,'local test')",(retry_paused,))
        raise AssertionError("paused failed run retried without operator Start")
    except psycopg.Error as e:
        assert e.sqlstate=="PT409",(e.sqlstate,str(e))
    newrun=single("SELECT public.factory_retry_failed_run(%s,'local test')",(retry_running,))
    assert newrun["status"]=="queued"
    assert single("SELECT count(*) FROM public.factory_runs WHERE task_id=%s",(fail_tp,))==1
    assert single("SELECT count(*) FROM public.factory_runs WHERE task_id=%s",(fail_tr,))==2

    # A running row with zero generation or inactive project must be rejected.
    conn.execute("UPDATE public.factory_project_execution_controls SET generation=0 WHERE project_id=%s",(running,))
    try:
        conn.execute("SELECT public.factory_assert_project_running(%s)",(running,))
        raise AssertionError("generation zero admitted")
    except psycopg.Error as e:
        assert e.sqlstate=="PT409"
    conn.execute("UPDATE public.factory_project_execution_controls SET generation=2 WHERE project_id=%s",(running,))
    conn.execute("UPDATE public.factory_projects SET is_active=false WHERE id=%s",(running,))
    try:
        conn.execute("SELECT public.factory_assert_project_running(%s)",(running,))
        raise AssertionError("inactive project admitted")
    except psycopg.Error as e:
        assert e.sqlstate=="PT409"

print("RECOVERY_MANUAL_CONTROL_POSTGRES_PASS=1")
