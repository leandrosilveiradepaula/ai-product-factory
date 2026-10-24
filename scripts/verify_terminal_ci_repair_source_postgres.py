#!/usr/bin/env python3
"""Prove terminal CI repair settlement only against disposable local PostgreSQL."""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict

dsn = os.getenv("FACTORY_REPAIR_SETTLEMENT_DSN", "")
cfg = conninfo_to_dict(dsn)
if (os.getenv("FACTORY_REPAIR_SETTLEMENT_ISOLATED") != "true"
    or cfg.get("host") not in ("127.0.0.1", "localhost")
    or cfg.get("dbname") != "factory_repair_settlement_test"
    or cfg.get("user") != "factory_ci"):
    raise SystemExit("REFUSING_NON_ISOLATED_REPAIR_SETTLEMENT_DATABASE")

root = Path(__file__).resolve().parents[1]
migration = (root / "supabase/migrations/"
             "20261024162500_settle_terminal_ci_repair_sources.sql").read_text()
schema = """
create role service_role nologin;
create role anon nologin;
create role authenticated nologin;
create table public.factory_projects (
 id uuid primary key, project_key text not null, project_kind text not null,
 is_active boolean not null
);
create table public.factory_project_execution_controls (
 project_id uuid primary key references public.factory_projects(id),
 state text not null, generation bigint not null
);
create table public.factory_tasks (
 id uuid primary key, project_id uuid not null references public.factory_projects(id),
 status text not null
);
create table public.factory_runs (
 id uuid primary key, task_id uuid not null references public.factory_tasks(id),
 status text not null, candidate_commit text, metadata jsonb not null default '{}'::jsonb,
 lease_owner text, finished_at timestamptz
);
create table public.factory_change_sets (
 id uuid primary key, project_id uuid not null references public.factory_projects(id),
 release_run_id uuid references public.factory_runs(id), candidate_commit text,
 status text not null, lease_owner text
);
create table public.factory_ci_repair_requests (
 id uuid primary key, project_id uuid references public.factory_projects(id),
 change_set_id uuid references public.factory_change_sets(id),
 source_run_id uuid references public.factory_runs(id),
 release_run_id uuid references public.factory_runs(id),
 original_candidate_commit text, repaired_commit text,
 execution_generation bigint not null, status text not null,
 lease_owner text, created_at timestamptz not null default now()
);
create table public.factory_audit_events (
 id bigint generated always as identity primary key,
 project_id uuid,task_id uuid,run_id uuid,actor_type text,actor_ref text,
 event_type text,payload jsonb
);
"""

project_id, task_id, source_id, release_id, cs_id, repair_id = (uuid.uuid4() for _ in range(6))
old_sha = "a" * 40
new_sha = "b" * 40
generation = 10
source_metadata = json.dumps({
 "source": "change-set", "change_set_id": str(cs_id),
 "ci_repair_request_id": str(repair_id), "execution_generation": generation
})
release_metadata = json.dumps({
 "source": "change-set", "change_set_id": str(cs_id), "execution_generation": generation
})


def observe(db: psycopg.Connection):
    receipt = db.execute(
        "select public.factory_settle_terminal_ci_repair_sources_v1(%s)", (3,)
    ).fetchone()[0]
    assert receipt["max_items"] == 3, receipt
    assert receipt["release_authorized"] is False, receipt
    assert receipt["paid_model_calls"] == 0, receipt
    return receipt


with psycopg.connect(dsn, autocommit=True) as db:
    db.execute(schema)
    db.execute(migration)
    privileges = db.execute("""
      select prosecdef,
        has_function_privilege('service_role',oid,'execute'),
        has_function_privilege('anon',oid,'execute'),
        has_function_privilege('authenticated',oid,'execute')
      from pg_proc where proname='factory_settle_terminal_ci_repair_sources_v1'
    """).fetchone()
    assert privileges == (False, True, False, False), privileges
    db.execute(
        "insert into factory_projects values (%s,'crm-test','existing',true)", (project_id,)
    )
    db.execute(
        "insert into factory_project_execution_controls values (%s,'running',%s)",
        (project_id, generation),
    )
    db.execute("insert into factory_tasks values (%s,%s,'completed')", (task_id, project_id))
    db.execute(
        "insert into factory_runs values (%s,%s,'repair_pending',%s,%s::jsonb,null,null)",
        (source_id,task_id,old_sha,source_metadata),
    )
    db.execute(
        "insert into factory_runs values (%s,%s,'integrated',%s,%s::jsonb,null,null)",
        (release_id,task_id,new_sha,release_metadata),
    )
    db.execute(
        "insert into factory_change_sets values (%s,%s,%s,%s,'completed',null)",
        (cs_id,project_id,release_id,new_sha),
    )
    db.execute(
        "insert into factory_ci_repair_requests"
        " values (%s,%s,%s,%s,%s,%s,%s,%s,'passed',null,now())",
        (repair_id,project_id,cs_id,source_id,release_id,old_sha,new_sha,generation),
    )

    def still_pending():
        status,finished = db.execute(
            "select status,finished_at from factory_runs where id=%s",(source_id,)
        ).fetchone()
        assert status == "repair_pending" and finished is None, (status,finished)
        assert observe(db)["status"] == "idle"

    # An incorrect receipt cannot be used to erase unfinished work.
    db.execute("update factory_project_execution_controls set generation=11 where project_id=%s",(project_id,))
    still_pending()
    db.execute("update factory_project_execution_controls set generation=10 where project_id=%s",(project_id,))
    db.execute("update factory_tasks set status='running' where id=%s",(task_id,))
    still_pending()
    db.execute("update factory_tasks set status='completed' where id=%s",(task_id,))
    db.execute("update factory_runs set lease_owner='active-worker' where id=%s",(source_id,))
    still_pending()
    db.execute("update factory_runs set lease_owner=null where id=%s",(source_id,))
    db.execute("update factory_ci_repair_requests set status='ci_failed' where id=%s",(repair_id,))
    still_pending()
    db.execute("update factory_ci_repair_requests set status='passed' where id=%s",(repair_id,))
    db.execute("update factory_change_sets set candidate_commit=%s where id=%s",(old_sha,cs_id))
    still_pending()
    db.execute("update factory_change_sets set candidate_commit=%s where id=%s",(new_sha,cs_id))
    db.execute("update factory_runs set status='ci_pending' where id=%s",(release_id,))
    still_pending()
    db.execute("update factory_runs set status='integrated' where id=%s",(release_id,))
    db.execute("update factory_runs set status='failed_gate' where id=%s",(source_id,))
    assert observe(db)["status"] == "idle"
    db.execute("update factory_runs set status='repair_pending' where id=%s",(source_id,))

    # Locked rows must be skipped rather than double-settled.
    with psycopg.connect(dsn,autocommit=False) as held:
        held.execute("select id from factory_ci_repair_requests where id=%s for update",(repair_id,))
        still_pending()
        held.rollback()

    good = observe(db)
    assert good["status"] == "settled" and good["settled"] == 1, good
    source = db.execute(
        "select status,finished_at,metadata from factory_runs where id=%s",(source_id,)
    ).fetchone()
    assert source[0] == "completed" and source[1] is not None, source
    assert source[2]["ci_repair_request_id"] == str(repair_id), source
    again = observe(db)
    assert again["status"] == "idle" and again["settled"] == 0, again
    audits = db.execute("""
      select payload from factory_audit_events
      where event_type='ci.repair.source_terminal_settled'
    """).fetchall()
    assert len(audits) == 1 and audits[0][0]["repair_request_id"] == str(repair_id), audits
    assert db.execute("select status from factory_change_sets where id=%s",(cs_id,)).fetchone()[0] == "completed"
    assert db.execute("select status from factory_runs where id=%s",(release_id,)).fetchone()[0] == "integrated"
    try:
        with db.transaction():
            db.execute("select public.factory_settle_terminal_ci_repair_sources_v1(0)")
    except psycopg.Error:
        pass
    else:
        raise AssertionError("unbounded settlement was accepted")
    print(json.dumps({"status": "pass", "settled": 1,
        "replay_settled": 0, "malformed_or_live_rejected": True,
        "migration_acl_enforced": True, "audit_events": len(audits),
        "paid_model_calls": 0, "production_modified": False}))
