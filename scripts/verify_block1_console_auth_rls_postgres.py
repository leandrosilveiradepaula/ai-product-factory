#!/usr/bin/env python3
"""B2 real SQL RLS/role negative tests on isolated PostgreSQL ONLY.

Uses committed migrations, never a credential, live database or model call.
Does not certify production-signed JWT, routes, tenant broker or all tables.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from uuid import UUID

import psycopg
from psycopg.conninfo import conninfo_to_dict

ROOT = Path(__file__).resolve().parents[1]
POLICY_FILE = ROOT / "supabase/migrations/20260925232713_factory_console_auth_and_gate_resolution.sql"
ADMIN_FILE = ROOT / "supabase/migrations/20260925234331_factory_console_operator_admin.sql"
CUT = "create or replace function public.factory_record_dispatch_decision("
IDS = (
    UUID("11111111-1111-4111-8111-111111111111"),
    UUID("22222222-2222-4222-8222-222222222222"),
    UUID("33333333-3333-4333-8333-333333333333"),
    UUID("44444444-4444-4444-8444-444444444444"),
)


def require(ok: bool, error_code: str) -> None:
    if not ok:
        raise AssertionError(error_code)


def scoped_dsn() -> str:
    dsn = os.environ.get("FACTORY_CONTROL_TEST_DSN", "")
    try:
        cfg = conninfo_to_dict(dsn)
    except (ValueError, psycopg.Error):
        raise SystemExit("b2_isolated_dsn_invalid") from None
    if (os.environ.get("FACTORY_CONTROL_TEST_ISOLATED") != "true"
            or cfg.get("host") not in ("127.0.0.1", "localhost")
            or cfg.get("dbname") != "factory_project_control_test"
            or cfg.get("port") not in ("5432", None)
            or not cfg.get("user")
            or not dsn
            or set(cfg) - {"host", "port", "dbname", "user", "password"}):
        raise SystemExit("b2_isolated_postgres_only")
    return dsn


def policy_sql() -> str:
    source = POLICY_FILE.read_text(encoding="utf-8")
    require(source.count(CUT) == 1, "b2_auth_migration_cut_invalid")
    policy = source.split(CUT, 1)[0]
    for phrase in ("factory_console_operators", "enable row level security",
                   "revoke all on table", "grant select on table",
                   "create policy factory_console_operators_select_self",
                   "auth.uid()", "is_active = true"):
        require(phrase in policy, "b2_auth_migration_missing_guard")
    require("security definer" not in policy.lower(), "b2_auth_policy_bypass")
    return policy


def expect_denied(conn: psycopg.Connection, *, role: str,
                  sql: str, params: tuple = ()) -> None:
    require(role in ("anon", "authenticated"), "b2_unknown_role")
    try:
        with conn.transaction():
            conn.execute("SET LOCAL ROLE " + role)
            conn.execute(sql, params)
    except psycopg.Error as exc:
        require(exc.sqlstate == "42501", "b2_expected_privilege_denial")
    else:
        raise AssertionError("b2_unexpected_grant")


def rows_for_subject(conn: psycopg.Connection, *, subject: UUID | None) -> list[tuple]:
    with conn.transaction():
        if subject is not None:
            conn.execute("SELECT set_config('request.jwt.claim.sub', %s, true)",
                         (str(subject),))
        conn.execute("SET LOCAL ROLE authenticated")
        return conn.execute(
            "SELECT user_id,role,is_active FROM public.factory_console_operators ORDER BY user_id"
        ).fetchall()


def main() -> int:
    dsn = scoped_dsn()  # before any connection or SQL
    raw_policy = policy_sql()
    raw_admin = ADMIN_FILE.read_text(encoding="utf-8")
    require("revoke all on function public.factory_bootstrap_console_admin" in raw_admin,
            "b2_admin_migration_missing_revoke")
    require("revoke all on function public.factory_upsert_console_operator" in raw_admin,
            "b2_admin_migration_missing_revoke")
    cases = 0
    with psycopg.connect(dsn, autocommit=True) as conn:
        # Existing disposable PostgreSQL QA creates all three roles.
        for role in ("anon", "authenticated", "service_role"):
            require(conn.execute(
                "SELECT count(*)=1 FROM pg_roles WHERE rolname=%s", (role,)
            ).fetchone()[0], "b2_test_role_unavailable")

        conn.execute("CREATE SCHEMA auth")
        conn.execute("GRANT USAGE ON SCHEMA auth TO authenticated")
        conn.execute("CREATE TABLE auth.users(id uuid PRIMARY KEY)")
        conn.execute("""CREATE FUNCTION auth.uid() RETURNS uuid
            LANGUAGE sql STABLE
            AS $$SELECT nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$""")
        # Apply exact committed policy and admin SQL, not a weaker rewrite.
        conn.execute(raw_policy)
        conn.execute(raw_admin)

        for uid in IDS[:3]:
            conn.execute("INSERT INTO auth.users(id) VALUES (%s)", (uid,))
        for uid, role, active in (
            (IDS[0], "admin", True),
            (IDS[1], "operator", True),
            (IDS[2], "operator", False),
        ):
            conn.execute(
                "INSERT INTO public.factory_console_operators(user_id,role,is_active)"
                " VALUES (%s,%s,%s)", (uid, role, active)
            )

        permissions = conn.execute("""SELECT
            (SELECT relrowsecurity FROM pg_class
             WHERE oid='public.factory_console_operators'::regclass),
            NOT has_table_privilege('anon','public.factory_console_operators','SELECT'),
            has_table_privilege('authenticated','public.factory_console_operators','SELECT'),
            NOT has_table_privilege('authenticated','public.factory_console_operators','INSERT'),
            NOT has_table_privilege('authenticated','public.factory_console_operators','UPDATE'),
            NOT has_table_privilege('authenticated','public.factory_console_operators','DELETE')
        """).fetchone()
        require(all(permissions), "b2_table_rls_or_grant_violation")
        cases += len(permissions)

        policies = conn.execute("""SELECT roles::text,cmd,qual FROM pg_policies
            WHERE schemaname='public' AND tablename='factory_console_operators'""").fetchall()
        require(len(policies) == 1 and policies[0][0] == "{authenticated}"
                and policies[0][1] == "SELECT"
                and "auth.uid()" in policies[0][2]
                and "is_active" in policies[0][2],
                "b2_self_only_policy_invalid")
        cases += 1

        expect_denied(conn, role="anon",
                      sql="SELECT count(*) FROM public.factory_console_operators")
        cases += 1

        for subject, expected in (
            (None, []),
            (IDS[3], []),
            (IDS[0], [(IDS[0], "admin", True)]),
            (IDS[1], [(IDS[1], "operator", True)]),
            (IDS[2], []),
        ):
            require(rows_for_subject(conn, subject=subject) == expected,
                    "b2_subject_not_self_isolated")
            cases += 1

        for sql, params in (
            ("INSERT INTO public.factory_console_operators(user_id,role,is_active)"
             " VALUES (%s,'admin',true)", (IDS[3],)),
            ("UPDATE public.factory_console_operators SET role='admin' WHERE user_id=%s",
             (IDS[1],)),
            ("DELETE FROM public.factory_console_operators WHERE user_id=%s",
             (IDS[0],)),
        ):
            expect_denied(conn, role="authenticated", sql=sql, params=params)
            cases += 1

        functions = conn.execute("""SELECT proname,prosecdef,
            has_function_privilege('anon',oid,'EXECUTE'),
            has_function_privilege('authenticated',oid,'EXECUTE')
            FROM pg_proc WHERE oid IN (
              'public.factory_bootstrap_console_admin(uuid)'::regprocedure,
              'public.factory_upsert_console_operator(uuid,uuid,text,boolean)'::regprocedure
            ) ORDER BY proname""").fetchall()
        require(len(functions) == 2 and
                all(not row[1] and not row[2] and not row[3] for row in functions),
                "b2_operator_mutation_rpc_accessible")
        cases += 2

        expect_denied(conn, role="authenticated",
                      sql="SELECT public.factory_bootstrap_console_admin(%s)",
                      params=(IDS[3],))
        expect_denied(conn, role="anon",
                      sql="SELECT public.factory_bootstrap_console_admin(%s)",
                      params=(IDS[3],))
        cases += 2

    print(json.dumps({
        "schema": "factory-block1-b2-isolated-console-auth-v1",
        "scope": "isolated_sql_role_policy_not_production_jwt_or_full_tenant_auth",
        "cases_passed": cases,
        "policy_sha256": hashlib.sha256(raw_policy.encode()).hexdigest(),
        "admin_sha256": hashlib.sha256(raw_admin.encode()).hexdigest(),
        "production_writes": 0,
        "model_calls": 0,
        "all_authn_authz_certified": False,
        "all_data_boundaries_certified": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
