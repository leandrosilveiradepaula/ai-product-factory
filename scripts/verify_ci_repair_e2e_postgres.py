#!/usr/bin/env python3
"""Exercise the deployed CI-repair migration plus its replay correction in disposable PG16.

No GitHub writes, model calls, Supabase production access, or synthetic production runs.
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict

dsn = os.environ.get("FACTORY_CI_REPAIR_E2E_DSN", "")
info = conninfo_to_dict(dsn)
if (
    os.environ.get("FACTORY_CI_REPAIR_E2E_ISOLATED") != "true"
    or info.get("host") not in ("127.0.0.1", "localhost")
    or info.get("dbname") != "factory_ci_repair_e2e_test"
    or info.get("user") != "factory_ci"
):
    raise SystemExit("REFUSING_NON_ISOLATED_CI_REPAIR_DATABASE")

root = Path(__file__).resolve().parents[1]
original = (root / "supabase/migrations/20261021213414_durable_ci_repair_requests.sql").read_text()
correction = (root / "supabase/migrations/20261021234500_ci_repair_replay_idempotency.sql").read_text()
cumulative_scopes = (root / "supabase/migrations/20261022125100_ci_repair_cumulative_scopes.sql").read_text()
schema = """
create role anon nologin;
create role authenticated nologin;
create role service_role nologin;
create table public.factory_projects (
 id uuid primary key, project_key text not null, repository text not null
);
create table public.factory_tasks (
 id uuid primary key default gen_random_uuid(), project_id uuid not null references public.factory_projects(id),
 parent_task_id uuid references public.factory_tasks(id),
 external_key text, title text not null default 'Task',
 description text not null default '', status text not null default 'queued',
 complexity text not null default 'medium', risk jsonb not null default '{}'::jsonb,
 acceptance_criteria jsonb not null default '[]'::jsonb,
 depends_on jsonb not null default '[]'::jsonb,
 scope_keys jsonb not null default '[]'::jsonb
);
create table public.factory_runs (
 id uuid primary key, task_id uuid not null references public.factory_tasks(id),
 status text not null, candidate_commit text, branch_name text,
 metadata jsonb not null default '{}'::jsonb,
 lease_owner text, lease_expires_at timestamptz
);
create table public.factory_execution_team_plans (
 id uuid primary key, plan jsonb not null default '{}'::jsonb
);
create table public.factory_change_sets (
 id uuid primary key, project_id uuid not null references public.factory_projects(id),
 root_task_id uuid not null references public.factory_tasks(id),
 team_plan_id uuid references public.factory_execution_team_plans(id),
 status text not null, release_run_id uuid references public.factory_runs(id),
 candidate_commit text, integration_branch text,
 metadata jsonb not null default '{}'::jsonb, current_wave integer not null default 1,
 attempt_count integer not null default 0, lease_owner text, lease_expires_at timestamptz,
 updated_at timestamptz not null default now()
);
create table public.factory_change_set_work_units (
 id uuid primary key default gen_random_uuid(),
 change_set_id uuid not null references public.factory_change_sets(id),
 task_id uuid not null references public.factory_tasks(id),
 run_id uuid references public.factory_runs(id),
 plan_task_key text not null, agent_key text not null, wave integer not null,
 status text not null, changed_files jsonb
);
create table public.factory_project_execution_controls (
 project_id uuid primary key references public.factory_projects(id),
 state text not null, generation bigint not null
);
create table public.factory_repair_jobs (
 id uuid primary key, work_unit_id uuid, cycle integer, max_cycles integer,
 source_role text, finding jsonb, write_scopes jsonb, candidate_commit text
);
create table public.factory_tool_usage (
 run_id uuid not null references public.factory_runs(id),
 operation text not null, metadata jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now()
);
create table public.factory_audit_events (
 project_id uuid, task_id uuid, run_id uuid,
 actor_type text not null, actor_ref text, event_type text not null,
 payload jsonb not null default '{}'::jsonb
);
"""

failures = json.dumps([{"name": "pytest", "conclusion": "failure", "failure_class": "code"}])
branch = "factory/change-set-123"
repository = "test/isolated-factory"


def setup(conn: psycopg.Connection, *, sha: str, status: str = "ci_pending"):
    project, task, run, change_set, plan = (uuid.uuid4() for _ in range(5))
    conn.execute(
        "insert into public.factory_projects values (%s,'isolated',%s)", (project, repository)
    )
    conn.execute(
        "insert into public.factory_project_execution_controls values (%s,'running',3)",
        (project,),
    )
    conn.execute(
        "insert into public.factory_tasks(id,project_id,status) values (%s,%s,'completed')",
        (task, project),
    )
    conn.execute(
        "insert into public.factory_execution_team_plans(id) values (%s)", (plan,)
    )
    metadata = json.dumps({
        "source": "change-set",
        "change_set_id": str(change_set),
        "execution_generation": 3,
    })
    conn.execute(
        """insert into public.factory_runs
           (id,task_id,status,candidate_commit,branch_name,metadata)
           values (%s,%s,%s,%s,%s,%s::jsonb)""",
        (run, task, status, sha, branch, metadata),
    )
    conn.execute(
        """insert into public.factory_change_sets
           (id,project_id,root_task_id,team_plan_id,status,release_run_id,
            candidate_commit,integration_branch,metadata)
           values (%s,%s,%s,%s,'ci_pending',%s,%s,%s,%s::jsonb)""",
        (change_set, project, task, plan, run, sha, branch,
         json.dumps({"integrated_files": ["src/core.py"]})),
    )
    conn.execute(
        """insert into public.factory_tool_usage(run_id,operation,metadata)
           values (%s,'create_pr',%s::jsonb)""",
        (run, json.dumps({"pr": 73, "head_sha": sha, "change_set_id": str(change_set)})),
    )
    # A ci_pending candidate has already integrated its builder work units.
    # The fixture must mirror that durable history, not just the final-wave
    # metadata. Those historical units are not new repair work units.
    conn.execute(
        """insert into public.factory_change_set_work_units
           (change_set_id,task_id,plan_task_key,agent_key,wave,status,changed_files)
           values (%s,%s,'initial-builder','development',1,'integrated',%s::jsonb)""",
        (change_set, task, json.dumps(["src/core.py"])),
    )
    return project, task, run, change_set


def enqueue(conn: psycopg.Connection, ids, *, sha: str, error_json=failures, max_attempts=2,
            failure_class="code"):
    project, _task, run, change_set = ids
    return conn.execute(
        """select public.factory_enqueue_ci_repair(
          %s,%s,%s,%s,73,%s,%s,3,%s,%s::jsonb,%s)""",
        (run, project, change_set, repository, branch, sha,
         failure_class, error_json, max_attempts),
    ).fetchone()[0]


def count(conn: psycopg.Connection, change_set: uuid.UUID):
    return conn.execute(
        "select count(*) from public.factory_ci_repair_requests where change_set_id=%s",
        (change_set,),
    ).fetchone()[0]


def rejects(conn: psycopg.Connection, ids, **kwargs):
    try:
        with conn.transaction():
            enqueue(conn, ids, **kwargs)
    except psycopg.Error as error:
        assert error.sqlstate in {"PT409", "PT400"}, error
    else:
        raise AssertionError("unsafe CI repair call succeeded")


with psycopg.connect(dsn, autocommit=True) as conn:
    conn.execute(schema)
    conn.execute(original)
    conn.execute(correction)
    conn.execute(cumulative_scopes)

    # Confirm migration source and privilege boundaries as installed.
    installed = conn.execute("""
      select relrowsecurity from pg_class
       where oid='public.factory_ci_repair_requests'::regclass
    """).fetchone()
    assert installed == (True,), installed
    for fn in (
        "factory_enqueue_ci_repair",
        "factory_record_ci_repair_result",
    ):
        acl = conn.execute("""
          select has_function_privilege('service_role', p.oid, 'EXECUTE'),
                 has_function_privilege('anon', p.oid, 'EXECUTE'),
                 has_function_privilege('authenticated', p.oid, 'EXECUTE')
          from pg_proc p join pg_namespace n on n.oid=p.pronamespace
          where n.nspname='public' and p.proname=%s
        """, (fn,)).fetchone()
        assert acl == (True, False, False), (fn, acl)

    # First request must enqueue one durable work unit and modify the run.
    first_sha = "a" * 40
    ids = setup(conn, sha=first_sha)
    first = enqueue(conn, ids, sha=first_sha)
    assert first["created"] is True and first["attempt"] == 1, first
    assert count(conn, ids[3]) == 1
    assert conn.execute(
        "select status from public.factory_runs where id=%s", (ids[2],)
    ).fetchone()[0] == "repair_pending"
    assert conn.execute(
        "select status from public.factory_change_sets where id=%s", (ids[3],)
    ).fetchone()[0] == "building"
    assert conn.execute(
        "select count(*) from public.factory_change_set_work_units where change_set_id=%s and status='pending'",
        (ids[3],),
    ).fetchone()[0] == 1

    # Same-SHA retry after an HTTP timeout is exactly idempotent, not PT409.
    replay = enqueue(conn, ids, sha=first_sha)
    assert replay["created"] is False and replay["repair_request_id"] == first["repair_request_id"], replay
    assert count(conn, ids[3]) == 1
    assert conn.execute(
        "select count(*) from public.factory_change_set_work_units where change_set_id=%s and status='pending'",
        (ids[3],),
    ).fetchone()[0] == 1
    assert conn.execute("select count(*) from public.factory_audit_events").fetchone()[0] == 1

    # Different evidence or paused generation does not reuse another receipt.
    rejects(conn, ids, sha=first_sha, error_json=json.dumps([
        {"name": "different test", "conclusion": "failure", "failure_class": "code"}
    ]))
    conn.execute(
        "update public.factory_project_execution_controls set state='paused' where project_id=%s",
        (ids[0],),
    )
    rejects(conn, ids, sha=first_sha)
    conn.execute(
        "update public.factory_project_execution_controls set state='running' where project_id=%s",
        (ids[0],),
    )
    assert count(conn, ids[3]) == 1

    # Non-code GitHub failure can never be interpreted as authority to patch.
    other_sha = "b" * 40
    non_code_ids = setup(conn, sha=other_sha)
    non_code_evidence = json.dumps([
        {"name": "runner lost", "conclusion": "failure", "failure_class": "runner"}
    ])
    blocked = enqueue(conn, non_code_ids, sha=other_sha,
                      error_json=non_code_evidence, failure_class="runner")
    assert blocked["status"] == "blocked"
    assert conn.execute(
        "select status from public.factory_runs where id=%s",
        (non_code_ids[2],),
    ).fetchone()[0] == "failed_gate"
    assert conn.execute(
        "select count(*) from public.factory_change_set_work_units where change_set_id=%s and status='pending'",
        (non_code_ids[3],),
    ).fetchone()[0] == 0
    again = enqueue(conn, non_code_ids, sha=other_sha,
                    error_json=non_code_evidence, failure_class="runner")
    assert again["created"] is False

    # Three prior attempted repairs: terminal exhausted sentinel = fourth row.
    final_sha = "f" * 40
    exhausted_ids = setup(conn, sha=final_sha)
    p, root_task, _run, cs = exhausted_ids
    for attempt, source_sha in enumerate(("c" * 40, "d" * 40, "e" * 40), 1):
        old_run = uuid.uuid4()
        conn.execute(
            """insert into public.factory_runs(id,task_id,status,candidate_commit,branch_name,metadata)
               values (%s,%s,'ci_failed',%s,%s,'{}'::jsonb)""",
            (old_run, root_task, source_sha, branch),
        )
        conn.execute(
            """insert into public.factory_ci_repair_requests (
                 project_id,change_set_id,source_run_id,repository,pr_number,branch,
                 original_candidate_commit,execution_generation,attempt,max_attempts,
                 failure_class,failures,status
               ) values (%s,%s,%s,%s,73,%s,%s,3,%s,3,'code',%s::jsonb,'ci_failed')""",
            (p, cs, old_run, repository, branch, source_sha, attempt, failures),
        )
    exhausted = enqueue(conn, exhausted_ids, sha=final_sha, max_attempts=3)
    assert exhausted["status"] == "exhausted" and exhausted["attempt"] == 4, exhausted
    assert count(conn, cs) == 4
    assert conn.execute(
        "select status from public.factory_runs where id=%s", (exhausted_ids[2],)
    ).fetchone()[0] == "failed_gate"
    assert conn.execute(
        "select status from public.factory_change_sets where id=%s", (cs,)
    ).fetchone()[0] == "blocked"
    terminal_replay = enqueue(conn, exhausted_ids, sha=final_sha, max_attempts=3)
    assert terminal_replay["created"] is False and terminal_replay["status"] == "exhausted"
    assert count(conn, cs) == 4

    # A real multi-wave Change Set has a file ledger in every integrated
    # Work Unit. The old metadata only retained the final wave's files.
    cumulative_sha = "3" * 40
    cumulative_ids = setup(conn, sha=cumulative_sha)
    project, root_task, release_run, cumulative_cs = cumulative_ids
    conn.execute(
        """update public.factory_change_sets
           set current_wave=2, metadata=%s::jsonb where id=%s""",
        (json.dumps({"integrated_files": ["src/late.py"]}), cumulative_cs),
    )
    conn.execute(
        """update public.factory_change_set_work_units
           set changed_files=%s::jsonb where change_set_id=%s""",
        (json.dumps(["src/shared.py", "src/early.py"]), cumulative_cs),
    )
    conn.execute(
        """insert into public.factory_change_set_work_units
           (change_set_id,task_id,plan_task_key,agent_key,wave,status,changed_files)
           values (%s,%s,'second-builder','development',2,'integrated',%s::jsonb)""",
        (cumulative_cs, root_task, json.dumps(["src/late.py", "src/shared.py"])),
    )
    result = enqueue(conn, cumulative_ids, sha=cumulative_sha)
    assert result["status"] == "repair_pending", result
    scopes = conn.execute(
        "select write_scopes from public.factory_ci_repair_requests where id=%s",
        (result["repair_request_id"],),
    ).fetchone()[0]
    assert scopes == ["src/early.py", "src/late.py", "src/shared.py"], scopes
    task_scopes = conn.execute(
        "select scope_keys from public.factory_tasks where id=%s",
        (result["task_id"],),
    ).fetchone()[0]
    assert task_scopes == scopes
    assert conn.execute(
        """select count(*) from public.factory_change_set_work_units
           where change_set_id=%s and status='pending'""",
        (cumulative_cs,),
    ).fetchone()[0] == 1
    retry = enqueue(conn, cumulative_ids, sha=cumulative_sha)
    assert retry["created"] is False
    assert retry["repair_request_id"] == result["repair_request_id"]
    assert count(conn, cumulative_cs) == 1

    # Exercise the *real* context-source RPC with a routed repair run: the
    # semantic packet and executor receive exactly the same cumulative scopes.
    repair_run = uuid.uuid4()
    conn.execute(
        """insert into public.factory_runs(id,task_id,status,branch_name)
           values (%s,%s,'queued',%s)""",
        (repair_run, result["task_id"], branch),
    )
    conn.execute(
        "update public.factory_change_set_work_units set run_id=%s where id=%s",
        (repair_run, result["work_unit_id"]),
    )
    packet = conn.execute(
        "select public.factory_work_unit_context_source(%s)", (repair_run,),
    ).fetchone()[0]
    assert packet["repair"]["repair_kind"] == "ci", packet
    assert packet["repair"]["write_scopes"] == scopes, packet
    assert packet["assignment"]["scope_keys"] == scopes, packet

    # Untrusted broad final-wave metadata cannot expand the verified ledger.
    metadata_sha = "4" * 40
    metadata_ids = setup(conn, sha=metadata_sha)
    conn.execute(
        """update public.factory_change_sets set metadata=%s::jsonb where id=%s""",
        (json.dumps({"integrated_files": [".github/workflows/validate.yml", "."]}),
         metadata_ids[3]),
    )
    metadata_receipt = enqueue(conn, metadata_ids, sha=metadata_sha)
    metadata_scopes = conn.execute(
        "select write_scopes from public.factory_ci_repair_requests where id=%s",
        (metadata_receipt["repair_request_id"],),
    ).fetchone()[0]
    assert metadata_scopes == ["src/core.py"], metadata_scopes

    # A forged non-integrated historical unit blocks the Change Set, without
    # adding another work unit, granting a broad scope or leaving CI pending.
    inconsistent_sha = "5" * 40
    inconsistent_ids = setup(conn, sha=inconsistent_sha)
    conn.execute(
        """update public.factory_change_set_work_units set status='completed'
           where change_set_id=%s""",
        (inconsistent_ids[3],),
    )
    invalid = enqueue(conn, inconsistent_ids, sha=inconsistent_sha)
    assert invalid["status"] == "blocked"
    assert invalid["reason"] == "repair_scope_inconsistent"
    assert conn.execute(
        "select status from public.factory_change_sets where id=%s",
        (inconsistent_ids[3],),
    ).fetchone()[0] == "blocked"
    assert conn.execute(
        "select status from public.factory_runs where id=%s",
        (inconsistent_ids[2],),
    ).fetchone()[0] == "failed_gate"
    assert conn.execute(
        """select count(*) from public.factory_change_set_work_units
           where change_set_id=%s and status='pending'""",
        (inconsistent_ids[3],),
    ).fetchone()[0] == 0

    # Unsafe historical file paths are never passed to the model or worker.
    unsafe_sha = "6" * 40
    unsafe_ids = setup(conn, sha=unsafe_sha)
    conn.execute(
        "update public.factory_change_set_work_units set changed_files=%s::jsonb where change_set_id=%s",
        (json.dumps(["../escape.py"]), unsafe_ids[3]),
    )
    unsafe = enqueue(conn, unsafe_ids, sha=unsafe_sha)
    assert unsafe["status"] == "blocked" and unsafe["reason"] == "repair_scope_unsafe_path"
    assert count(conn, unsafe_ids[3]) == 1
    assert conn.execute(
        "select write_scopes from public.factory_ci_repair_requests where id=%s",
        (unsafe["repair_request_id"],),
    ).fetchone()[0] == []

    # 500 distinct paths are allowed; 501 fail closed. Individual work unit
    # arrays remain inside the <=500 item limit of integration evidence.
    large_sha = "7" * 40
    large_ids = setup(conn, sha=large_sha)
    conn.execute(
        "update public.factory_change_set_work_units set changed_files=%s::jsonb where change_set_id=%s",
        (json.dumps([f"src/file_{i:04d}.py" for i in range(500)]), large_ids[3]),
    )
    conn.execute(
        """insert into public.factory_change_set_work_units
           (change_set_id,task_id,plan_task_key,agent_key,wave,status,changed_files)
           values (%s,%s,'extra-integrated','development',1,'integrated',%s::jsonb)""",
        (large_ids[3], large_ids[1], json.dumps(["src/one_extra.py"])),
    )
    excess = enqueue(conn, large_ids, sha=large_sha)
    assert excess["status"] == "blocked" and excess["reason"] == "repair_scope_exceeds_limit"
    assert conn.execute(
        """select count(*) from public.factory_change_set_work_units
           where change_set_id=%s and status='pending'""",
        (large_ids[3],),
    ).fetchone()[0] == 0

# Cross-layer fixture: real runtime entrypoint, real transactional SQL RPCs and
# actual integration crash recovery with a fully simulated GitHub adapter.
# sys.path is local source only; no installed external model/provider.
import sys
sys.path.insert(0, str(root / "src"))
from ci_repair_disposable_full_journey import prove_full_journey

with psycopg.connect(dsn, autocommit=True) as conn:
    prove_full_journey(conn, setup, repository=repository, branch=branch)

print("CI_REPAIR_POSTGRES_E2E_PASS")
