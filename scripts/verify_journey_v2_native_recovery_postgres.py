"""Exercise native V2 recovery in disposable PostgreSQL only; never production."""
import hashlib
import os
from pathlib import Path
import psycopg
from psycopg.types.json import Jsonb

dsn=os.environ["FACTORY_JOURNEY_RECOVERY_TEST_DSN"]
if "localhost:5432/journey_binding_test" not in dsn:
    raise SystemExit("REFUSING_NON_ISOLATED_JOURNEY_RECOVERY_DATABASE")
root=Path(__file__).resolve().parents[1]
# Reuse exactly the V2 fixture schema without importing its executable body.
prefix=(root/"scripts/verify_journey_delivery_binding_postgres.py").read_text().split("with psycopg.connect",1)[0]
os.environ.setdefault("FACTORY_JOURNEY_BINDING_TEST_DSN",dsn)
ns={"__file__":str(root/"scripts/verify_journey_delivery_binding_postgres.py")}; exec(prefix,ns)
BASE, V2=ns["BASE"], ns["MIGRATION"]
# The preceding V2 verifier deliberately leaves service roles in the same
# disposable cluster.  Rebuild tables only; roles are cluster-global.
BASE=BASE.replace("create schema extensions; create extension pgcrypto with schema extensions;", "")
BASE=BASE.replace("create role service_role; create role authenticated; create role anon;", "")
RECOVERY=(root/"supabase/migrations/20261031120000_native_journey_v2_recovery.sql").read_text()
REQUEUE=(root/"supabase/migrations/20261031130000_v2_preflight_requeue_same_run.sql").read_text()
CHECKPOINT=(root/"supabase/migrations/20261031140000_v2_checkpoint_failure_requeue_once.sql").read_text()
EVENT_INTEGRITY=(root/"supabase/migrations/20261031141500_v2_recovery_retry_event_integrity.sql").read_text()
project, request, sha, policy, proof=ns["PROJECT"],ns["REQUEST"],ns["SHA"],ns["POLICY"],ns["PROOF"]

def call(cur,name,*args):
    cur.execute("select public."+name+"("+",".join(["%s"]*len(args))+")",args)
    return cur.fetchone()[0]

with psycopg.connect(dsn,autocommit=True) as db:
  with db.cursor() as cur:
    cur.execute("drop schema public cascade; create schema public")
    cur.execute(BASE)
    # The production task schema has this lifecycle timestamp; the older V2
    # fixture predates it, so model the real column before applying recovery.
    cur.execute("alter table public.factory_tasks add column updated_at timestamptz default now()")
    cur.execute(V2); cur.execute(RECOVERY); cur.execute(REQUEUE); cur.execute(CHECKPOINT); cur.execute(EVENT_INTEGRITY)
    manifest={"journey_delivery_binding_v2":{"enabled":True,"version":2,"digest":policy,"source_mode":"main_snapshot","preview_base_ref":"main","release_base_ref":"main"}}
    cur.execute("insert into factory_projects values(%s,'crm-infodive','leandrosilveiradepaula/crm-infodive',%s,true,'existing')",(project,Jsonb(manifest)))
    cur.execute("insert into factory_project_execution_controls values(%s,'running',16,1)",(project,))
    text="authorized recovery"; digest=hashlib.sha256(text.encode()).hexdigest()
    intake=call(cur,"factory_enqueue_journey_intake_v2","crm-infodive",text,request,"github-owner","github-owner","123",digest,"leandrosilveiradepaula/ai-product-factory",1055)
    journey=intake["journey_id"]
    call(cur,"factory_record_journey_source_evidence_v2",journey,"leandrosilveiradepaula/crm-infodive","main",sha,policy,proof,16)
    binding={"journey_id":journey,"project_id":project,"request_id":request,"execution_generation":16,"policy_version":2,"policy_digest":policy,"repository":"leandrosilveiradepaula/crm-infodive","source_repository":"leandrosilveiradepaula/crm-infodive","source_commit":sha,"source_ref":"main","source_mode":"main_snapshot","integration_branch":"factory/journey-"+journey,"preview_branch_prefix":"preview/journey-"+journey[:8],"preview_base_ref":"main","release_base_ref":"main","binding_version":2,"source_proof_digest":proof}
    bound=call(cur,"factory_bind_journey_source_v2","crm-infodive",request,16,2,Jsonb(binding))
    recon={"summary":"durable baseline"}; gap={"recommended_next_work":["implement"]}
    metadata={"stages":["reconciliation","gap_analysis","planning"],"execution_generation":16,"journey_binding_v2":binding,"journey_request":{"text":text,"digest":digest},"error":"planning has no actionable tasks or decisions","stage_evidence":{"reconciliation":{"output":recon},"gap_analysis":{"output":gap}}}
    cur.execute("update factory_runs set status='failed',metadata=%s where id=%s",(Jsonb(metadata),bound["run_id"]))
    cur.execute("update factory_tasks set status='failed' where id=%s",(bound["task_id"],))
    first=call(cur,"factory_resume_failed_journey_v2",journey)
    assert first["created"] is True and first["generation"]==16
    second=call(cur,"factory_resume_failed_journey_v2",journey)
    assert second["created"] is False and second["run_id"]==first["run_id"]
    cur.execute("select journey_id,task_id,source_commit,metadata from factory_runs where id=%s",(first["run_id"],))
    jid,tid,stored_sha,md=cur.fetchone()
    assert str(jid)==journey and str(tid)==bound["task_id"] and stored_sha==sha
    assert md["resume_checkpoint"]["source_run_id"]==bound["run_id"] and md["journey_binding_v2"]==binding
    # Simulate both pre-provider failures on exactly the same durable recovery run.
    # Each failure class gets at most one same-run retry; no new run is minted.
    cur.execute("update factory_runs set status='failed', metadata=metadata || %s where id=%s",
                (Jsonb({"error":"planning_resume_provenance_preflight_failed"}),first["run_id"]))
    cur.execute("update factory_tasks set status='failed' where id=%s",(bound["task_id"],))
    preflight=call(cur,"factory_resume_failed_journey_v2",journey)
    assert preflight["created"] is True and preflight["requeued"] is True
    assert preflight["run_id"]==first["run_id"]
    cur.execute("select count(*) from factory_audit_events where run_id=%s and event_type=%s",
                (first["run_id"],"journey.planning.preflight_requeued"))
    assert cur.fetchone()[0]==1
    cur.execute("update factory_runs set status='failed', metadata=metadata || %s where id=%s",
                (Jsonb({"error":"planning_resume_provenance_preflight_failed"}),first["run_id"]))
    cur.execute("update factory_tasks set status='failed' where id=%s",(bound["task_id"],))
    duplicate=call(cur,"factory_resume_failed_journey_v2",journey)
    assert duplicate["created"] is False and duplicate["run_id"]==first["run_id"]
    # Historical preflight receipt must NOT consume checkpoint-recovery allowance.
    cur.execute("update factory_runs set metadata=metadata || %s where id=%s",
                (Jsonb({"error":"verified planning checkpoint is invalid",
                        "stage_evidence":{"planning":{"status":"failed","output":{}}}}),first["run_id"]))
    checkpoint=call(cur,"factory_resume_failed_journey_v2",journey)
    assert checkpoint["created"] is True and checkpoint["requeued"] is True
    assert checkpoint["run_id"]==first["run_id"]
    cur.execute("select count(*) from factory_audit_events where run_id=%s and event_type=%s",
                (first["run_id"],"journey.planning.checkpoint_requeued"))
    assert cur.fetchone()[0]==1
    cur.execute("select metadata from factory_runs where id=%s",(first["run_id"],))
    clean_metadata=cur.fetchone()[0]
    assert "stage_evidence" not in clean_metadata and "error" not in clean_metadata
    cur.execute("update factory_runs set status='failed', metadata=metadata || %s where id=%s",
                (Jsonb({"error":"verified planning checkpoint is invalid",
                        "stage_evidence":{"planning":{"status":"failed","output":{}}}}),first["run_id"]))
    cur.execute("update factory_tasks set status='failed' where id=%s",(bound["task_id"],))
    duplicate=call(cur,"factory_resume_failed_journey_v2",journey)
    assert duplicate["created"] is False
    cur.execute("select count(*) from factory_runs where journey_id=%s",(journey,))
    assert cur.fetchone()[0]==2, "recovery must not mint another run"
    cur.execute("select count(*) from factory_audit_events where run_id=%s and event_type like 'journey.planning.%requeued'",
                (first["run_id"],))
    assert cur.fetchone()[0]==2, "each retry category must be single use"

    cur.execute("update factory_project_execution_controls set state='paused' where project_id=%s",(project,))
    try: call(cur,"factory_resume_failed_journey_v2",journey)
    except psycopg.Error: pass
    else: raise AssertionError("paused project resumed V2 journey")
    cur.execute("set role authenticated")
    try: call(cur,"factory_resume_failed_journey_v2",journey)
    except psycopg.Error: pass
    else: raise AssertionError("authenticated role reached V2 recovery RPC")
    finally: cur.execute("reset role")
print("JOURNEY_V2_NATIVE_RECOVERY_POSTGRES_PASS")
