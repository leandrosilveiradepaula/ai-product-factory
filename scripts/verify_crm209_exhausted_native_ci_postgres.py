#!/usr/bin/env python3
"""Disposable PostgreSQL proof for the exact one-shot exhausted CRM209 CI recovery.

Never connect to a shared database or assume CI green means operational PASS.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict

dsn = os.environ.get("FACTORY_CRM209_NATIVE_QA_DSN", "")
cfg = conninfo_to_dict(dsn)
if (os.environ.get("FACTORY_CRM209_NATIVE_QA_ISOLATED") != "true"
    or cfg.get("host") not in ("127.0.0.1", "localhost")
    or cfg.get("dbname") != "factory_crm209_native_qa"
    or cfg.get("user") != "factory_ci"):
    raise SystemExit("REFUSING_NON_ISOLATED_CRM209_DATABASE")

migration = (
    Path(__file__).resolve().parents[1]
    / "supabase/migrations/20261104123000_v2_crm209_exhausted_native_ci_recovery.sql"
).read_text()

PROJECT = "2d30e00a-ff72-4044-b838-011c263ed672"
JOURNEY = "bb14e150-2c7e-423b-8e5d-e211dab6225c"
CS = "3f09952e-0384-46ee-97aa-a46c89346678"
ROOT_RUN = "b302e61f-0471-4f92-9e9d-84ac9f5c9694"
EXHAUSTED = "ca53e605-b132-4937-aed3-f907cea2e221"
PREVIOUS = "50076343-55e7-47dc-80ee-2424e4d69499"
ROOT_TASK = "50749027-26b0-4200-9c25-c1ed18548071"
CANDIDATE = "e5eb59c1a56b0c922a5e0d1e956e8c442dff152b"
SOURCE = "b1935c8f6e61ae246eb8958673b2a9e18c3da81f"
BRANCH = "factory/journey-" + JOURNEY
PREVIEW = "preview/crm209-delivery-v4"
REPO = "leandrosilveiradepaula/crm-infodive"
URL = ("https://github.com/" + REPO
       + "/actions/runs/41764182167/job/126358570861")
RPC = "public.factory_resume_crm209_exhausted_native_ci_once"
SCOPES = ["src/services/ContractService.ts", "test/contract-access.test.ts"]

schema = """
create role anon nologin;
create role authenticated nologin;
create role service_role nologin;
create table public.factory_projects (
  id uuid primary key, project_key text, repository text,
  project_kind text, is_active boolean
);
create table public.factory_project_execution_controls (
  project_id uuid primary key, state text, generation bigint
);
create table public.factory_project_scheduling (project_id uuid, paused boolean);
create table public.factory_tasks (
  id uuid primary key default gen_random_uuid(), project_id uuid,
  parent_task_id uuid, external_key text, title text, description text,
  status text, complexity text, risk jsonb,
  acceptance_criteria jsonb, depends_on jsonb, scope_keys jsonb,
  journey_id uuid, updated_at timestamptz
);
create table public.factory_runs (
  id uuid primary key, task_id uuid, journey_id uuid, status text,
  attempt_count integer, source_commit text, candidate_commit text,
  branch_name text, lease_owner text, lease_expires_at timestamptz,
  metadata jsonb
);
create table public.factory_journeys (
  id uuid primary key, project_id uuid, state text,
  execution_generation bigint, source_commit text, binding jsonb
);
create table public.factory_change_sets (
  id uuid primary key, project_id uuid, root_task_id uuid, journey_id uuid,
  status text, source_commit text, candidate_commit text, integration_branch text,
  current_wave integer, attempt_count integer, release_run_id uuid,
  lease_owner text, lease_expires_at timestamptz, metadata jsonb,
  updated_at timestamptz
);
create table public.factory_change_set_work_units (
  id uuid primary key default gen_random_uuid(), change_set_id uuid, task_id uuid,
  plan_task_key text, agent_key text, wave integer, status text
);
create table public.factory_ci_repair_requests (
  id uuid primary key, project_id uuid, change_set_id uuid,
  source_run_id uuid, work_unit_id uuid, task_id uuid,
  release_run_id uuid, repaired_commit text,
  repository text, pr_number integer, branch text,
  original_candidate_commit text, execution_generation bigint,
  attempt integer check (attempt between 1 and 4),
  max_attempts integer check (max_attempts between 1 and 3),
  failure_class text, failures jsonb, write_scopes jsonb, status text,
  blocker_reason text, lease_owner text, lease_expires_at timestamptz,
  updated_at timestamptz,
  constraint factory_ci_repair_attempt_bound check (
    (status = 'exhausted' and attempt = max_attempts + 1)
    or (status <> 'exhausted' and attempt <= max_attempts)
  )
);
create table public.factory_run_agent_assignments (
  run_id uuid, status text
);
create table public.factory_human_gates (run_id uuid, status text);
create table public.factory_audit_events (
  id bigint generated always as identity primary key,
  project_id uuid, task_id uuid, run_id uuid,
  actor_type text, actor_ref text, event_type text, payload jsonb
);
"""

def receipt(db, *, sha=CANDIDATE, generation=19, request=EXHAUSTED):
    return db.execute(
        "select " + RPC + "(%s,%s,%s)",
        (sha, generation, UUID(request)),
    ).fetchone()[0]

with psycopg.connect(dsn, autocommit=True) as db:
    db.execute(schema)
    db.execute(migration)
    access = db.execute("""
      select prosecdef,
             has_function_privilege('service_role',oid,'execute'),
             has_function_privilege('anon',oid,'execute'),
             has_function_privilege('authenticated',oid,'execute')
      from pg_proc where proname='factory_resume_crm209_exhausted_native_ci_once'
    """).fetchone()
    assert access == (False, True, False, False), access

    db.execute("insert into factory_projects values (%s,'crm-infodive',%s,'existing',true)",
               (PROJECT, REPO))
    db.execute("insert into factory_project_execution_controls values (%s,'running',19)", (PROJECT,))
    binding = {
        "source_commit": SOURCE, "integration_branch": BRANCH,
        "preview_base_ref": PREVIEW, "binding_version": 2,
        "execution_generation": 19,
    }
    db.execute(
        "insert into factory_journeys values (%s,%s,'executing',19,%s,%s::jsonb)",
        (JOURNEY, PROJECT, SOURCE, json.dumps(binding)),
    )
    db.execute(
        "insert into factory_tasks(id,project_id,status,journey_id)"
        " values (%s,%s,'failed',%s)",
        (ROOT_TASK, PROJECT, JOURNEY),
    )
    run_meta = {"ci_repair_request_id": EXHAUSTED, "execution_generation": 19,
                "change_set_id": CS}
    db.execute(
        "insert into factory_runs(id,task_id,journey_id,status,attempt_count,"
        "candidate_commit,branch_name,metadata) "
        "values (%s,%s,%s,'failed_gate',0,%s,%s,%s::jsonb)",
        (ROOT_RUN, ROOT_TASK, JOURNEY, CANDIDATE, BRANCH, json.dumps(run_meta)),
    )
    meta = {"blocker": "ci_repair_attempts_exhausted",
            "ci_repair_request_id": PREVIOUS}
    db.execute(
        "insert into factory_change_sets (id,project_id,root_task_id,journey_id,"
        "status,source_commit,candidate_commit,integration_branch,current_wave,"
        "attempt_count,release_run_id,metadata) values "
        "(%s,%s,%s,%s,'blocked',%s,%s,%s,4,1,%s,%s::jsonb)",
        (CS, PROJECT, ROOT_TASK, JOURNEY, SOURCE, CANDIDATE,
         BRANCH, ROOT_RUN, json.dumps(meta)),
    )
    for i in (1, 2, 3):
        db.execute(
            "insert into factory_ci_repair_requests("
            "id,project_id,change_set_id,source_run_id,repository,pr_number,branch,"
            "original_candidate_commit,execution_generation,attempt,max_attempts,"
            "failure_class,failures,write_scopes,status) values "
            "(%s,%s,%s,%s,%s,212,%s,%s,19,%s,3,'code','[]'::jsonb,'[]'::jsonb,'ci_failed')",
            (PREVIOUS if i == 3 else uuid4(), PROJECT, CS, uuid4(),
             REPO, BRANCH, CANDIDATE, i),
        )
    failures = [{
        "name": "native-ci/tests",
        "conclusion": "failure",
        "failure_class": "code",
        "summary": "Verified failed GitHub Actions step (run and attempt bound)",
        "details_url": URL,
    }]
    db.execute(
        "insert into factory_ci_repair_requests("
        "id,project_id,change_set_id,source_run_id,repository,pr_number,branch,"
        "original_candidate_commit,execution_generation,attempt,max_attempts,"
        "failure_class,failures,write_scopes,status,blocker_reason) values "
        "(%s,%s,%s,%s,%s,212,%s,%s,19,4,3,'code',%s::jsonb,"
        "'[]'::jsonb,'exhausted','ci_repair_attempts_exhausted')",
        (EXHAUSTED, PROJECT, CS, ROOT_RUN, REPO, BRANCH, CANDIDATE,
         json.dumps(failures)),
    )

    for wrong in (
        {"sha": "0" * 40}, {"generation": 20}, {"request": str(uuid4())}
    ):
        other = receipt(db, **wrong)
        assert other == {"status": "idle", "requeued": False}, other

    db.execute("update factory_project_execution_controls set generation=20")
    try:
        receipt(db)
        raise AssertionError("epoch drift was accepted")
    except psycopg.Error as exc:
        assert exc.sqlstate == "PT409", exc
    db.execute("update factory_project_execution_controls set generation=19")

    db.execute("insert into factory_project_scheduling values (%s,true)", (PROJECT,))
    try:
        receipt(db)
        raise AssertionError("paused project was accepted")
    except psycopg.Error as exc:
        assert exc.sqlstate == "PT409", exc
    db.execute("delete from factory_project_scheduling")

    first = receipt(db)
    assert first["status"] == "requeued" and first["requeued"] is True, first
    assert first["paid_model_calls"] == 0 and first["model_calls_allowed"] is False
    assert first["release_authorized"] is False
    assert receipt(db) == {"status": "idle", "requeued": False}
    row = db.execute("""
        select rr.status,rr.deterministic_only,rr.attempt,rr.max_attempts,
               rr.write_scopes,cs.status,cs.current_wave,r.status,t.status,u.status
        from factory_ci_repair_requests rr
        join factory_change_sets cs on cs.id=rr.change_set_id
        join factory_tasks t on t.id=rr.task_id
        join factory_change_set_work_units u on u.id=rr.work_unit_id
        join factory_runs r on r.id=rr.source_run_id
        where rr.id=%s
    """, (EXHAUSTED,)).fetchone()
    assert row == ("queued",True,4,3,SCOPES,"building",5,
                   "repair_pending","queued","pending"), row
    root_state = db.execute(
        "select status from factory_tasks where id=%s", (ROOT_TASK,),
    ).fetchone()[0]
    assert root_state == "queued_execution", root_state
    previous = db.execute(
        "select count(*) from factory_ci_repair_requests "
        "where change_set_id=%s and status='ci_failed' and not deterministic_only",
        (CS,),
    ).fetchone()[0]
    assert previous == 3
    events = db.execute(
        "select payload from factory_audit_events where "
        "event_type='journey.v2.native_ci_deterministic_exception'"
    ).fetchall()
    assert len(events) == 1 and events[0][0]["paid_model_calls"] == 0

    try:
        db.execute(
            "insert into factory_ci_repair_requests("
            "id,attempt,max_attempts,status,deterministic_only) "
            "values (%s,4,3,'queued',true)", (uuid4(),)
        )
        raise AssertionError("unrelated over-limit request was accepted")
    except psycopg.Error as exc:
        assert exc.sqlstate == "23514", exc

    print("CRM209_NATIVE_EXHAUSTED_RECOVERY_QA=PASS")
    print("EXCEPTION_REQUESTS=1 PAID_MODEL_CALLS=0 RELEASE_AUTHORIZED=false")
