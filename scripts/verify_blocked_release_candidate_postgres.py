#!/usr/bin/env python3
"""Adversarial one-shot replay QA against disposable PostgreSQL 16 ONLY.

NEVER pass a hosted Supabase DSN. This is an offline local fixture with fake
project IDs, synthetic commits and no outbound calls or model execution.
"""
from __future__ import annotations

import copy
import json
import os
import uuid
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict

dsn = os.getenv("FACTORY_BLOCKED_CANDIDATE_TEST_DSN", "")
cfg = conninfo_to_dict(dsn)
if (os.getenv("FACTORY_BLOCKED_CANDIDATE_ISOLATED") != "true"
        or cfg.get("host") not in ("127.0.0.1", "localhost")
        or cfg.get("dbname") != "factory_blocked_candidate_test"
        or cfg.get("user") != "factory_ci"):
    raise SystemExit("refusing non-isolated candidate recovery PostgreSQL")

root = Path(__file__).resolve().parents[1]
migration = (root / "supabase/migrations"
             / "20261116152500_reconcile_blocked_release_candidate_once.sql").read_text()

PID = uuid.UUID("11111111-1111-1111-1111-111111111111")
CS = uuid.UUID("22222222-2222-2222-2222-222222222222")
RUN = uuid.UUID("33333333-3333-3333-3333-333333333333")
TASK = uuid.UUID("44444444-4444-4444-4444-444444444444")
ORIGINAL, PRIOR, NEW = "a"*40, "b"*40, "c"*40
BRANCH = "factory/change-set-22222222"
REPO = "example/product"

setup = """
create role service_role nologin;
create role anon nologin;
create role authenticated nologin;
create table public.factory_projects (
 id uuid primary key, project_kind text, repository text, is_active boolean);
create table public.factory_project_execution_controls (
 project_id uuid primary key, state text, generation bigint);
create table public.factory_tasks (
 id uuid primary key, project_id uuid, status text);
create table public.factory_runs (
 id uuid primary key, task_id uuid, status text, candidate_commit text,
 branch_name text, lease_owner text, lease_expires_at timestamptz,
 last_error text, finished_at timestamptz, metadata jsonb not null);
create table public.factory_change_sets (
 id uuid primary key, project_id uuid, release_run_id uuid, root_task_id uuid,
 status text, candidate_commit text, integration_branch text,
 lease_owner text, lease_expires_at timestamptz, current_wave int,
 metadata jsonb not null, updated_at timestamptz default now());
create table public.factory_release_reports (
 id uuid primary key, run_id uuid unique, status text,
 candidate_commit text, report jsonb not null);
create table public.factory_tool_usage (
 id bigint generated always as identity primary key,
 run_id uuid, tool_family text, operation text, usage_units numeric,
 estimated_cost numeric, metadata jsonb not null,
 created_at timestamptz default now());
create table public.factory_audit_events (
 id bigint generated always as identity primary key,
 project_id uuid, task_id uuid, run_id uuid,
 actor_type text, actor_ref text, event_type text, payload jsonb,
 created_at timestamptz default now());
create table public.factory_evaluations (
 id uuid primary key, run_id uuid, eval_type text, status text,
 baseline_ref text, result jsonb);
create table public.factory_specialist_lane_jobs (
 id uuid primary key, run_id uuid, status text,
 candidate_commit text, required boolean);
"""

create_receipt = {"pr": 2, "head_sha": ORIGINAL, "change_set_id": str(CS)}
previous_receipt = {
    "pr_number": 2, "previous_commit": ORIGINAL,
    "old_sha": ORIGINAL, "new_sha": PRIOR,
    "candidate_commit": PRIOR, "change_set_id": str(CS),
    "compare_status": "ahead",
}
csmeta = {
    "integration_release_request": {
        "branch": BRANCH, "candidate_commit": PRIOR,
        "issue_number": 1, "pr_number": 2,
    },
    "integration_epoch_receipt": {
        "generation": 1, "wave": 9,
        "project_id": str(PID), "candidate_commit": PRIOR,
    },
}
runmeta = {
    "source": "change-set", "change_set_id": str(CS),
    "execution_generation": 1,
    "specialist_lanes": {
        "roles": ["security", "qa", "operations"],
        "candidate_commit": PRIOR, "required": True,
    },
}
evidence = {
    "source": "github_actions_exact_sha", "repository": REPO,
    "pr_number": 2, "pr_head_sha": NEW,
    "branch_head_sha": NEW, "ci_sha": NEW,
    "prior_candidate_commit": PRIOR, "new_sha": NEW,
    "pr_state": "open", "pr_merged": False, "pr_draft": False,
    "pr_base": "main", "branch": BRANCH,
    "compare_status": "ahead", "ahead_by": 7, "behind_by": 0,
    "prior_compare_status": "ahead", "prior_ahead_by": 5,
    "prior_behind_by": 0, "ci_run_id": 123456,
    "original_head_sha": ORIGINAL, "old_sha": ORIGINAL,
    "ci_checks": [
        {"name": name, "app": "github-actions", "status": "completed",
         "conclusion": "success", "head_sha": NEW}
        for name in ("candidate", "tenant-rls-postgres")
    ],
}


with psycopg.connect(dsn, autocommit=True) as db:
    db.execute(setup)
    db.execute(migration)
    grants = db.execute("""
        select p.prosecdef,
            has_function_privilege('service_role',p.oid,'EXECUTE'),
            has_function_privilege('anon',p.oid,'EXECUTE'),
            has_function_privilege('authenticated',p.oid,'EXECUTE')
        from pg_proc p join pg_namespace n on n.oid=p.pronamespace
        where n.nspname='public'
          and p.proname='factory_reconcile_blocked_release_candidate_once_v1'
    """).fetchone()
    assert grants == (False, True, False, False), grants

    db.execute("""insert into public.factory_projects(id,project_kind,repository,is_active)
                  values (%s,'greenfield',%s,true)""", (PID, REPO))
    db.execute("""insert into public.factory_project_execution_controls
                  (project_id,state,generation) values(%s,'running',1)""", (PID,))
    db.execute("""insert into public.factory_tasks(id,project_id,status)
                  values(%s,%s,'integrated')""", (TASK, PID))
    db.execute("""insert into public.factory_runs
       (id,task_id,status,candidate_commit,branch_name,metadata)
       values(%s,%s,'release_policy_blocked',%s,%s,%s::jsonb)
    """, (RUN, TASK, PRIOR, BRANCH, json.dumps(runmeta)))
    db.execute("""insert into public.factory_change_sets
       (id,project_id,release_run_id,root_task_id,status,candidate_commit,
        integration_branch,current_wave,metadata)
       values(%s,%s,%s,%s,'ci_pending',%s,%s,9,%s::jsonb)
    """, (CS, PID, RUN, TASK, PRIOR, BRANCH, json.dumps(csmeta)))
    db.execute("""insert into public.factory_release_reports
       (id,run_id,status,candidate_commit,report)
       values(%s,%s,'blocked',%s,%s::jsonb)
    """, (uuid.uuid4(), RUN, PRIOR, json.dumps({
        "release_state": "blocked", "product_complete": False,
        "definition_of_done": {"ready": False}})))
    for name, details in (("create_pr", create_receipt),
                          ("reconcile_pr_candidate", previous_receipt)):
        db.execute("""insert into public.factory_tool_usage(
          run_id,tool_family,operation,usage_units,estimated_cost,metadata)
          values(%s,'github',%s,1,0,%s::jsonb)
        """, (RUN, name, json.dumps(details)))
    for name in ("github_ci", "quality_gate", "browser_e2e"):
        db.execute("""insert into public.factory_evaluations
          (id,run_id,eval_type,status,baseline_ref,result)
          values(%s,%s,%s,'success',%s,'{}'::jsonb)""",
                   (uuid.uuid4(), RUN, name, PRIOR))
    for role in ("security", "qa", "operations"):
        db.execute("""insert into public.factory_specialist_lane_jobs
          (id,run_id,status,candidate_commit,required)
          values(%s,%s,'passed',%s,true)""",
                   (uuid.uuid4(), RUN, PRIOR))

    def state():
        return db.execute("""
          select r.status,r.candidate_commit,
            r.metadata->'specialist_lanes',
            cs.status,cs.candidate_commit,
            cs.metadata#>>'{integration_release_request,candidate_commit}',
            rr.status,rr.candidate_commit,
            (select count(*) from public.factory_tool_usage),
            (select count(*) from public.factory_audit_events)
          from public.factory_runs r
          join public.factory_change_sets cs on cs.release_run_id=r.id
          join public.factory_release_reports rr on rr.run_id=r.id
          where r.id=%s
        """, (RUN,)).fetchone()

    def rpc(*, set_id=CS, run_id=RUN, pr=2, prior=PRIOR, new=NEW, proof=None):
        return db.execute("""
            select public.factory_reconcile_blocked_release_candidate_once_v1(
                %s::uuid,%s::uuid,%s::integer,%s::text,%s::text,%s::jsonb)
        """, (set_id, run_id, pr, prior, new,
              json.dumps(evidence if proof is None else proof))).fetchone()[0]

    def reject(**kwargs):
        baseline = state()
        try:
            with db.transaction():
                rpc(**kwargs)
        except psycopg.Error:
            assert state() == baseline, ("mutated after denied operation", kwargs)
            return
        raise AssertionError("unsafe blocked candidate recovery was accepted: "+str(kwargs))

    reject(pr=3)
    reject(prior=NEW)
    reject(new=PRIOR)
    reject(set_id=uuid.uuid4())
    reject(run_id=uuid.uuid4())
    for field in (
        "source", "repository", "pr_number", "pr_head_sha",
        "branch_head_sha", "ci_sha", "prior_candidate_commit",
        "old_sha", "new_sha", "original_head_sha", "ci_run_id",
        "ci_checks", "pr_base", "pr_state", "pr_draft", "pr_merged",
        "prior_compare_status", "compare_status", "behind_by",
        "prior_behind_by", "branch", "ahead_by", "prior_ahead_by",
    ):
        proof=copy.deepcopy(evidence)
        proof.pop(field)
        reject(proof=proof)
    for key, value in (
        ("pr_merged", True), ("pr_draft", True),
        ("pr_state", "closed"), ("pr_base", "development"),
        ("compare_status", "diverged"), ("behind_by", 1),
        ("prior_behind_by", 1), ("prior_candidate_commit", ORIGINAL),
        ("original_head_sha", PRIOR),
        ("ci_sha", PRIOR),
    ):
        reject(proof={**evidence, key:value})
    proof=copy.deepcopy(evidence)
    proof["ci_checks"][0]["conclusion"]="failure"
    reject(proof=proof)
    proof=copy.deepcopy(evidence)
    proof["ci_checks"][0]["head_sha"]=PRIOR
    reject(proof=proof)

    # Fail when one control-plane identity, epoch or release gate is revoked.
    for table, col, bad, good, key in (
        ("factory_runs", "status", "awaiting_release", "release_policy_blocked", "id"),
        ("factory_change_sets", "status", "completed", "ci_pending", "id"),
        ("factory_runs", "lease_owner", "another-worker", None, "id"),
        ("factory_change_sets", "lease_owner", "another-worker", None, "id"),
        ("factory_project_execution_controls", "state", "stopped", "running", "project_id"),
        ("factory_release_reports", "status", "ready_for_human_release", "blocked", "run_id"),
        ("factory_tasks", "status", "failed", "integrated", "id"),
    ):
        pk = PID if table=="factory_project_execution_controls" else (
            CS if table=="factory_change_sets" else
            TASK if table=="factory_tasks" else RUN)
        db.execute(f"update public.{table} set {col}=%s where {key}=%s", (bad, pk))
        reject()
        db.execute(f"update public.{table} set {col}=%s where {key}=%s", (good, pk))

    # A missing previous reconciliation cannot rewrite the immutable
    # original PR receipt to justify a different prior SHA.
    try:
        with db.transaction():
            db.execute("delete from public.factory_tool_usage where operation='reconcile_pr_candidate'")
            reject()
            # Restore the deliberately removed historical receipt.
            raise RuntimeError("fixture rollback")
    except RuntimeError as exc:
        if str(exc) != "fixture rollback":
            raise

    # Original blocked report, evaluations and specialists must persist.
    old_state = state()
    assert old_state[:2] == ("release_policy_blocked", PRIOR)
    assert old_state[-2:] == (2, 0)
    expected_original_count = db.execute("""
        select count(*) from public.factory_tool_usage
        where operation='create_pr' and metadata->>'head_sha'=%s
    """, (ORIGINAL,)).fetchone()[0]
    assert expected_original_count == 1

    # A nonprivileged role cannot invoke even a perfectly valid proof.
    for role in ("anon", "authenticated"):
        db.execute("set role "+role)
        try:
            rpc()
        except psycopg.errors.InsufficientPrivilege:
            pass
        else:
            raise AssertionError(role+" unexpectedly invoked privileged recovery RPC")
        finally:
            db.execute("reset role")
    assert state() == old_state

    receipt = rpc()
    assert receipt["status"] == "ci_pending", receipt
    assert receipt["candidate_commit"] == NEW
    assert receipt["previous_commit"] == PRIOR
    assert receipt["original_head_sha"] == ORIGINAL
    assert receipt["fresh_ci_required"] is True
    assert receipt["fresh_specialists_required"] is True
    assert receipt["fresh_preview_required"] is True
    assert receipt["release_authorized"] is False
    assert receipt["prior_evidence_preserved"] is True
    current=state()
    assert current[0:2]==("ci_pending",NEW),current
    assert current[2] is None, "prior specialist approval reused"
    assert current[3:6] == ("ci_pending",NEW,NEW),current
    assert current[6:8] == ("blocked",PRIOR), "old release report overwritten"
    assert current[-2:]==(3,1), "receipt or audit not atomically recorded"
    audit=db.execute("""
      select event_type,payload from public.factory_audit_events
      where run_id=%s order by id
    """,(RUN,)).fetchall()
    assert len(audit)==1 and audit[0][0]=="change_set.blocked_release_candidate.reconciled"
    assert audit[0][1]["release_authorized"] is False
    latest=db.execute("""
      select metadata from public.factory_tool_usage
      where run_id=%s and operation='reconcile_pr_candidate'
      order by created_at desc,id desc limit 1
    """,(RUN,)).fetchone()[0]
    assert latest["previous_commit"]==ORIGINAL and latest["old_sha"]==ORIGINAL
    assert latest["candidate_commit"]==NEW and latest["new_sha"]==NEW
    assert latest["prior_candidate_commit"]==PRIOR
    # All old source evidence must be untouched, never read as current-SHA PASS.
    old_evals=db.execute("""
      select count(*) from public.factory_evaluations
      where run_id=%s and baseline_ref=%s
    """,(RUN,PRIOR)).fetchone()[0]
    new_evals=db.execute("""
      select count(*) from public.factory_evaluations
      where run_id=%s and baseline_ref=%s
    """,(RUN,NEW)).fetchone()[0]
    prior_lanes=db.execute("""
      select count(*) from public.factory_specialist_lane_jobs
      where run_id=%s and candidate_commit=%s and status='passed'
    """,(RUN,PRIOR)).fetchone()[0]
    new_lanes=db.execute("""
      select count(*) from public.factory_specialist_lane_jobs
      where run_id=%s and candidate_commit=%s
    """,(RUN,NEW)).fetchone()[0]
    assert (old_evals,new_evals,prior_lanes,new_lanes)==(3,0,3,0)
    # Replay, including the exact same signature, must not create new audits.
    reject()
    assert state()==current
    print("BLOCKED_RELEASE_CANDIDATE_CAS_POSTGRES=PASS")
