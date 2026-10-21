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
terminal_migration = (root / "supabase/migrations/20261021014000_fence_terminal_descendant_recovery_manual_control.sql").read_text()
epoch_migration = (root / "supabase/migrations/20261021021000_quarantine_cross_epoch_recovery_replay.sql").read_text()
schema = """
CREATE TABLE public.factory_projects(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),project_key text NOT NULL UNIQUE,
 is_active bool NOT NULL DEFAULT true,
 repository text NOT NULL DEFAULT 'owner/repo',manifest jsonb NOT NULL DEFAULT '{}'::jsonb);
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
CREATE TABLE public.factory_human_gates(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 run_id uuid NOT NULL REFERENCES public.factory_runs(id),
 status text NOT NULL);
CREATE TABLE public.factory_change_sets(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),project_id uuid REFERENCES public.factory_projects(id),
 root_task_id uuid REFERENCES public.factory_tasks(id),
 status text NOT NULL,lease_owner text,lease_expires_at timestamptz,
 created_at timestamptz DEFAULT now(),updated_at timestamptz DEFAULT now(),attempt_count int DEFAULT 0,
 metadata jsonb DEFAULT '{}'::jsonb);
CREATE TABLE public.factory_change_set_work_units(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),task_id uuid REFERENCES public.factory_tasks(id),
 run_id uuid REFERENCES public.factory_runs(id),
 change_set_id uuid REFERENCES public.factory_change_sets(id),
 plan_task_key text DEFAULT 'fixture',wave integer DEFAULT 1,
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
CREATE TABLE public.factory_agents(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 agent_key text NOT NULL UNIQUE,is_active boolean NOT NULL DEFAULT true);
CREATE TABLE public.factory_run_agent_assignments(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 run_id uuid REFERENCES public.factory_runs(id),
 agent_id uuid REFERENCES public.factory_agents(id),
 status text NOT NULL DEFAULT 'assigned',
 assigned_at timestamptz DEFAULT now(),
 claimed_at timestamptz);
CREATE TABLE public.factory_audit_events(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 project_id uuid,task_id uuid,run_id uuid,actor_type text,
 actor_ref text,event_type text,payload jsonb);
CREATE OR REPLACE FUNCTION public.factory_assert_project_execution_epoch(p_project_id uuid,p_generation bigint)
RETURNS void LANGUAGE plpgsql SET search_path TO '' AS $fixture$
DECLARE v_state text;v_generation bigint;
BEGIN
  SELECT state,generation INTO v_state,v_generation
  FROM public.factory_project_execution_controls WHERE project_id=p_project_id FOR SHARE;
  IF v_state IS DISTINCT FROM 'running' OR v_generation IS DISTINCT FROM p_generation
    OR p_generation<1 THEN RAISE EXCEPTION 'project epoch revoked' USING errcode='PT409'; END IF;
END;
$fixture$;
"""

with psycopg.connect(dsn, autocommit=True) as conn:
    conn.execute(schema)
    conn.execute(migration)
    conn.execute(terminal_migration)
    conn.execute(epoch_migration)
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
    rp=run(tp,"implementing",expired=True,metadata='{"execution_generation":1}')
    rr=run(tr,"implementing",expired=True,metadata='{"execution_generation":1}')
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

    # A pause command must wait for an authorized shared-control guard to
    # commit, proving the lock boundary rather than merely string matching.
    with psycopg.connect(dsn) as guarded, psycopg.connect(dsn, autocommit=True) as pauser:
        guarded.execute("SELECT public.factory_assert_project_running(%s)",(running,))
        pauser.execute("SET lock_timeout='200ms'")
        try:
            pauser.execute(
                "UPDATE public.factory_project_execution_controls SET state='paused' WHERE project_id=%s",
                (running,),
            )
            raise AssertionError("Pause updated control during guarded transaction")
        except psycopg.Error as e:
            assert e.sqlstate=="55P03", (e.sqlstate,str(e))
        guarded.commit()
        pauser.execute(
            "UPDATE public.factory_project_execution_controls SET state='paused' WHERE project_id=%s",
            (running,),
        )
        assert pauser.execute(
            "SELECT state FROM public.factory_project_execution_controls WHERE project_id=%s",
            (running,),
        ).fetchone()[0]=="paused"
    try:
        conn.execute("SELECT public.factory_assert_project_running(%s)",(running,))
        raise AssertionError("paused project admitted after lock was released")
    except psycopg.Error as e:
        assert e.sqlstate=="PT409"
    conn.execute("UPDATE public.factory_project_execution_controls SET state='running' WHERE project_id=%s",(running,))

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


    # Terminal reconciliation was the remaining unfenced recovery RPC.
    # A cancelled parent is not permission to modify its paused/stopped children.
    # Independent running projects must still make progress in this same call.
    live = project("terminal-running","running")
    def cancelled_parent(pid):
        return task(pid,"cancelled")
    parent_paused = cancelled_parent(paused)
    parent_stopped = cancelled_parent(stopped)
    parent_running = cancelled_parent(live)
    child_paused = task(paused,"queued")
    child_stopped = task(stopped,"queued")
    child_running = task(live,"queued")
    child_integrated = task(live,"integrated")
    # Deliberately cross-project parent: no project may cancel another project's child.
    cross_project_child = task(live,"queued")
    for child_id,parent_id in ((child_paused,parent_paused),(child_stopped,parent_stopped),
                               (child_running,parent_running),(child_integrated,parent_running),
                               (cross_project_child,parent_paused)):
        conn.execute("UPDATE public.factory_tasks SET parent_task_id=%s WHERE id=%s",
                     (parent_id,child_id))
    def change_set_for(pid,root):
        return single(
            "INSERT INTO public.factory_change_sets(project_id,root_task_id,status) VALUES (%s,%s,'integrating') RETURNING id",
            (pid,root),
        )
    cs_paused=change_set_for(paused,parent_paused)
    cs_stopped=change_set_for(stopped,parent_stopped)
    cs_running=change_set_for(live,parent_running)
    counts=single("SELECT public.factory_reconcile_terminal_task_descendants()")
    assert counts=={"completed_children":1,"cancelled_children":1,"superseded_change_sets":1},counts
    for tid in (child_paused,child_stopped,cross_project_child):
        assert single("SELECT status FROM public.factory_tasks WHERE id=%s",(tid,))=="queued"
    assert single("SELECT status FROM public.factory_tasks WHERE id=%s",(child_integrated,))=="completed"
    assert single("SELECT status FROM public.factory_tasks WHERE id=%s",(child_running,))=="cancelled"
    for sid in (cs_paused,cs_stopped):
        assert single("SELECT status FROM public.factory_change_sets WHERE id=%s",(sid,))=="integrating"
    assert single("SELECT status FROM public.factory_change_sets WHERE id=%s",(cs_running,))=="superseded"
    assert single("SELECT public.factory_reconcile_terminal_task_descendants()")=={
        "completed_children":0,"cancelled_children":0,"superseded_change_sets":0
    }
    # Resume preserves old work until an authorized recovery, with no new run.
    before_runs=single("SELECT count(*) FROM public.factory_runs")
    conn.execute("UPDATE public.factory_project_execution_controls SET state='running',generation=2 WHERE project_id=%s",(paused,))
    counts=single("SELECT public.factory_reconcile_terminal_task_descendants()")
    assert counts=={"completed_children":0,"cancelled_children":1,"superseded_change_sets":1},counts
    assert single("SELECT status FROM public.factory_tasks WHERE id=%s",(child_paused,))=="cancelled"
    assert single("SELECT status FROM public.factory_tasks WHERE id=%s",(cross_project_child,))=="queued"
    assert single("SELECT status FROM public.factory_change_sets WHERE id=%s",(cs_paused,))=="superseded"
    assert single("SELECT count(*) FROM public.factory_runs")==before_runs

    # Simulate an in-flight operator pause with the control row locked. A
    # second worker must SKIP that project instead of blocking/deadlocking,
    # and must still reconcile an unrelated running project's ready child.
    race=project("terminal-pausing","running")
    race_parent=cancelled_parent(race)
    race_child=task(race,"queued")
    conn.execute("UPDATE public.factory_tasks SET parent_task_id=%s WHERE id=%s",(race_parent,race_child))
    live_2=project("terminal-independent","running")
    other_parent=cancelled_parent(live_2)
    other_child=task(live_2,"queued")
    conn.execute("UPDATE public.factory_tasks SET parent_task_id=%s WHERE id=%s",(other_parent,other_child))
    with psycopg.connect(dsn) as pausing:
        pausing.execute("UPDATE public.factory_project_execution_controls SET state='paused' WHERE project_id=%s",(race,))
        with psycopg.connect(dsn,autocommit=True) as recovering:
            recovering.execute("SET statement_timeout='2000ms'")
            race_count=recovering.execute("SELECT public.factory_reconcile_terminal_task_descendants()").fetchone()[0]
            assert race_count["cancelled_children"]==1,race_count
            assert recovering.execute("SELECT status FROM public.factory_tasks WHERE id=%s",(race_child,)).fetchone()[0]=="queued"
            assert recovering.execute("SELECT status FROM public.factory_tasks WHERE id=%s",(other_child,)).fetchone()[0]=="cancelled"
        pausing.commit()
    assert single("SELECT public.factory_reconcile_terminal_task_descendants()")=={
        "completed_children":0,"cancelled_children":0,"superseded_change_sets":0
    }
    assert single("SELECT status FROM public.factory_tasks WHERE id=%s",(race_child,))=="queued"

    # Reverse interleave: recovery holds a shared project-control lock until
    # its transaction commits; Pause cannot commit between guard and mutation.
    share=project("terminal-share-lock","running")
    share_parent=cancelled_parent(share)
    share_child=task(share,"queued")
    conn.execute("UPDATE public.factory_tasks SET parent_task_id=%s WHERE id=%s",(share_parent,share_child))
    with psycopg.connect(dsn) as reconciler, psycopg.connect(dsn,autocommit=True) as pauser:
        first=reconciler.execute("SELECT public.factory_reconcile_terminal_task_descendants()").fetchone()[0]
        assert first["cancelled_children"]==1,first
        pauser.execute("SET lock_timeout='200ms'")
        try:
            pauser.execute("UPDATE public.factory_project_execution_controls SET state='paused' WHERE project_id=%s",(share,))
            raise AssertionError("Pause committed through an in-flight terminal recovery")
        except psycopg.Error as e:
            assert e.sqlstate=="55P03",(e.sqlstate,str(e))
        reconciler.commit()
        pauser.execute("UPDATE public.factory_project_execution_controls SET state='paused' WHERE project_id=%s",(share,))
    assert single("SELECT status FROM public.factory_tasks WHERE id=%s",(share_child,))=="cancelled"
    assert single("SELECT public.factory_reconcile_terminal_task_descendants()")=={
        "completed_children":0,"cancelled_children":0,"superseded_change_sets":0
    }


    # Live-condition reproducer: a claimed gen1 run can have an expired
    # lease when the operator Pauses, then Resume advances project epoch to
    # gen2. Never replay unknown network/model effects with a new claim.
    epoch=project("cross-epoch-control","running",2)
    def status(run_id):
        return single("SELECT status FROM public.factory_runs WHERE id=%s",(run_id,))
    def task_status(task_id):
        return single("SELECT status FROM public.factory_tasks WHERE id=%s",(task_id,))
    def set_date(run_id,day):
        conn.execute("UPDATE public.factory_runs SET created_at=%s::timestamptz WHERE id=%s",(day,run_id))
    def create_direct(pid,gen,stamp,day):
        tid=task(pid,"queued_execution")
        rid=run(tid,"queued",metadata=('{"execution_generation":%d}'%stamp if stamp else "{}"))
        conn.execute("UPDATE public.factory_runs SET execution_route='direct' WHERE id=%s",(rid,))
        set_date(rid,day)
        cs=single("""INSERT INTO public.factory_change_sets(project_id,root_task_id,status)
                      VALUES (%s,%s,'building') RETURNING id""",(pid,tid))
        unit=single("""INSERT INTO public.factory_change_set_work_units(task_id,run_id,change_set_id,status)
                        VALUES (%s,%s,%s,'queued') RETURNING id""",(tid,rid,cs))
        agent_id=single("SELECT id FROM public.factory_agents WHERE agent_key='direct-test'")
        conn.execute("""INSERT INTO public.factory_run_agent_assignments(run_id,agent_id,status)
                        VALUES (%s,%s,'assigned')""",(rid,agent_id))
        return tid,rid,cs,unit

    # Pure classic claiming must skip an older stale queued run before LIMIT.
    stale_task=task(epoch,"queued")
    stale=run(stale_task,"queued",metadata='{"stages":[],"execution_generation":1}')
    set_date(stale,"2001-01-01 00:00:00+00")
    fresh_task=task(epoch,"queued")
    fresh=run(fresh_task,"queued",metadata='{"stages":[]}')
    set_date(fresh,"2001-01-02 00:00:00+00")
    received=single("SELECT public.factory_claim_next_run('epoch-fixture')")
    assert received["run_id"]==str(fresh),received
    assert status(stale)=="queued" and status(fresh)=="running"
    assert single("SELECT metadata->>'execution_generation' FROM public.factory_runs WHERE id=%s",(fresh,))=="2"

    # Direct claims likewise must not keep selecting the oldest stale item.
    conn.execute("INSERT INTO public.factory_agents(agent_key) VALUES ('direct-test')")
    dt_stale,dr_stale,cs_stale,u_stale=create_direct(epoch,2,1,"2000-01-01 00:00:00+00")
    dt_fresh,dr_fresh,cs_fresh,u_fresh=create_direct(epoch,2,0,"2000-01-02 00:00:00+00")
    chosen=single("SELECT public.factory_claim_next_agent_direct_run('direct-fixture')")
    assert chosen["run_id"]==str(dr_fresh),chosen
    assert status(dr_stale)=="queued" and status(dr_fresh)=="implementing"
    assert single("SELECT metadata->>'execution_generation' FROM public.factory_runs WHERE id=%s",(dr_fresh,))=="2"

    # Direct Change Set recovery called independently of global recovery
    # quarantines a stale implementing lease, while a same-epoch work unit
    # remains automatically recoverable.
    d_stale_task=task(epoch,"implementing")
    d_stale=run(d_stale_task,"implementing",expired=True,
                metadata='{"execution_generation":1}',attempts=1)
    conn.execute("UPDATE public.factory_runs SET execution_route='direct' WHERE id=%s",(d_stale,))
    d_stale_cs=single("""INSERT INTO public.factory_change_sets(project_id,root_task_id,status)
                        VALUES (%s,%s,'building') RETURNING id""",(epoch,d_stale_task))
    d_stale_u=single("""INSERT INTO public.factory_change_set_work_units(task_id,run_id,change_set_id,status)
                       VALUES (%s,%s,%s,'running') RETURNING id""",(d_stale_task,d_stale,d_stale_cs))
    d_valid_task=task(epoch,"implementing")
    d_valid=run(d_valid_task,"implementing",expired=True,
                metadata='{"execution_generation":2}',attempts=1)
    conn.execute("UPDATE public.factory_runs SET execution_route='direct' WHERE id=%s",(d_valid,))
    d_valid_cs=single("""INSERT INTO public.factory_change_sets(project_id,root_task_id,status)
                        VALUES (%s,%s,'building') RETURNING id""",(epoch,d_valid_task))
    d_valid_u=single("""INSERT INTO public.factory_change_set_work_units(task_id,run_id,change_set_id,status)
                       VALUES (%s,%s,%s,'running') RETURNING id""",(d_valid_task,d_valid,d_valid_cs))
    changed=single("SELECT public.factory_recover_change_sets(3)")
    assert changed["stale_direct_requeued"]==1,changed
    assert status(d_stale)=="blocked" and task_status(d_stale_task)=="blocked"
    assert single("SELECT status FROM public.factory_change_set_work_units WHERE id=%s",(d_stale_u,))=="blocked"
    assert single("SELECT status FROM public.factory_change_sets WHERE id=%s",(d_stale_cs,))=="blocked"
    assert single("SELECT metadata->>'blocker' FROM public.factory_change_sets WHERE id=%s",(d_stale_cs,))=="stale_execution_epoch"
    assert status(d_valid)=="queued"
    assert single("SELECT status FROM public.factory_change_set_work_units WHERE id=%s",(d_valid_u,))=="queued"

    # Resume of paused old claims: expired gen1, unknown gen, and a stale
    # queued run are quarantined; an expired gen2 lease is safely requeued.
    paused_epoch=project("epoch-paused-before-resume","paused",1)
    stale_paused_task=task(paused_epoch,"running")
    stale_paused=run(stale_paused_task,"running",expired=True,
                     metadata='{"execution_generation":1,"stages":[]}')
    pre=single("SELECT public.factory_recover_expired_runs(3)")
    assert status(stale_paused)=="running",pre
    conn.execute("UPDATE public.factory_project_execution_controls SET state='running',generation=2 WHERE project_id=%s",(paused_epoch,))
    live_task=task(epoch,"running")
    valid_expired=run(live_task,"running",expired=True,metadata='{"execution_generation":2,"stages":[]}')
    unknown_task=task(epoch,"running")
    unknown=run(unknown_task,"running",expired=True,metadata='{"stages":[]}')
    count_before=single("SELECT count(*) FROM public.factory_runs")
    out=single("SELECT public.factory_recover_expired_runs(3)")
    assert out["requeued"]==1 and out["failed"]==0,out
    assert status(stale_paused)=="blocked" and task_status(stale_paused_task)=="blocked"
    assert status(stale)=="blocked" and task_status(stale_task)=="blocked"
    assert status(dr_stale)=="blocked" and task_status(dt_stale)=="blocked"
    assert status(unknown)=="blocked" and task_status(unknown_task)=="blocked"
    assert status(valid_expired)=="queued"
    assert single("SELECT count(*) FROM public.factory_runs")==count_before
    ev_count=single("""SELECT count(*) FROM public.factory_audit_events
                       WHERE event_type='run.stale_execution_epoch_quarantined'""")
    assert ev_count>=4,ev_count

    # A later recovery reconciles the original stale direct Change Set unit
    # to blocked instead of silently replaying it in another wave.
    again=single("SELECT public.factory_recover_change_sets(3)")
    assert again["stale_direct_requeued"]==0,again
    assert single("SELECT status FROM public.factory_change_set_work_units WHERE id=%s",(u_stale,))=="blocked"
    assert single("SELECT status FROM public.factory_change_sets WHERE id=%s",(cs_stale,))=="blocked"

    # A second recovery cannot create a run, cost or duplicate audit receipt.
    single("SELECT public.factory_recover_expired_runs(3)")
    single("SELECT public.factory_recover_change_sets(3)")
    assert single("SELECT count(*) FROM public.factory_runs")==count_before
    assert single("""SELECT count(*) FROM public.factory_audit_events
                     WHERE event_type='run.stale_execution_epoch_quarantined'""")==ev_count

    # Explicit retry is a new operator-authorized run; provenance of the
    # old generation stays, but its execution capability must not be copied.
    failed_task=task(epoch,"failed")
    failed_run=run(failed_task,"failed",metadata='{"stages":[],"execution_generation":1}')
    retry=single("SELECT public.factory_retry_failed_run(%s,'operator-reviewed')",(failed_run,))
    new_run=retry["run_id"]
    epoch_copied=single("""SELECT metadata ? 'execution_generation'
                           FROM public.factory_runs WHERE id=%s""",(new_run,))
    assert epoch_copied is False
    assert single("SELECT metadata->>'retry_source_generation' FROM public.factory_runs WHERE id=%s",(new_run,))=="1"
    try:
        conn.execute("SELECT public.factory_retry_failed_run(%s,'again')",(failed_run,))
        raise AssertionError("duplicate retry created")
    except psycopg.Error:
        pass
    assert single("SELECT count(*) FROM public.factory_runs WHERE task_id=%s",(failed_task,))==2

print("RECOVERY_MANUAL_CONTROL_POSTGRES_PASS=1")
