#!/usr/bin/env python3
"""Adversarial CAS verification on a disposable PostgreSQL 16 database only."""
import json
import os
import uuid
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict

dsn = os.getenv("FACTORY_CANDIDATE_SWITCH_TEST_DSN", "")
cfg = conninfo_to_dict(dsn)
if (os.getenv("FACTORY_CANDIDATE_SWITCH_ISOLATED") != "true"
    or cfg.get("host") not in {"127.0.0.1", "localhost"}
    or cfg.get("dbname") != "factory_candidate_switch_test"):
    raise SystemExit("refusing non-isolated database")

OLD = "a" * 40
NEW = "b" * 40
BASE = "c" * 40
REPO = "leandrosilveiradepaula/crm-infodive"
OLD_BRANCH = "preview/hardening-release-candidate"
NEW_BRANCH = "preview/crm22-rbac-security-evidence"
project_id = uuid.uuid4()
request_id = "authorized-issue-22"

native = {
    "schema_version": 1, "event": "pull_request",
    "workflow_id": 372542929, "workflow_name": "CRM validation",
    "workflow_path": ".github/workflows/crm-validation.yml",
}
target = {
    "schema_version": 1, "mode": "open_pr_candidate",
    "repository": REPO, "branch": OLD_BRANCH, "sha": OLD,
    "candidate_pr_number": 56,
    "repin_policy": {
        "schema_version": 1, "enabled": True, "native_ci": native,
    },
}
manifest = {
    "delivery_target": target,
    "continuation_request": {
        "id": request_id, "source": "github-owner",
        "summary": "Concluir as pendências reais da issue #22 do CRM",
    },
}
evidence = {
    "source": "github_actions_exact_sha",
    "repository": REPO, "request_id": request_id, "issue_number": 22,
    "old_branch": OLD_BRANCH, "old_sha": OLD, "old_pr_number": 56,
    "new_branch": NEW_BRANCH, "new_sha": NEW, "new_pr_number": 202,
    "pr_head_sha": NEW, "branch_head_sha": NEW,
    "pr_base": "main", "pr_base_sha": BASE, "pr_state": "open",
    "compare_status": "ahead", "ahead_by": 1, "behind_by": 0,
    "ci_conclusion": "success", "ci_sha": NEW, "ci_run_id": 40865091633,
    "ci_workflow_id": 372542929, "ci_run_number": 1081,
    "ci_run_attempt": 1,
    "ci_workflow_path": native["workflow_path"],
    "ci_workflow_name": native["workflow_name"],
}

setup = """
create role service_role nologin;
create role anon nologin;
create role authenticated nologin;
create table public.factory_projects (
 id uuid primary key, project_key text unique, repository text,
 project_kind text, is_active boolean, manifest jsonb not null,
 updated_at timestamptz default now()
);
create table public.factory_project_execution_controls (
 project_id uuid primary key, state text, generation bigint,
 version bigint, updated_at timestamptz default now()
);
create table public.factory_tasks (
 id uuid primary key, project_id uuid, status text
);
create table public.factory_runs (
 id uuid primary key, task_id uuid, status text,
 lease_owner text, lease_expires_at timestamptz,
 metadata jsonb not null default '{}'::jsonb
);
create table public.factory_change_sets (
 id uuid primary key, project_id uuid, root_task_id uuid,
 status text, lease_owner text, lease_expires_at timestamptz
);
create table public.factory_audit_events (
 id bigint generated always as identity primary key,
 project_id uuid, actor_type text, actor_ref text,
 event_type text, payload jsonb
);
create function public.factory_control_quiescent(p_project_id uuid)
returns boolean language sql stable as $$
select not exists (
 select 1 from public.factory_runs r
 join public.factory_tasks t on t.id=r.task_id
 where t.project_id=p_project_id and r.lease_owner is not null
 and (r.lease_expires_at is null or r.lease_expires_at>now())
 and r.status not in ('completed','blocked','cancelled')
) and not exists (
 select 1 from public.factory_change_sets cs
 where cs.project_id=p_project_id and cs.lease_owner is not null
 and (cs.lease_expires_at is null or cs.lease_expires_at>now())
 and cs.status not in ('completed','blocked','cancelled')
)$$;
"""

migration = (Path(__file__).resolve().parents[1] /
             "supabase/migrations/20261029115000_replace_existing_nonproduction_candidate.sql"
            ).read_text()

with psycopg.connect(dsn, autocommit=True) as db:
    db.execute(setup)
    db.execute(migration)
    grants = db.execute("""
      select prosecdef,
       has_function_privilege('service_role',oid,'EXECUTE'),
       has_function_privilege('anon',oid,'EXECUTE'),
       has_function_privilege('authenticated',oid,'EXECUTE')
      from pg_proc where proname='factory_replace_nonproduction_candidate_v1'
    """).fetchone()
    assert grants == (False, True, False, False), grants

    db.execute("""
      insert into public.factory_projects
      (id,project_key,repository,project_kind,is_active,manifest)
      values (%s,'crm-infodive',%s,'existing',true,%s::jsonb)
    """, (project_id, REPO, json.dumps(manifest)))
    db.execute("""
      insert into public.factory_project_execution_controls
      (project_id,state,generation,version)
      values (%s,'running',13,12)
    """, (project_id,))

    def rpc(**overrides):
        values = dict(
            p_project_key="crm-infodive",
            p_expected_old_branch=OLD_BRANCH,
            p_expected_old_sha=OLD,
            p_expected_old_pr=56,
            p_new_branch=NEW_BRANCH,
            p_new_sha=NEW,
            p_new_pr=202,
            p_issue_number=22,
            p_expected_generation=13,
            p_expected_version=12,
            p_evidence=evidence,
            p_actor_ref="factory-candidate-switch",
        )
        values.update(overrides)
        return db.execute("""
          select public.factory_replace_nonproduction_candidate_v1(
            %(p_project_key)s, %(p_expected_old_branch)s,
            %(p_expected_old_sha)s, %(p_expected_old_pr)s,
            %(p_new_branch)s, %(p_new_sha)s, %(p_new_pr)s,
            %(p_issue_number)s, %(p_expected_generation)s,
            %(p_expected_version)s, %(p_evidence)s::jsonb,
            %(p_actor_ref)s
          )
        """, {**values, "p_evidence": json.dumps(values["p_evidence"])}).fetchone()[0]

    def current():
        return db.execute("""
          select p.manifest->'delivery_target',c.generation,c.version
          from public.factory_projects p
          join public.factory_project_execution_controls c
            on c.project_id=p.id
          where p.id=%s
        """, (project_id,)).fetchone()

    def rejected(**overrides):
        try:
            with db.transaction():
                rpc(**overrides)
        except psycopg.Error:
            assert current() == (target,13,12)
            assert db.execute("select count(*) from public.factory_audit_events").fetchone()[0] == 0
            return
        raise AssertionError("unsafe candidate switch accepted")

    rejected(p_expected_old_sha="d"*40)
    rejected(p_expected_generation=12)
    rejected(p_expected_version=11)
    rejected(p_new_branch=OLD_BRANCH)
    rejected(p_issue_number=23)
    rejected(p_new_pr=56)
    for key in (
        "source","repository","request_id","issue_number",
        "old_sha","old_branch","old_pr_number",
        "new_sha","new_branch","new_pr_number",
        "pr_head_sha","branch_head_sha","pr_base_sha",
        "ci_sha","ci_run_id","ci_workflow_id","ci_conclusion",
        "ci_workflow_path","ahead_by","behind_by",
    ):
        forged = dict(evidence)
        forged.pop(key)
        rejected(p_evidence=forged)
    for key, value in (
        ("ci_conclusion","failure"),("compare_status","diverged"),
        ("ci_sha",OLD),("ci_workflow_id",111),("behind_by",1),
        ("pr_base","preview"),("new_pr_number",56),
    ):
        rejected(p_evidence={**evidence, key:value})

    task_id = uuid.uuid4()
    db.execute(
        "insert into public.factory_tasks(id,project_id,status) values (%s,%s,'running')",
        (task_id, project_id),
    )
    run_id = uuid.uuid4()
    db.execute("""
      insert into public.factory_runs(id,task_id,status)
      values (%s,%s,'ci_pending')
    """, (run_id, task_id))
    rejected()
    db.execute("delete from public.factory_runs where id=%s",(run_id,))

    # Terminal history is exempt only when both its root and Change Set have
    # exact, completed, unleased provenance. Neither row may be rewritten.
    db.execute("update public.factory_tasks set status='completed' where id=%s",(task_id,))
    cs_id = uuid.uuid4()
    db.execute("""
      insert into public.factory_change_sets(
        id,project_id,root_task_id,status
      ) values (%s,%s,%s,'completed')
    """, (cs_id, project_id, task_id))
    history_id = uuid.uuid4()
    db.execute("""
      insert into public.factory_runs(
        id,task_id,status,metadata
      ) values (%s,%s,'repair_pending',%s::jsonb)
    """, (history_id,task_id,json.dumps({"change_set_id":str(cs_id)})))
    db.execute("update public.factory_tasks set status='running' where id=%s",(task_id,))
    rejected()
    db.execute("update public.factory_tasks set status='completed' where id=%s",(task_id,))

    result = rpc()
    assert result["status"]=="replaced",result
    new_target, generation, version = current()
    assert new_target["sha"]==NEW and new_target["branch"]==NEW_BRANCH
    assert new_target["candidate_pr_number"]==202
    assert new_target["repin_policy"]==target["repin_policy"]
    assert (generation,version)==(14,13)
    events = db.execute("""
      select event_type,payload from public.factory_audit_events
    """).fetchall()
    assert len(events)==1 and events[0][0]=="project.delivery_target.replaced"
    assert events[0][1]["old_pr_number"]==56
    assert events[0][1]["new_pr_number"]==202
    assert db.execute("""
      select status,lease_owner from public.factory_runs where id=%s
    """,(history_id,)).fetchone()==("repair_pending",None)
    try:
        with db.transaction():
            rpc()
    except psycopg.Error:
        pass
    else:
        raise AssertionError("replay accepted")
    print("EXISTING_CANDIDATE_SWITCH_POSTGRES_PASS")
