#!/usr/bin/env python3
"""Real PostgreSQL-16 integration regression for the Preview-only merge RPC.

Never targets a remote database. No GitHub actions, no paid models, no
production writes. Executed in its own disposable GitHub Actions PG service.
"""
from __future__ import annotations

import json
import os
import uuid
from copy import deepcopy
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict


dsn = os.environ.get("FACTORY_PREVIEW_OBSERVER_TEST_DSN", "")
cfg = conninfo_to_dict(dsn)
if (
    os.environ.get("FACTORY_PREVIEW_OBSERVER_TEST_ISOLATED") != "true"
    or cfg.get("host") not in ("127.0.0.1", "localhost")
    or cfg.get("dbname") != "factory_preview_observer_test"
):
    raise SystemExit("refusing non-isolated PostgreSQL connection")

root = Path(__file__).resolve().parents[1]
sql = (root / "supabase/migrations/20261018213500_observe_preview_branch_integration.sql").read_text()
assert sql.count("create or replace function public.factory_observe_nonproduction_preview_merge(") == 1
assert sql.count("\ncommit;") == 1
assert sql.strip().endswith("commit;")
assert sql.count("$fn$;") == 1

head = "aee522fe742589e961420e15e9dc92a1500ae502"
merge = "88c3517529654911ed4ee3315fdcdafc200e3004"
base = "preview/hardening-release-candidate"
original_url = "https://crm-infodive-git-preview-pr-180-example.vercel.app"
postmerge_url = "https://crm-infodive-git-preview-hard-example.vercel.app"
project_id, task_id, run_id, change_set_id, snapshot_id = (uuid.uuid4() for _ in range(5))

setup = """
create role service_role nologin;
create role anon nologin;
create role authenticated nologin;

create table public.factory_projects (
 id uuid primary key, repository text not null
);
create table public.factory_tasks (
 id uuid primary key, project_id uuid not null, status text not null,
 risk jsonb not null default '{}'::jsonb
);
create table public.factory_runs (
 id uuid primary key, task_id uuid not null, status text not null,
 candidate_commit text not null, branch_name text not null,
 metadata jsonb not null default '{}'::jsonb, finished_at timestamptz
);
create table public.factory_change_sets (
 id uuid primary key, project_id uuid not null, release_run_id uuid not null,
 status text not null, candidate_commit text not null,
 integration_branch text not null, metadata jsonb not null, updated_at timestamptz
);
create table public.factory_project_execution_controls (
 project_id uuid primary key, state text not null, generation bigint not null
);
create table public.factory_release_reports (
 id uuid primary key default gen_random_uuid(),
 run_id uuid not null, status text not null, candidate_commit text not null,
 report jsonb not null, created_at timestamptz default now(), updated_at timestamptz
);
create table public.factory_evaluations (
 run_id uuid not null, eval_type text not null, status text not null,
 baseline_ref text, result jsonb
);
create table public.factory_specialist_lane_jobs (
 run_id uuid not null, role text not null, required boolean not null,
 status text not null, candidate_commit text not null
);
create table public.factory_tool_usage (
 run_id uuid not null, tool_family text not null, operation text not null,
 usage_units numeric, estimated_cost numeric, metadata jsonb,
 created_at timestamptz default now()
);
create table public.factory_deployments (
 run_id uuid not null, environment text not null, status text not null,
 metadata jsonb not null
);
create table public.factory_project_state_snapshots (
 id uuid primary key, project_id uuid not null, evidence jsonb not null,
 gaps jsonb not null, source_status jsonb not null, constraints jsonb not null
);
create table public.factory_audit_events (
 project_id uuid, task_id uuid, run_id uuid, actor_type text, actor_ref text,
 event_type text, payload jsonb
);
create table public.factory_agent_scope_locks (
 run_id uuid not null, released_at timestamptz
);
create function public.factory_release_agent_scope_locks(p_run_id uuid)
returns integer language plpgsql as $$
declare n integer;
begin
  update public.factory_agent_scope_locks set released_at=now()
  where run_id=p_run_id and released_at is null;
  get diagnostics n = row_count;
  return n;
end;
$$;
"""


def query(conn: psycopg.Connection, stmt: str, *args):
    return conn.execute(stmt, args).fetchone()


def refuse(conn: psycopg.Connection, evidence: dict, *,
           pr_number: int = 180, browser_snapshot: uuid.UUID | None = None):
    """A failed RPC must leave the synthetic Control Plane unchanged."""
    ev = deepcopy(evidence)
    if browser_snapshot is not None:
        ev["postmerge_browser_snapshot_id"] = str(browser_snapshot)
    try:
        with conn.transaction():
            query(conn,
                  "select public.factory_observe_nonproduction_preview_merge(%s,%s,%s,%s,%s,%s::jsonb)",
                  run_id, pr_number, head, merge, base, json.dumps(ev))
    except psycopg.Error:
        pass
    else:
        raise AssertionError("unsafe Preview integration was admitted")
    assert query(conn, "select status from public.factory_runs where id=%s", run_id)[0] == "awaiting_release"
    assert query(conn, "select status from public.factory_change_sets where id=%s", change_set_id)[0] == "ci_pending"
    assert query(conn, "select status from public.factory_release_reports where run_id=%s", run_id)[0] == "ready_for_human_release"
    assert query(conn, "select count(*) from public.factory_audit_events")[0] == 0


with psycopg.connect(dsn, autocommit=True) as conn:
    conn.execute(setup)
    # This actual CREATE FUNCTION is the test. No mocks or string-only checks.
    conn.execute(sql)
    rights = query(
        conn,
        """select p.prosecdef,
                  has_function_privilege('service_role',p.oid,'execute'),
                  has_function_privilege('anon',p.oid,'execute'),
                  has_function_privilege('authenticated',p.oid,'execute')
           from pg_proc p join pg_namespace n on n.oid=p.pronamespace
           where n.nspname='public'
             and p.proname='factory_observe_nonproduction_preview_merge'"""
    )
    assert rights == (False, True, False, False), rights

    conn.execute(
        "insert into public.factory_projects(id,repository) values (%s,%s)",
        (project_id, "leandrosilveiradepaula/crm-infodive"))
    conn.execute(
        "insert into public.factory_tasks(id,project_id,status,risk) values (%s,%s,'integrated','{}'::jsonb)",
        (task_id, project_id))
    conn.execute(
        """insert into public.factory_runs
           (id,task_id,status,candidate_commit,branch_name,metadata)
           values (%s,%s,'awaiting_release',%s,%s,'{}'::jsonb)""",
        (run_id, task_id, head, "factory/change-set-9e4647f6"))
    conn.execute(
        """insert into public.factory_change_sets
           (id,project_id,release_run_id,status,candidate_commit,integration_branch,metadata)
           values (%s,%s,%s,'ci_pending',%s,%s,%s::jsonb)""",
        (change_set_id, project_id, run_id, head, "factory/change-set-9e4647f6",
         json.dumps({"integration_epoch_receipt": {"generation": 1},
                     "integration_release_request": {
                         "pr_number": 180, "branch": "factory/change-set-9e4647f6",
                         "candidate_commit": head}})))
    conn.execute(
        """insert into public.factory_project_execution_controls
           (project_id,state,generation) values (%s,'running',1)""",
        (project_id,))
    conn.execute(
        """insert into public.factory_release_reports
           (run_id,status,candidate_commit,report)
           values (%s,'ready_for_human_release',%s,'{"blockers":[]}'::jsonb)""",
        (run_id,head))
    for kind, status, ref, result in (
        ("github_ci","success",head,{}),
        ("quality_gate","success",head,{"passed":True}),
        ("browser_e2e","success",original_url,{}),
    ):
        conn.execute(
            """insert into public.factory_evaluations
               (run_id,eval_type,status,baseline_ref,result)
               values (%s,%s,%s,%s,%s::jsonb)""",
            (run_id,kind,status,ref,json.dumps(result)))
    for role in ("security","qa","operations"):
        conn.execute(
            """insert into public.factory_specialist_lane_jobs
               (run_id,role,required,status,candidate_commit)
               values (%s,%s,true,'passed',%s)""",
            (run_id,role,head))
    conn.execute(
        """insert into public.factory_tool_usage
           (run_id,tool_family,operation,metadata)
           values (%s,'github','verified_preview_awaiting_human_merge',%s::jsonb)""",
        (run_id,json.dumps({"pr":180,"head_sha":head,"preview_url":original_url})))
    conn.execute(
        """insert into public.factory_deployments
           (run_id,environment,status,metadata) values (%s,'preview','success',%s::jsonb)""",
        (run_id,json.dumps({"candidate_commit":head,"preview_url":original_url})))
    conn.execute(
        """insert into public.factory_project_state_snapshots
           (id,project_id,evidence,gaps,source_status,constraints)
           values (%s,%s,%s::jsonb,'[]'::jsonb,%s::jsonb,%s::jsonb)""",
        (snapshot_id,project_id,
         json.dumps({"candidate_commit":merge,"target_repository":"leandrosilveiradepaula/crm-infodive",
                     "preview":{"url":postmerge_url,"provider":"vercel",
                                "status":"browser_verified","browser_verifier_run_id":39168503121}}),
         json.dumps({"vercel_preview":"resolved","browser_visual_validation":"success"}),
         json.dumps({"production_merge_authorized":False})))
    conn.execute("insert into public.factory_agent_scope_locks(run_id) values (%s)",(run_id,))
    evidence = {
        "repository":"leandrosilveiradepaula/crm-infodive",
        "pr_number":"180","candidate_commit":head,"head_sha":head,
        "head_ref":"factory/change-set-9e4647f6","base_ref":base,
        "merge_sha":merge,"merged":True,"merge_is_ancestor":True,
        "vercel_state":"success","production_released":False,
        "production_main_sha":"e521308e14380121670b22f1aa3078d14e1883d7",
        "observed_base_tip":merge,
        "postmerge_browser_snapshot_id":str(snapshot_id),
        "postmerge_preview_url":postmerge_url,"verifier_run_id":"39168503121",
    }

    wrong_vercel = {**evidence,"vercel_state":"pending"}
    refuse(conn, wrong_vercel)
    wrong_main = {**evidence,"production_main_sha":merge}
    refuse(conn, wrong_main)
    refuse(conn, evidence, browser_snapshot=uuid.uuid4())
    wrong_browser = {**evidence,"postmerge_preview_url":original_url}
    refuse(conn, wrong_browser)
    bad_identity = {**evidence,"repository":"attacker/crm"}
    refuse(conn, bad_identity)
    refuse(conn, evidence, pr_number=181)

    # Even with correct external evidence, a paused project cannot be modified.
    conn.execute("update public.factory_project_execution_controls set state='paused'")
    refuse(conn,evidence)
    conn.execute("update public.factory_project_execution_controls set state='running'")
    conn.execute("update public.factory_specialist_lane_jobs set status='failed' where role='qa'")
    refuse(conn,evidence)
    conn.execute("update public.factory_specialist_lane_jobs set status='passed' where role='qa'")

    ok = query(conn,
               "select public.factory_observe_nonproduction_preview_merge(%s,%s,%s,%s,%s,%s::jsonb)",
               run_id,180,head,merge,base,json.dumps(evidence))[0]
    assert ok["status"]=="integrated" and ok["release_completed"] is False,ok
    assert ok["idempotent"] is False,ok
    assert query(conn,"select status from public.factory_runs where id=%s",run_id)[0]=="integrated"
    assert query(conn,"select status from public.factory_change_sets where id=%s",change_set_id)[0]=="completed"
    assert query(conn,"select status from public.factory_release_reports where run_id=%s",run_id)[0]=="blocked"
    report = query(conn,"select report from public.factory_release_reports where run_id=%s",run_id)[0]
    assert report["release_state"]=="nonproduction_integrated"
    assert report["nonproduction_integration"]["production_release_completed"] is False
    assert query(conn,"select count(*) from public.factory_audit_events")[0]==1
    assert query(conn,"select count(*) from public.factory_tool_usage where operation='nonproduction_merge_observed'")[0]==1
    assert query(conn,"select count(*) from public.factory_agent_scope_locks where released_at is not null")[0]==1
    assert query(conn,"select count(*) from public.factory_evaluations where eval_type='human_release'")[0]==0

    replay = query(conn,
                   "select public.factory_observe_nonproduction_preview_merge(%s,%s,%s,%s,%s,%s::jsonb)",
                   run_id,180,head,merge,base,json.dumps(evidence))[0]
    assert replay["idempotent"] is True,replay
    assert query(conn,"select count(*) from public.factory_audit_events")[0]==1
    assert query(conn,"select count(*) from public.factory_tool_usage where operation='nonproduction_merge_observed'")[0]==1

print("NONPRODUCTION_PREVIEW_MERGE_POSTGRES_PASS")
