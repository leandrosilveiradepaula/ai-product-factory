#!/usr/bin/env python3
"""Exercise actual fail-closed backend-503 Preview recovery SQL in isolated PG16.

Never connect to a live Control Plane. No Vercel/GitHub/model calls or accounts.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict

dsn = os.environ.get("FACTORY_PREVIEW_BACKEND_TEST_DSN", "")
conninfo = conninfo_to_dict(dsn)
if (
    os.environ.get("FACTORY_PREVIEW_BACKEND_TEST_ISOLATED") != "true"
    or conninfo.get("host") not in ("localhost", "127.0.0.1")
    or conninfo.get("dbname") != "factory_preview_backend_test"
    or conninfo.get("user") != "factory_ci"
):
    raise SystemExit("REFUSING_NON_ISOLATED_PREVIEW_BACKEND_TEST_DATABASE")

root = Path(__file__).resolve().parents[1]
sql = (root / "supabase/migrations/"
       "20261026170000_resume_preview_backend_unavailable.sql").read_text()
assert sql.count("create or replace function public.factory_resume_preview_backend_unavailable_v1(") == 1
assert sql.strip().endswith("commit;")
assert sql.count("$fn$;") == 1

project, task, run, change_set = (uuid4() for _ in range(4))
sha = "a" * 40
branch = "factory/change-set-12345678"
url = "https://service-desk-preview-example.vercel.app"
repository = "owner/service-desk"
pr = 10

schema = """
create role service_role nologin;
create role anon nologin;
create role authenticated nologin;
create table public.factory_projects (
 id uuid primary key, is_active boolean, repository text
);
create table public.factory_project_execution_controls (
 project_id uuid primary key, state text, generation bigint
);
create table public.factory_tasks (
 id uuid primary key, project_id uuid, status text,
 updated_at timestamptz
);
create table public.factory_runs (
 id uuid primary key, task_id uuid, status text, candidate_commit text,
 branch_name text, lease_owner text, lease_expires_at timestamptz,
 metadata jsonb, finished_at timestamptz, last_error text
);
create table public.factory_change_sets (
 id uuid primary key, project_id uuid, release_run_id uuid,
 status text, candidate_commit text, integration_branch text,
 lease_owner text, lease_expires_at timestamptz, metadata jsonb
);
create table public.factory_specialist_lane_jobs (
 run_id uuid, required boolean, status text, candidate_commit text
);
create table public.factory_evaluations (
 id uuid primary key default gen_random_uuid(), run_id uuid,
 eval_type text, status text, baseline_ref text, result jsonb,
 created_at timestamptz default now()
);
create table public.factory_deployments (
 run_id uuid, environment text, status text, metadata jsonb
);
create table public.factory_audit_events (
 id bigint generated always as identity primary key,
 project_id uuid, task_id uuid, run_id uuid,
 actor_type text, actor_ref text, event_type text, payload jsonb
);
"""


def query(db, stmt: str, *args):
    return db.execute(stmt, args).fetchone()


def now_probe():
    return {
        "kind": "unauthenticated_json_session_probe",
        "url": url + "/api/session",
        "candidate_commit": sha,
        "http_status": "401",
        "content_type": "application/json",
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


github = {
    "pr_number": str(pr), "head_sha": sha, "head_ref": branch,
    "pr_state": "open", "merged": False, "vercel_state": "success",
    "repository": repository, "preview_url": url,
}


def invoke(db, *, evidence=None, proof=None, candidate=sha, number=pr):
    return query(
        db,
        "select public.factory_resume_preview_backend_unavailable_v1"
        "(%s,%s,%s,%s::jsonb,%s::jsonb)",
        run, candidate, number,
        json.dumps(evidence if evidence is not None else github),
        json.dumps(proof if proof is not None else now_probe()),
    )[0]


def assert_failed_unchanged(db):
    assert query(db, "select status from public.factory_runs where id=%s", run)[0] == "failed"
    assert query(db, "select status from public.factory_tasks where id=%s", task)[0] == "failed"
    assert query(db, "select status from public.factory_change_sets where id=%s", change_set)[0] == "ci_pending"
    assert query(db, "select count(*) from public.factory_audit_events")[0] == 0


def refuse(db, *, evidence=None, proof=None, candidate=sha, number=pr):
    try:
        with db.transaction():
            invoke(db, evidence=evidence, proof=proof, candidate=candidate, number=number)
    except psycopg.Error:
        pass
    else:
        raise AssertionError("unsafe Preview requeue admitted")
    assert_failed_unchanged(db)


with psycopg.connect(dsn, autocommit=True) as db:
    db.execute(schema)
    db.execute(sql)
    rights = query(db, """
        select p.prosecdef,
          has_function_privilege('service_role',p.oid,'execute'),
          has_function_privilege('anon',p.oid,'execute'),
          has_function_privilege('authenticated',p.oid,'execute')
        from pg_proc p join pg_namespace n on n.oid=p.pronamespace
        where n.nspname='public'
          and p.proname='factory_resume_preview_backend_unavailable_v1'
    """)
    assert rights == (False, True, False, False), rights

    db.execute("insert into public.factory_projects values (%s,true,%s)",
               (project, repository))
    db.execute("insert into public.factory_project_execution_controls values (%s,'running',1)",
               (project,))
    db.execute("insert into public.factory_tasks(id,project_id,status) values (%s,%s,'failed')",
               (task, project))
    db.execute("""insert into public.factory_runs(id,task_id,status,candidate_commit,
       branch_name,metadata) values (%s,%s,'failed',%s,%s,%s::jsonb)""",
               (run, task, sha, branch, json.dumps({
                   "change_set_id": str(change_set), "execution_generation": 1})))
    db.execute("""insert into public.factory_change_sets
      (id,project_id,release_run_id,status,candidate_commit,integration_branch,metadata)
      values (%s,%s,%s,'ci_pending',%s,%s,%s::jsonb)""",
               (change_set,project,run,sha,branch,json.dumps({
                   "integration_epoch_receipt":{"generation":1},
                   "integration_release_request":{"pr_number":pr,"candidate_commit":sha}})))
    for role in ("security","qa","operations"):
        db.execute("""insert into public.factory_specialist_lane_jobs
           values (%s,true,'passed',%s)""",(run,sha))
    for kind, status, ref, result in (
        ("github_ci","success",sha,{"pr":pr,"head_sha":sha,"ci_state":"success"}),
        ("quality_gate","success",sha,{"passed":True}),
        ("browser_e2e","failure",url,{"preview_url":url,
            "detail":"console: Failed to load resource: 503 | http_503: fetch /api/session"}),
    ):
        db.execute("""insert into public.factory_evaluations
           (run_id,eval_type,status,baseline_ref,result)
           values (%s,%s,%s,%s,%s::jsonb)""",
           (run,kind,status,ref,json.dumps(result)))
    db.execute("""insert into public.factory_deployments
       (run_id,environment,status,metadata) values (%s,'preview','success',%s::jsonb)""",
       (run,json.dumps({"candidate_commit":sha,"preview_url":url})))

    assert_failed_unchanged(db)

    # Wrong PR/commit/status/branch/URL and stale/failed health probes reject
    # without changing run status or overwriting the failed browser evaluation.
    for candidate, number in (("f"*40,pr),(sha,pr+1)):
        refuse(db,candidate=candidate,number=number)
    for k, bad in (
        ("pr_state", "closed"), ("head_ref", "other"),
        ("repository", "other/repo"), ("merged", True),
        ("vercel_state", "pending"), ("preview_url", "https://evil.vercel.app"),
    ):
        bogus = dict(github); bogus[k]=bad
        refuse(db,evidence=bogus)
    for changes in (
        {"http_status":"503"}, {"http_status":"302"},
        {"http_status":None}, {"content_type":None},
        {"content_type":"text/html"}, {"checked_at":None},
        {"url":"https://evil.vercel.app/api/session"},
        {"kind":"untrusted"},
        {"checked_at":(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()},
        {"checked_at":(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()},
    ):
        proof=now_probe();proof.update(changes)
        refuse(db,proof=proof)

    def mutate_and_refuse(stmt, restore):
        db.execute(stmt)
        refuse(db)
        db.execute(restore)

    mutate_and_refuse(
        f"update public.factory_project_execution_controls set state='paused' where project_id='{project}'",
        f"update public.factory_project_execution_controls set state='running' where project_id='{project}'")
    mutate_and_refuse(
        f"update public.factory_project_execution_controls set generation=2 where project_id='{project}'",
        f"update public.factory_project_execution_controls set generation=1 where project_id='{project}'")
    mutate_and_refuse(
        f"update public.factory_change_sets set lease_owner='busy' where id='{change_set}'",
        f"update public.factory_change_sets set lease_owner=null where id='{change_set}'")
    mutate_and_refuse(
        f"update public.factory_runs set lease_owner='busy' where id='{run}'",
        f"update public.factory_runs set lease_owner=null where id='{run}'")
    mutate_and_refuse(
        f"update public.factory_specialist_lane_jobs set status='pending' where run_id='{run}'",
        f"update public.factory_specialist_lane_jobs set status='passed' where run_id='{run}'")
    mutate_and_refuse(
        f"update public.factory_evaluations set status='failure' where run_id='{run}' and eval_type='github_ci'",
        f"update public.factory_evaluations set status='success' where run_id='{run}' and eval_type='github_ci'")
    mutate_and_refuse(
        f"update public.factory_deployments set status='failed' where run_id='{run}'",
        f"update public.factory_deployments set status='success' where run_id='{run}'")
    mutate_and_refuse(
        f"update public.factory_evaluations set result=jsonb_set(result,'{{detail}}','\"different failure\"') "
        f"where run_id='{run}' and eval_type='browser_e2e'",
        f"update public.factory_evaluations set result=jsonb_set(result,'{{detail}}',"
        f"'\"console: Failed to load resource: 503 | http_503: fetch /api/session\"') "
        f"where run_id='{run}' and eval_type='browser_e2e'")

    result=invoke(db)
    assert result["status"]=="preview_ready",result
    assert result["attempt"]==1
    assert result["original_failure_preserved"] is True
    assert result["browser_verified"] is False
    assert result["release_authorized"] is False
    assert query(db,"select status from public.factory_tasks where id=%s",task)[0]=="integrated"
    assert query(db,"select status from public.factory_change_sets where id=%s",change_set)[0]=="ci_pending"
    assert query(db,"select status from public.factory_evaluations where run_id=%s "
             "and eval_type='browser_e2e'",run)[0]=="failure"
    assert query(db,"select count(*) from public.factory_audit_events")[0]==1

    try:
        with db.transaction():
            invoke(db)
    except psycopg.Error:
        pass
    else:
        raise AssertionError("duplicate retry admitted")

    # A second properly evidenced failure can be retried once more;
    # a third attempt is forbidden even after the run is manually reset here.
    db.execute("update public.factory_runs set status='failed' where id=%s",(run,))
    db.execute("update public.factory_tasks set status='failed' where id=%s",(task,))
    second=invoke(db)
    assert second["attempt"]==2
    db.execute("update public.factory_runs set status='failed' where id=%s",(run,))
    db.execute("update public.factory_tasks set status='failed' where id=%s",(task,))
    try:
        with db.transaction():
            invoke(db)
    except psycopg.Error:
        pass
    else:
        raise AssertionError("retry budget not enforced")
    assert query(db,"select count(*) from public.factory_audit_events")[0]==2
    assert query(db,"select status from public.factory_runs where id=%s",run)[0]=="failed"

print("PREVIEW_BACKEND_RECOVERY_PG16_PASS=1")
