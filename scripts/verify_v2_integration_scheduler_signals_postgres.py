#!/usr/bin/env python3
"""Isolated PostgreSQL proof that V2 scheduler wake matches integration claim.

Never connect to a live Control Plane; no GitHub or model API calls.
"""
from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict

dsn = os.environ.get("FACTORY_V2_SIGNAL_QA_DSN", "")
settings = conninfo_to_dict(dsn)
if (
    os.environ.get("FACTORY_V2_SIGNAL_QA_ISOLATED") != "true"
    or settings.get("host") not in ("127.0.0.1", "localhost")
    or settings.get("dbname") != "factory_v2_signals_qa"
    or settings.get("user") != "factory_ci"
):
    raise SystemExit("REFUSING_NON_ISOLATED_V2_SIGNAL_DATABASE")

path = (
    Path(__file__).resolve().parents[1]
    / "supabase/migrations/20261104155600_v2_integration_scheduler_signals.sql"
)
migration = path.read_text(encoding="utf-8")
SOURCE = "b1935c8f6e61ae246eb8958673b2a9e18c3da81f"
CANDIDATE = "e5eb59c1a56b0c922a5e0d1e956e8c442dff152b"
BRANCH = "factory/journey-bb14e150-2c7e-423b-8e5d-e211dab6225c"
LEGACY = "c" * 40
PROJECT = "2d30e00a-ff72-4044-b838-011c263ed672"
JOURNEY = "bb14e150-2c7e-423b-8e5d-e211dab6225c"
CS = "3f09952e-0384-46ee-97aa-a46c89346678"
REQUEST = "1c19ce32-b42a-9e0a-29af-0767474b9244"
POLICY = "c1e1b9c46c5e3d30ec9c9f69e340f3a15962c39aac0c38ca46180f106a495a79"

schema = """
create role service_role nologin;
create role anon nologin;
create role authenticated nologin;
create table public.factory_projects (
 id uuid primary key, project_key text, repository text,
 project_kind text, is_active boolean, manifest jsonb
);
create table public.factory_project_execution_controls (
 project_id uuid primary key, state text, generation integer
);
create table public.factory_tasks (
 id uuid primary key, project_id uuid, status text
);
create table public.factory_runs (
 id uuid primary key, task_id uuid, status text, execution_route text,
 metadata jsonb
);
create table public.factory_journeys (
 id uuid primary key, project_id uuid, request_id uuid, policy_digest text,
 state text, execution_generation integer, source_commit text, binding jsonb
);
create table public.factory_change_sets (
 id uuid primary key, project_id uuid, journey_id uuid, status text,
 attempt_count integer, lease_expires_at timestamptz, current_wave integer,
 source_commit text, candidate_commit text, integration_branch text
);
create table public.factory_change_set_work_units (
 id uuid primary key, change_set_id uuid, wave integer, status text
);
create table public.factory_specialist_lane_jobs (
 id uuid primary key, project_id uuid, status text, role text
);
"""

with psycopg.connect(dsn, autocommit=True) as db:
    db.execute(schema)
    db.execute(migration)

    acl = db.execute("""
       select prosecdef, has_function_privilege('service_role',oid,'EXECUTE'),
        has_function_privilege('anon',oid,'EXECUTE'),
        has_function_privilege('authenticated',oid,'EXECUTE')
       from pg_proc
       where proname='factory_scheduler_queue_signals'
         and pronamespace='public'::regnamespace
    """).fetchone()
    assert acl == (False, True, False, False), acl

    manifest = '{"delivery_target":{"mode":"open_pr_candidate","sha":"' + LEGACY + '","repository":"leandrosilveiradepaula/crm-infodive","branch":"preview/crm209-delivery-v4"}}'
    db.execute(
        "insert into public.factory_projects values (%s,'crm-infodive',%s,'existing',true,%s::jsonb)",
        (PROJECT, "leandrosilveiradepaula/crm-infodive", manifest),
    )
    db.execute(
        "insert into public.factory_project_execution_controls values (%s,'running',19)",
        (PROJECT,),
    )
    binding = {
       "journey_id": JOURNEY, "project_id": PROJECT,
       "request_id": REQUEST, "policy_digest": POLICY,
       "source_commit": SOURCE, "integration_branch": BRANCH,
    }
    import json
    db.execute(
        "insert into public.factory_journeys values (%s,%s,%s,%s,'executing',19,%s,%s::jsonb)",
        (JOURNEY, PROJECT, REQUEST, POLICY, SOURCE, json.dumps(binding)),
    )
    db.execute(
        "insert into public.factory_change_sets values (%s,%s,%s,'building',0,null,5,%s,%s,%s)",
        (CS, PROJECT, JOURNEY, SOURCE, CANDIDATE, BRANCH),
    )
    unit_id = uuid4()
    db.execute(
        "insert into public.factory_change_set_work_units values (%s,%s,5,'completed')",
        (unit_id, CS),
    )

    def signals():
        result = db.execute("select public.factory_scheduler_queue_signals()").fetchone()[0]
        assert type(result) is dict
        assert type(result["integration_work"]) is bool
        return result

    good = signals()
    assert good["integration_work"] is True, good
    assert good["stale_integration_change_sets"] == 0, good
    assert good["routed_execution_work"] is False
    assert good["product_work"] is False
    assert good["ci_work"] is False

    # V2 delivery identity must fail closed, not inherit legacy manifest target.
    tampered = dict(binding)
    tampered["policy_digest"] = "bad-policy"
    db.execute("update public.factory_journeys set binding=%s::jsonb where id=%s",
               (json.dumps(tampered), JOURNEY))
    assert signals()["integration_work"] is False
    db.execute("update public.factory_journeys set binding=%s::jsonb where id=%s",
               (json.dumps(binding), JOURNEY))
    assert signals()["integration_work"] is True

    for state in ("stopped", "pausing"):
        db.execute("update public.factory_project_execution_controls set state=%s where project_id=%s",
                   (state, PROJECT))
        assert signals()["integration_work"] is False, state
    db.execute("update public.factory_project_execution_controls set state='running',generation=20 where project_id=%s",
               (PROJECT,))
    assert signals()["integration_work"] is False, "epoch drift"
    db.execute("update public.factory_project_execution_controls set generation=19 where project_id=%s",
               (PROJECT,))

    db.execute("update public.factory_change_set_work_units set status='pending' where id=%s",
               (unit_id,))
    assert signals()["integration_work"] is False, "incomplete work unit"
    db.execute("update public.factory_change_set_work_units set status='completed' where id=%s",
               (unit_id,))
    db.execute("update public.factory_change_sets set candidate_commit=null where id=%s",
               (CS,))
    assert signals()["integration_work"] is False, "missing V2 candidate"
    db.execute("update public.factory_change_sets set candidate_commit=%s where id=%s",
               (CANDIDATE, CS))
    assert signals()["integration_work"] is True

    # A legacy Change Set with a stale manifest remains ineligible and appears
    # only in the diagnostic counter, never as executable integration.
    db.execute("update public.factory_change_sets set journey_id=null where id=%s",
               (CS,))
    legacy_stale = signals()
    assert legacy_stale["integration_work"] is False
    assert legacy_stale["stale_integration_change_sets"] == 1
    db.execute(
        "update public.factory_projects set manifest=jsonb_set(manifest,"
        " '{delivery_target,sha}',to_jsonb(%s::text)) where id=%s",
        (SOURCE, PROJECT),
    )
    legacy_pinned = signals()
    assert legacy_pinned["integration_work"] is True, legacy_pinned
    assert legacy_pinned["stale_integration_change_sets"] == 0

    db.execute("update public.factory_change_sets set journey_id=%s where id=%s",
               (JOURNEY, CS))
    db.execute("update public.factory_projects set is_active=false where id=%s",
               (PROJECT,))
    assert signals()["integration_work"] is False, "inactive project"
    print("V2_INTEGRATION_SCHEDULER_SIGNALS_POSTGRES=PASS")
    print("V2_LIVENESS_MATCH=TRUE LEGACY_DRIFT_BLOCKED=TRUE MODEL_CALLS=0 PRODUCTION_WRITES=0")
