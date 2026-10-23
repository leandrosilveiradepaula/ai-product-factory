"""Prove actual runtime stage receipt persistence in disposable PostgreSQL16.

Runs after verify_greenfield_planning_decision_postgres.py; reuses only its
isolated service DB schema. Never connects to Supabase production.
"""
from __future__ import annotations
import json
import os
import uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import psycopg
from psycopg.conninfo import conninfo_to_dict

dsn=os.environ.get("FACTORY_GREENFIELD_PG_TEST_DSN","")
d=conninfo_to_dict(dsn)
if (os.environ.get("FACTORY_GREENFIELD_PG_TEST_ISOLATED")!="true"
    or d.get("host")!="127.0.0.1" or d.get("port")!="5432"
    or d.get("dbname")!="factory_greenfield_test" or d.get("user")!="factory_ci"):
    raise SystemExit("REFUSING_NON_ISOLATED_STAGE_DATABASE")

root=Path(__file__).resolve().parents[1]
sql=(root/"supabase/migrations/20261023145000_preserve_runtime_stage_evidence.sql").read_text()
sha="a"*40
typed={"reason_code":"planning_non_actionable","observed_model_response":True,
       "tasks_count":0,"decisions_count":0,"implementation_completed":False,
       "requires_scope_reconciliation":True,"assessed_commit":sha}
with psycopg.connect(dsn,autocommit=True) as db:
    db.execute(sql)
    acl=db.execute("""
     select has_function_privilege('service_role',p.oid,'execute'),
      has_function_privilege('anon',p.oid,'execute'),
      has_function_privilege('authenticated',p.oid,'execute'),p.prosecdef
     from pg_proc p where p.proname='factory_record_runtime_stage'
       and p.pronamespace='public'::regnamespace
    """).fetchone()
    assert acl==(True,False,False,False),acl
    project,task,run=(uuid.uuid4() for _ in range(3))
    db.execute("insert into public.factory_projects(id,project_kind) values(%s,'existing')",(project,))
    db.execute("insert into public.factory_tasks(id,project_id,status,title) values(%s,%s,'queued','fixture')",(task,project))
    db.execute("insert into public.factory_runs(id,task_id,status,metadata) values(%s,%s,'running',%s::jsonb)",
       (run,task,json.dumps({"continuation_request_id":"fixed","execution_generation":3})))
    db.execute("select public.factory_record_runtime_stage(%s,'planning','started','{}'::jsonb)",(run,))
    first=db.execute("select metadata from public.factory_runs where id=%s",(run,)).fetchone()[0]
    assert first["stage_evidence"]["planning"]["status"]=="started"
    assert first["continuation_request_id"]=="fixed"
    barrier=Barrier(2)
    def write(stage):
        with psycopg.connect(dsn,autocommit=True) as conn:
            barrier.wait(timeout=20)
            conn.execute("select public.factory_record_runtime_stage(%s,%s,'completed','{}'::jsonb)",(run,stage))
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(write,stage) for stage in ("reconciliation","gap_analysis")]
        for future in futures: future.result(timeout=35)
    db.execute("select public.factory_record_runtime_stage(%s,'planning','failed',%s::jsonb)",
       (run,json.dumps(typed)))
    final=db.execute("select metadata from public.factory_runs where id=%s",(run,)).fetchone()[0]
    assert set(final["stage_evidence"])=={"reconciliation","gap_analysis","planning"},final
    assert final["stage_evidence"]["planning"]["output"]==typed
    db.execute("update public.factory_runs set status='failed',metadata=metadata||jsonb_build_object('error','planning has no actionable tasks or decisions') where id=%s",(run,))
    after=db.execute("select metadata from public.factory_runs where id=%s",(run,)).fetchone()[0]
    assert after["stage_evidence"]["planning"]["output"]==typed
    audits=db.execute("select payload from public.factory_audit_events where run_id=%s and event_type='run.stage.recorded'",(run,)).fetchall()
    assert len(audits)==4 and all(set(x[0])=={"stage","status"} for x in audits),audits
    malformed=uuid.uuid4()
    db.execute("insert into public.factory_runs(id,task_id,status,metadata) values (%s,%s,'running',%s::jsonb)",(malformed,task,json.dumps({"stage_evidence":["invalid"]})))
    try:
        db.execute("select public.factory_record_runtime_stage(%s,'planning','started','{}'::jsonb)",(malformed,))
    except psycopg.Error as exc:
        assert exc.sqlstate=="PT409",exc
    else: raise AssertionError("malformed parent was accepted")
    assert db.execute("select metadata->'stage_evidence' from public.factory_runs where id=%s",(malformed,)).fetchone()[0]==["invalid"]
print("RUNTIME_STAGE_EVIDENCE_POSTGRES_PASS")
