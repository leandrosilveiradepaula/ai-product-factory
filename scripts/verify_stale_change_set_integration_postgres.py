#!/usr/bin/env python3
"""Exercise real Change Set scheduler/claim SQL in disposable PostgreSQL 16.

This test MUST NOT be run against a remote or production database.
No paid models, GitHub writes, migrations to real projects, or live CRM access.
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict


DSN = os.environ.get("FACTORY_STALE_CHANGE_SET_TEST_DSN", "")
cfg = conninfo_to_dict(DSN)
if (
    os.environ.get("FACTORY_STALE_CHANGE_SET_TEST_ISOLATED") != "true"
    or cfg.get("host") not in ("localhost", "127.0.0.1")
    or cfg.get("dbname") != "factory_change_set_guard_test"
    or cfg.get("user") != "factory_ci"
):
    raise SystemExit("refusing non-isolated Change Set guard database")

migration = (
    Path(__file__).resolve().parents[1]
    / "supabase/migrations/20261019193000_guard_stale_change_set_integration.sql"
).read_text()

# Minimal but REAL PostgreSQL relations used by the two function definitions.
# No mocked SQL results are used to assert claim behavior.
schema = """
create role service_role nologin;
create role anon nologin;
create role authenticated nologin;
create table public.factory_projects(
    id uuid primary key,
    project_key text not null,
    repository text,
    project_kind text not null,
    is_active boolean not null,
    manifest jsonb not null
);
create table public.factory_project_execution_controls(
    project_id uuid primary key,
    state text not null,
    generation bigint not null
);
create table public.factory_tasks(
    id uuid primary key,
    project_id uuid not null,
    status text not null
);
create table public.factory_runs(
    id uuid primary key,
    task_id uuid not null,
    status text not null,
    execution_route text,
    metadata jsonb
);
create table public.factory_change_sets(
    id uuid primary key,
    project_id uuid not null,
    status text not null,
    source_commit text,
    candidate_commit text,
    current_wave integer not null,
    attempt_count integer not null default 0,
    lease_owner text,
    lease_expires_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    integration_branch text not null
);
create table public.factory_change_set_work_units(
    id uuid primary key,
    change_set_id uuid not null,
    wave integer not null,
    status text not null,
    task_id uuid not null,
    plan_task_key text not null,
    agent_key text not null,
    base_commit text not null,
    branch_name text not null,
    output_commit text,
    changed_files jsonb not null
);
create table public.factory_specialist_lane_jobs(
    id uuid primary key,
    role text,
    status text
);
"""


def target(sha: str, repository: str = "test/crm", branch: str = "preview/candidate"):
    return dict(
        delivery_target=dict(
            mode="open_pr_candidate", repository=repository,
            branch=branch, sha=sha, candidate_pr_number=56,
        )
    )


with psycopg.connect(DSN, autocommit=True) as db:
    db.execute(schema)
    db.execute(migration)

    for function in (
        "factory_scheduler_queue_signals",
        "factory_claim_change_set_integration",
    ):
        row = db.execute("""
            select p.prosecdef,
                   has_function_privilege('service_role',p.oid,'execute'),
                   has_function_privilege('anon',p.oid,'execute'),
                   has_function_privilege('authenticated',p.oid,'execute')
            from pg_proc p join pg_namespace n on n.oid=p.pronamespace
            where n.nspname='public' and p.proname=%s
        """, (function,)).fetchone()
        assert row == (False, True, False, False), (function, row)

    def signals():
        result = db.execute(
            "select public.factory_scheduler_queue_signals()"
        ).fetchone()[0]
        assert isinstance(result["integration_work"], bool), result
        assert type(result["stale_integration_change_sets"]) is int, result
        return result

    def claim():
        return db.execute(
            "select public.factory_claim_change_set_integration(%s,%s)",
            ("qa-claim", 300),
        ).fetchone()[0]

    def create_project(key: str, kind: str, source_sha: str,
                       repository: str = "test/crm"):
        project_id, cs_id, task_id, unit_id = [uuid.uuid4() for _ in range(4)]
        manifest = target(source_sha, repository) if kind == "existing" else {}
        db.execute("""
            insert into public.factory_projects(
                id,project_key,repository,project_kind,is_active,manifest
            ) values(%s,%s,%s,%s,true,%s::jsonb)
        """, (project_id, key, repository, kind, json.dumps(manifest)))
        db.execute("""
            insert into public.factory_project_execution_controls(
                project_id,state,generation
            ) values(%s,'running',1)
        """, (project_id,))
        db.execute("""
            insert into public.factory_tasks(id,project_id,status)
            values(%s,%s,'completed')
        """, (task_id,project_id))
        db.execute("""
            insert into public.factory_change_sets(
                id,project_id,status,source_commit,candidate_commit,
                current_wave,attempt_count,integration_branch
            ) values(%s,%s,'building',%s,%s,1,0,%s)
        """, (cs_id,project_id,source_sha,source_sha,"factory/change-set-" + str(cs_id)[:8]))
        db.execute("""
            insert into public.factory_change_set_work_units(
                id,change_set_id,wave,status,task_id,plan_task_key,
                agent_key,base_commit,branch_name,output_commit,changed_files
            ) values(%s,%s,1,'completed',%s,'editor','ui',%s,%s,%s,%s::jsonb)
        """, (unit_id,cs_id,task_id,source_sha,
              "factory/work-" + str(unit_id)[:8], "f" * 40,
              json.dumps(["src/components/automations/NewAutomationModal.tsx"])))
        return project_id, cs_id, unit_id

    old_sha, new_sha = "a" * 40, "b" * 40
    project_id, old_cs, unit_id = create_project("crm", "existing", old_sha)

    # Preserve the currently deployed Codex manual-only readiness signal.
    # The source SQL was older than the live function; without this contract,
    # queued autonomous codex routes could trigger manual handoff incorrectly.
    manual_task, manual_run = uuid.uuid4(), uuid.uuid4()
    db.execute(
        "insert into public.factory_tasks(id,project_id,status) values(%s,%s,'queued_execution')",
        (manual_task,project_id),
    )
    db.execute("""
        insert into public.factory_runs(id,task_id,status,execution_route,metadata)
        values(%s,%s,'queued','codex',%s::jsonb)
    """,(manual_run,manual_task,json.dumps({"codex_execution_mode":"autonomous"})))
    assert signals()["codex_manual_work"] is False
    db.execute(
        "update public.factory_runs set metadata=%s::jsonb where id=%s",
        (json.dumps({"codex_execution_mode":"manual"}), manual_run),
    )
    assert signals()["codex_manual_work"] is True
    db.execute(
        "update public.factory_runs set execution_route='direct' where id=%s",
        (manual_run,),
    )
    assert signals()["codex_manual_work"] is False
    db.execute(
        "update public.factory_runs set status='awaiting_codex_manual' where id=%s",
        (manual_run,),
    )
    assert signals()["codex_manual_work"] is True
    db.execute(
        "update public.factory_runs set status='completed' where id=%s",
        (manual_run,),
    )
    assert signals()["codex_manual_work"] is False

    # A single legitimate completed wave is advertised and can be claimed.
    before = signals()
    assert before["integration_work"] is True, before
    assert before["stale_integration_change_sets"] == 0, before
    claimed = claim()
    assert claimed is not None and claimed["change_set_id"] == str(old_cs), claimed
    assert claimed["current_wave"] == 1, claimed
    assert claimed["work_units"][0]["work_unit_id"] == str(unit_id), claimed
    assert db.execute("""
        select status,attempt_count,lease_owner is not null
        from public.factory_change_sets where id=%s
    """, (old_cs,)).fetchone() == ("integrating", 1, True)
    assert claim() is None, "live lease must not be double-claimed"

    # Simulate only a completed run's prior job having failed AFTER the
    # Work Unit was persisted; resume its unclaimed integration wave.
    db.execute("""
        update public.factory_change_sets set
        status='building',attempt_count=0,lease_owner=null,lease_expires_at=null
        where id=%s
    """, (old_cs,))

    # CRM Preview HEAD advanced through a separate nonproduction human merge.
    # Historical code is still auditable, but is not now a writable candidate.
    db.execute(
        "update public.factory_projects set manifest=%s::jsonb where id=%s",
        (json.dumps(target(new_sha)), project_id),
    )
    stale = signals()
    assert stale["integration_work"] is False, stale
    assert stale["stale_integration_change_sets"] == 1, stale
    for _ in range(3):
        assert claim() is None, "stale candidate incorrectly claimed"
    historical = db.execute("""
        select status,source_commit,candidate_commit,attempt_count,
               lease_owner,lease_expires_at from public.factory_change_sets
        where id=%s
    """, (old_cs,)).fetchone()
    assert historical == ("building",old_sha,old_sha,0,None,None), historical
    assert db.execute("""
        select status,base_commit,output_commit from public.factory_change_set_work_units
        where id=%s
    """, (unit_id,)).fetchone() == ("completed",old_sha,"f"*40)

    # A stale older Change Set must not starve a newer eligible project.
    fresh_sha = "c" * 40
    fresh_project, fresh_cs, fresh_unit = create_project(
        "fresh", "existing", fresh_sha, "test/fresh"
    )
    mixed = signals()
    assert mixed["integration_work"] is True, mixed
    assert mixed["stale_integration_change_sets"] == 1, mixed
    next_claim = claim()
    assert next_claim is not None and next_claim["change_set_id"] == str(fresh_cs), next_claim
    assert next_claim["work_units"][0]["work_unit_id"] == str(fresh_unit), next_claim
    assert db.execute(
        "select attempt_count from public.factory_change_sets where id=%s",
        (old_cs,),
    ).fetchone() == (0,), "a stale candidate consumed a retry"

    # Paused, unfinished, over-retried, off-policy Preview branch and inactive
    # projects must all fail closed without a claim or retry increment.
    db.execute("""
        update public.factory_change_sets set
        status='building',attempt_count=0,lease_owner=null,lease_expires_at=null
        where id=%s
    """, (fresh_cs,))
    db.execute(
        "update public.factory_project_execution_controls set state='paused' where project_id=%s",
        (fresh_project,),
    )
    assert signals()["integration_work"] is False
    assert claim() is None
    db.execute(
        "update public.factory_project_execution_controls set state='running' where project_id=%s",
        (fresh_project,),
    )
    db.execute(
        "update public.factory_change_set_work_units set status='queued' where id=%s",
        (fresh_unit,),
    )
    assert signals()["integration_work"] is False
    assert claim() is None
    db.execute(
        "update public.factory_change_set_work_units set status='completed' where id=%s",
        (fresh_unit,),
    )
    db.execute(
        "update public.factory_change_sets set attempt_count=3 where id=%s",
        (fresh_cs,),
    )
    assert signals()["integration_work"] is False
    assert claim() is None
    db.execute(
        "update public.factory_change_sets set attempt_count=0 where id=%s",
        (fresh_cs,),
    )
    db.execute(
        "update public.factory_projects set manifest=%s::jsonb where id=%s",
        (json.dumps(target(fresh_sha,"test/fresh","main")), fresh_project),
    )
    assert signals()["integration_work"] is False
    assert claim() is None
    db.execute(
        "update public.factory_projects set manifest=%s::jsonb where id=%s",
        (json.dumps(target(fresh_sha,"test/fresh")), fresh_project),
    )
    db.execute(
        "update public.factory_projects set is_active=false where id=%s",
        (fresh_project,),
    )
    assert signals()["integration_work"] is False
    assert claim() is None

    # Greenfield has no pinned external PR, and must remain eligible.
    _, greenfield_cs, _ = create_project("new", "greenfield", "d"*40, "test/new")
    assert signals()["integration_work"] is True
    greenfield_claim = claim()
    assert greenfield_claim is not None, greenfield_claim
    assert greenfield_claim["change_set_id"] == str(greenfield_cs), greenfield_claim
    assert signals()["stale_integration_change_sets"] == 1

    # Final state proves old Work Unit is retained, not silently "integrated".
    assert db.execute("""
        select status,attempt_count from public.factory_change_sets where id=%s
    """, (old_cs,)).fetchone() == ("building",0)

print("STALE_CHANGE_SET_GUARD_POSTGRES_PASS")
