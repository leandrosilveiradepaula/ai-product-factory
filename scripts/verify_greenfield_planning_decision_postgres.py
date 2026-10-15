"""Isolated PostgreSQL regression for greenfield planning-decision resume.

Runs only against a known disposable GitHub Actions service DB. No production
connections, credentials, model invocations or migrations are attempted.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase/migrations/20261015210000_greenfield_planning_decision_resume.sql"


def require_isolated_dsn() -> str:
    if os.environ.get("FACTORY_GREENFIELD_PG_TEST_ISOLATED") != "true":
        raise RuntimeError("isolated PostgreSQL test opt-in is required")
    dsn = os.environ.get("FACTORY_GREENFIELD_PG_TEST_DSN", "")
    parts = conninfo_to_dict(dsn)
    if (parts.get("host") != "127.0.0.1"
            or parts.get("port") != "5432"
            or parts.get("dbname") != "factory_greenfield_test"
            or parts.get("user") != "factory_ci"):
        raise RuntimeError("refusing non-isolated PostgreSQL connection")
    return dsn


SCHEMA = """
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='service_role')
 THEN CREATE ROLE service_role NOLOGIN; END IF;
END $$;
CREATE TABLE public.factory_projects(
 id uuid primary key, project_kind text not null,
 lifecycle_stage text default 'planning', manifest jsonb default '{}'::jsonb,
 updated_at timestamptz default now()
);
CREATE TABLE public.factory_tasks(
 id uuid primary key default gen_random_uuid(), project_id uuid not null,
 parent_task_id uuid, external_key text, title text, description text,
 status text not null, complexity text, risk jsonb, acceptance_criteria jsonb,
 depends_on jsonb, updated_at timestamptz default now(),
 unique(project_id,external_key)
);
CREATE TABLE public.factory_runs(
 id uuid primary key default gen_random_uuid(), task_id uuid not null,
 status text not null, metadata jsonb default '{}'::jsonb,
 execution_route text, attempt_count integer default 0,
 finished_at timestamptz
);
CREATE TABLE public.factory_human_gates(
 id uuid primary key default gen_random_uuid(), run_id uuid not null,
 gate_type text, status text, reasons jsonb,
 resolved_at timestamptz, resolved_by text, resolution jsonb
);
CREATE TABLE public.factory_decisions(
 id uuid primary key default gen_random_uuid(), project_id uuid,
 task_id uuid, decision_type text, question text, decision jsonb, decided_by text
);
CREATE TABLE public.factory_audit_events(
 id uuid primary key default gen_random_uuid(), project_id uuid,
 task_id uuid, run_id uuid, actor_type text, actor_ref text,
 event_type text, payload jsonb
);
"""


def seed_project(conn: psycopg.Connection, kind: str) -> str:
    project = str(uuid.uuid4())
    conn.execute("insert into public.factory_projects(id,project_kind) values(%s,%s)", (project, kind))
    return project


def seed_decision(conn: psycopg.Connection, project: str, status: str = "pending"):
    task, run, gate = [str(uuid.uuid4()) for _ in range(3)]
    conn.execute(
        "insert into public.factory_tasks(id,project_id,external_key,title,status) "
        "values(%s,%s,%s,'Decidir escopo','awaiting_human')",
        (task, project, "decision-" + task),
    )
    conn.execute(
        "insert into public.factory_runs(id,task_id,status,metadata) "
        "values(%s,%s,'awaiting_human',%s::jsonb)",
        (run, task, '{"decision_only":true}'),
    )
    conn.execute(
        "insert into public.factory_human_gates(id,run_id,gate_type,status,reasons) "
        "values(%s,%s,'planning_decision',%s,'[]'::jsonb)",
        (gate, run, status),
    )
    return task, run, gate


def seed_old_continuation(conn: psycopg.Connection, project: str, gate: str, *, attempts: int = 0):
    task, run = [str(uuid.uuid4()) for _ in range(2)]
    conn.execute(
        "insert into public.factory_tasks(id,project_id,external_key,title,status) "
        "values(%s,%s,%s,'Antiga reconciliação','queued')",
        (task, project, "prior-" + task),
    )
    conn.execute(
        "insert into public.factory_runs(id,task_id,status,attempt_count,metadata) "
        "values(%s,%s,'created',%s,jsonb_build_object("
        "'source','planning-decision','stages',"
        "jsonb_build_array('reconciliation','gap_analysis','planning'),"
        "'reconcile_first',true,'decision_gate_id',%s::text))",
        (run, task, attempts, gate),
    )
    return task, run


def metadata(conn: psycopg.Connection, run: str) -> dict:
    result = conn.execute("select metadata from public.factory_runs where id=%s", (run,)).fetchone()
    assert result is not None
    return result["metadata"]


def run_check() -> None:
    dsn = require_isolated_dsn()
    with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as conn:
        conn.execute(SCHEMA)
        green = seed_project(conn, "greenfield")
        existing = seed_project(conn, "existing")
        _, _, approved = seed_decision(conn, green, "approved")
        _, old_green = seed_old_continuation(conn, green, approved)
        _, old_claimed = seed_old_continuation(conn, green, approved, attempts=1)
        _, _, existing_approved = seed_decision(conn, existing, "approved")
        _, old_existing = seed_old_continuation(conn, existing, existing_approved)

        sql = MIGRATION.read_text(encoding="utf-8")
        conn.execute(sql)

        assert metadata(conn, old_green)["stages"] == ["planning"]
        assert metadata(conn, old_green)["reconcile_first"] is False
        assert metadata(conn, old_claimed)["stages"] == ["reconciliation", "gap_analysis", "planning"]
        assert metadata(conn, old_existing)["stages"] == ["reconciliation", "gap_analysis", "planning"]
        audit = conn.execute(
            "select count(*) as n from public.factory_audit_events "
            "where run_id=%s and event_type='planning_decision.greenfield_stages_corrected'",
            (old_green,),
        ).fetchone()["n"]
        assert audit == 1

        # Reapply a new version of the same function; the backfill must not duplicate evidence.
        conn.execute(sql)
        audit = conn.execute(
            "select count(*) as n from public.factory_audit_events "
            "where run_id=%s and event_type='planning_decision.greenfield_stages_corrected'",
            (old_green,),
        ).fetchone()["n"]
        assert audit == 1

        for project, kind, expected in (
            (green, "greenfield", ["planning"]),
            (existing, "existing", ["reconciliation", "gap_analysis", "planning"]),
        ):
            _, _, gate = seed_decision(conn, project)
            result = conn.execute(
                "select public.factory_resolve_human_gate(%s,'approved','ci-operator',"
                "'Confirmado: respostas aprovadas') as result",
                (gate,),
            ).fetchone()["result"]
            assert result["resolution"] == "approved"
            run = result["resume_run_id"]
            assert metadata(conn, run)["stages"] == expected, (kind, metadata(conn, run))
            assert metadata(conn, run)["reconcile_first"] is (kind != "greenfield")
            assert result["next_state"] == (
                "planning_replan_queued" if kind == "greenfield" else "planning_reconciliation_queued"
            )
            row = conn.execute(
                "select status,attempt_count from public.factory_runs where id=%s", (run,)
            ).fetchone()
            assert row == {"status": "created", "attempt_count": 0}

        # The boundary stays closed: an approved planning decision must contain a human response.
        _, _, gate = seed_decision(conn, green)
        try:
            conn.execute(
                "select public.factory_resolve_human_gate(%s,'approved','ci-operator',null)",
                (gate,),
            )
        except psycopg.errors.RaiseException as exc:
            assert "planning decision requires an explicit response" in str(exc)
        else:
            raise AssertionError("empty approval was accepted")
    print("GREENFIELD_PLANNING_POSTGRES_PASS: corrected_backfill=1; existing_unchanged=true; gate_guard=true")


if __name__ == "__main__":
    run_check()
