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
    cur.execute((root/"supabase/migrations/20261125132642_journey_v2_greenfield_planning_recovery.sql").read_text())
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
    cur.execute("select count(*) from factory_audit_events where run_id=%s and event_type in ('journey.planning.preflight_requeued','journey.planning.checkpoint_requeued')",
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

    # A linked greenfield with completed discovery/specification recovers only
    # planning, using the exact request and original stage outputs.
    gp="c1608b7f-07ac-47c4-85bc-46df5cd4cbe3"
    greq="7db46ff1-9c5e-4823-8e46-17b068791c31"
    repo="leandrosilveiradepaula/dark-channel-studio"
    cur.execute("insert into factory_projects values(%s,'dark-channel-studio',%s,%s,true,'greenfield')",(gp,repo,Jsonb(manifest)))
    cur.execute("insert into factory_project_execution_controls values(%s,'running',1,1)",(gp,))
    gt="complete existing editorial delivery"
    gd=hashlib.sha256(gt.encode()).hexdigest()
    gj=call(cur,"factory_enqueue_journey_intake_v2","dark-channel-studio",gt,greq,"github-owner","github-owner","456",gd,"leandrosilveiradepaula/ai-product-factory",1055)["journey_id"]
    call(cur,"factory_record_journey_source_evidence_v2",gj,repo,"main",sha,policy,proof,1)
    gb={**binding,"journey_id":gj,"project_id":gp,"request_id":greq,"execution_generation":1,"repository":repo,"source_repository":repo,"integration_branch":"factory/journey-"+gj,"preview_branch_prefix":"preview/journey-"+gj[:8]}
    gr=call(cur,"factory_bind_journey_source_v2","dark-channel-studio",greq,1,2,Jsonb(gb))
    cur.execute("select metadata from factory_runs where id=%s",(gr["run_id"],)); gm=cur.fetchone()[0]
    assert gm["stages"]==["discovery","specification","planning"]
    disc={"problem":"editorial gap","_evidence":{"provider_ref":"discovery-proof"}}
    spec={"scope":"editorial delivery","_evidence":{"provider_ref":"spec-proof"}}
    empty={"reason_code":"planning_non_actionable","observed_model_response":True,"tasks_count":0,"decisions_count":0,"implementation_completed":False,"requires_scope_reconciliation":True}
    gm.update(error="planning has no actionable tasks or decisions",stage_evidence={"discovery":{"status":"completed","output":disc},"specification":{"status":"completed","output":spec},"planning":{"status":"failed","output":empty}})
    cur.execute("update factory_runs set status='failed',metadata=%s where id=%s",(Jsonb(gm),gr["run_id"]))
    cur.execute("update factory_tasks set status='failed' where id=%s",(gr["task_id"],))
    cur.execute("update factory_runs set metadata=jsonb_set(metadata,'{stage_evidence,specification,status}','\"started\"') where id=%s",(gr["run_id"],))
    try: call(cur,"factory_resume_failed_journey_v2",gj)
    except psycopg.Error: pass
    else: raise AssertionError("incomplete greenfield checkpoint admitted")
    cur.execute("update factory_runs set metadata=%s where id=%s",(Jsonb(gm),gr["run_id"]))
    recovered=call(cur,"factory_resume_failed_journey_v2",gj)
    assert recovered["created"] and recovered["stages"]==["planning"]
    cur.execute("select metadata,journey_id,source_commit from factory_runs where id=%s",(recovered["run_id"],))
    checkpoint,jid,source_sha=cur.fetchone()
    assert str(jid)==gj and source_sha==sha
    assert checkpoint["resume_checkpoint"]["prior_kind"]=="greenfield"
    assert checkpoint["resume_checkpoint"]["discovery"]==disc and checkpoint["resume_checkpoint"]["specification"]==spec
    assert call(cur,"factory_resume_failed_journey_v2",gj)["created"] is False
    cur.execute("select count(*) from factory_runs where journey_id=%s",(gj,)); assert cur.fetchone()[0]==2


    # Reproduce the real exhausted, pre-provider merge-source incident.
    # Only local fixture identity is substituted; guards are unchanged.
    cur.execute("alter table factory_runs add column lease_owner text, add column lease_expires_at timestamptz, add column last_error text, add column attempt_count int default 0, add column finished_at timestamptz")
    cur.execute("create table factory_human_gates(run_id uuid)")
    rid=recovered["run_id"]
    cur.execute("update factory_runs set status='failed',last_error='planning_resume_provenance_preflight_failed',metadata=metadata||%s where id=%s",
                (Jsonb({"error":"planning_resume_provenance_preflight_failed","worker_id":"gha-45626839179"}),rid))
    cur.execute("update factory_tasks set status='failed' where id=%s",(gr["task_id"],))
    for actor in ("factory-vps-infodive-product","gha-45626839179"):
        cur.execute("insert into factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload) values(%s,%s,%s,'system',%s,'run.claimed','{}')",(gp,gr["task_id"],rid,actor))
        cur.execute("insert into factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload) values(%s,%s,%s,'system','runtime-worker','run.failed',%s)",(gp,gr["task_id"],rid,Jsonb({"error":"planning_resume_provenance_preflight_failed"})))
    cur.execute("insert into factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload) values(%s,%s,%s,'system','journey-v2-recovery','journey.planning.preflight_requeued','{}')",(gp,gr["task_id"],rid))
    statement=(root/"scripts/requeue_dark_greenfield_merge_source_once.sql").read_text()
    for live,local in (("19f0f200-3777-46c6-969a-acf0d3426ff1",gp),
          ("c43e7781-7cb9-49fd-8459-cc358880df0a",gj),
          ("13fc575b-af98-4eb3-a5b8-01dce69ec8af",rid),
          ("1ed3c5d1-fc2a-4bab-a4a9-12f53bc83c29",gr["run_id"]),
          ("e30ee0cb-0be3-4ddc-a10e-d653d25fa266",gr["task_id"]),
          ("0b6ab27d-11eb-acf6-1392-50857d8d854c",greq),
          ("55e8e8d8422ee044eb1112ab678cb0223e987742",sha),
          ("7162981651","456")):
        statement=statement.replace(live,local)
    # Refuse a paid or otherwise side-effectful run before retrying.
    cur.execute("insert into factory_tool_usage(run_id,operation,metadata) values(%s,'model_call','{}')",(rid,))
    try: cur.execute(statement)
    except psycopg.Error: cur.execute("rollback")
    else: raise AssertionError("paid run was admitted for pre-provider recovery")
    cur.execute("delete from factory_tool_usage where run_id=%s",(rid,))
    cur.execute("update factory_project_execution_controls set state='paused' where project_id=%s",(gp,))
    try: cur.execute(statement)
    except psycopg.Error: cur.execute("rollback")
    else: raise AssertionError("paused greenfield recovered")
    cur.execute("update factory_project_execution_controls set state='running' where project_id=%s",(gp,))
    cur.execute(statement)
    cur.execute(statement)  # exact replay is a no-op
    cur.execute("select status,last_error,metadata from factory_runs where id=%s",(rid,))
    status,error,after=cur.fetchone()
    assert status=="queued" and error is None and after["resume_checkpoint"]==checkpoint["resume_checkpoint"]
    assert "merge_source_preflight_recovery" in after
    cur.execute("select count(*) from factory_runs where journey_id=%s",(gj,)); assert cur.fetchone()[0]==2
    cur.execute("select count(*) from factory_audit_events where run_id=%s and event_type='journey.planning.merge_source_preflight_requeued'",(rid,))
    assert cur.fetchone()[0]==1


    # The next incident is a real completed zero-price model call, not a
    # pre-provider failure. Preserve the full usage and original checkpoint.
    cur.execute("alter table factory_audit_events add column created_at timestamptz default now()")
    cur.execute("alter table factory_tool_usage add column tool_family text, add column estimated_cost numeric, add column usage_units numeric")
    cur.execute("create table factory_execution_team_plans(source_run_id uuid)")
    cur.execute("update factory_runs set status='failed',last_error='planning returned invalid JSON',finished_at='2026-11-25T15:42:47.971687Z',metadata=metadata||%s where id=%s",
        (Jsonb({"error":"planning returned invalid JSON","worker_id":"factory-vps-infodive-product",
            "claimed_at":"2026-11-25T15:41:17.774498+00:00",
            "worker_sync_recovery":"dark-greenfield-worker-sync-4d5efbe9-v1",
            "stage_evidence":{"planning":{"status":"failed","output":{},"recorded_at":"2026-11-25T15:42:47.724676+00:00"}}}),rid))
    cur.execute("update factory_tasks set status='failed' where id=%s",(gr["task_id"],))
    events=[
        ("run.claimed","factory-vps-infodive-product","2026-11-25T14:45:45.941793Z",{}),
        ("run.failed","runtime-worker","2026-11-25T14:45:46.599505Z",{"error":"planning_resume_provenance_preflight_failed"}),
        ("journey.planning.worker_sync_requeued","audited-worker-sync-recovery","2026-11-25T15:40:53.451288Z",{"incident":"dark-greenfield-worker-sync-4d5efbe9-v1"}),
        ("run.claimed","factory-vps-infodive-product","2026-11-25T15:41:17.774498Z",{}),
        ("run.stage.recorded","runtime-worker","2026-11-25T15:41:26.268422Z",{"stage":"planning","status":"started"}),
        ("run.stage.recorded","runtime-worker","2026-11-25T15:42:47.724676Z",{"stage":"planning","status":"failed"}),
        ("run.failed","runtime-worker","2026-11-25T15:42:47.971687Z",{"error":"planning returned invalid JSON"}),
    ]
    for event,actor,created,payload in events:
        cur.execute("insert into factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload,created_at) values(%s,%s,%s,'system',%s,%s,%s,%s)",
                    (gp,gr["task_id"],rid,actor,event,Jsonb(payload),created))
    usage={"provider":"infodive_ibm_cloud","model":"SQL-InfoDive","status":"completed","input_tokens":16386,"output_tokens":4096,"cost_usd":"0"}
    cur.execute("insert into factory_tool_usage(id,run_id,tool_family,operation,metadata,estimated_cost,usage_units) overriding system value values(382,%s,'model','private_sql_completed',%s,0,20482)",(rid,Jsonb(usage)))
    statement=(root/"scripts/requeue_dark_greenfield_bounded_planning_once.sql").read_text()
    for live,local in (("19f0f200-3777-46c6-969a-acf0d3426ff1",gp),
          ("c43e7781-7cb9-49fd-8459-cc358880df0a",gj),
          ("13fc575b-af98-4eb3-a5b8-01dce69ec8af",rid),
          ("1ed3c5d1-fc2a-4bab-a4a9-12f53bc83c29",gr["run_id"]),
          ("e30ee0cb-0be3-4ddc-a10e-d653d25fa266",gr["task_id"]),
          ("0b6ab27d-11eb-acf6-1392-50857d8d854c",greq),
          ("55e8e8d8422ee044eb1112ab678cb0223e987742",sha),
          ("7162981651","456")):
        statement=statement.replace(live,local)
    for invalid,restore in (
        ("update factory_tool_usage set estimated_cost=NULL where id=382","update factory_tool_usage set estimated_cost=0 where id=382"),
        ("update factory_tool_usage set estimated_cost=1 where id=382","update factory_tool_usage set estimated_cost=0 where id=382"),
        ("update factory_tool_usage set metadata=jsonb_set(metadata,'{output_tokens}','4095') where id=382","update factory_tool_usage set metadata=jsonb_set(metadata,'{output_tokens}','4096') where id=382"),
        ("update factory_project_execution_controls set state='paused' where project_id='"+gp+"'","update factory_project_execution_controls set state='running' where project_id='"+gp+"'"),
        ("insert into factory_execution_team_plans values('"+rid+"')","delete from factory_execution_team_plans where source_run_id='"+rid+"'"),
    ):
        cur.execute(invalid)
        try: cur.execute(statement)
        except psycopg.Error: cur.execute("rollback")
        else: raise AssertionError("unsafe bounded-output retry admitted")
        cur.execute(restore)
    cur.execute(statement)
    cur.execute(statement)
    cur.execute("select status,last_error,metadata from factory_runs where id=%s",(rid,))
    status,error,after=cur.fetchone()
    assert status=="queued" and error is None and "stage_evidence" not in after
    assert after["resume_checkpoint"]==checkpoint["resume_checkpoint"]
    assert after["bounded_planning_output_recovery"]=="dark-greenfield-bounded-plan-output-382-v1"
    cur.execute("select count(*) from factory_runs where journey_id=%s",(gj,))
    assert cur.fetchone()[0]==2
    cur.execute("select id,operation,estimated_cost,usage_units,metadata from factory_tool_usage where run_id=%s",(rid,))
    receipt=cur.fetchone()
    assert receipt==(382,"private_sql_completed",0,20482,usage) and cur.fetchone() is None
    cur.execute("select count(*) from factory_audit_events where run_id=%s and event_type='journey.planning.bounded_output_requeued'",(rid,))
    assert cur.fetchone()[0]==1


    # The subsequent paid provider returned an empty plan. Admit only the
    # exact reviewed-plan handoff; preserve both usage rows and the failure.
    failed_output={"reason_code":"planning_non_actionable","tasks_count":0,
        "assessed_commit":sha,"decisions_count":0,"observed_model_response":True,
        "implementation_completed":False,"requires_scope_reconciliation":True}
    failed_evidence={"planning":{"output":failed_output,"status":"failed",
        "recorded_at":"2026-11-26T12:46:53.409338+00:00"}}
    cur.execute("update factory_runs set status='failed',last_error='planning has no actionable tasks or decisions',finished_at='2026-11-26T12:46:54.032911Z',metadata=metadata||%s where id=%s",
        (Jsonb({"error":"planning has no actionable tasks or decisions","worker_id":"gha-45822639911",
            "claimed_at":"2026-11-26T12:46:27.931388+00:00","stage_evidence":failed_evidence}),rid))
    cur.execute("update factory_tasks set status='failed' where id=%s",(gr["task_id"],))
    paid={"provider":"openai","model":"gpt-5.6-terra","status":"completed","input_tokens":26120,"output_tokens":710}
    cur.execute("insert into factory_tool_usage(id,run_id,tool_family,operation,metadata,estimated_cost,usage_units) overriding system value values(383,%s,'openai','model_call',%s,0.06076,26830)",(rid,Jsonb(paid)))
    for event,actor,created,payload in [
        ("run.claimed","gha-45822639911","2026-11-26T12:46:27.931388Z",{}),
        ("run.stage.recorded","runtime-worker","2026-11-26T12:46:28Z",{"stage":"planning","status":"started"}),
        ("run.stage.recorded","runtime-worker","2026-11-26T12:46:53.409338Z",{"stage":"planning","status":"failed"}),
        ("run.failed","runtime-worker","2026-11-26T12:46:54.032911Z",{"error":"planning has no actionable tasks or decisions"}),
    ]:
        cur.execute("insert into factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload,created_at) values(%s,%s,%s,'system',%s,%s,%s,%s)",
                    (gp,gr["task_id"],rid,actor,event,Jsonb(payload),created))
    statement=(root/"scripts/requeue_dark_greenfield_reviewed_plan_once.sql").read_text()
    for live,local in (("19f0f200-3777-46c6-969a-acf0d3426ff1",gp),
          ("c43e7781-7cb9-49fd-8459-cc358880df0a",gj),("13fc575b-af98-4eb3-a5b8-01dce69ec8af",rid),("1ed3c5d1-fc2a-4bab-a4a9-12f53bc83c29",gr["run_id"]),
          ("e30ee0cb-0be3-4ddc-a10e-d653d25fa266",gr["task_id"]),("0b6ab27d-11eb-acf6-1392-50857d8d854c",greq),("55e8e8d8422ee044eb1112ab678cb0223e987742",sha),
          ("6325ff172bc0e73417bd365767deef78136ed016333e3d591adf921e8833888d",gd),("7162981651","456")):
        statement=statement.replace(live,local)
    cur.execute("update factory_tool_usage set estimated_cost=NULL where id=383")
    try: cur.execute(statement)
    except psycopg.Error: cur.execute("rollback")
    else: raise AssertionError("unknown cost admitted for reviewed plan")
    cur.execute("update factory_tool_usage set estimated_cost=0.06076 where id=383")
    cur.execute(statement)
    cur.execute(statement)
    cur.execute("select status,last_error,metadata from factory_runs where id=%s",(rid,))
    status,error,after=cur.fetchone()
    assert status=="queued" and error is None and "stage_evidence" not in after
    assert after["resume_checkpoint"]==checkpoint["resume_checkpoint"]
    assert after["reviewed_plan_recovery"]=="dark-greenfield-reviewed-plan-20261126-v1"
    cur.execute("select count(*) from factory_runs where journey_id=%s",(gj,)); assert cur.fetchone()[0]==2
    cur.execute("select count(*) from factory_tool_usage where run_id=%s",(rid,)); assert cur.fetchone()[0]==2
    cur.execute("select payload from factory_audit_events where run_id=%s and event_type='journey.planning.reviewed_plan_requeued'",(rid,))
    saved=cur.fetchone()[0]
    assert saved["prior_stage_evidence"]==failed_evidence and saved["autonomous_model_planning"] is False
    assert cur.fetchone() is None

print("JOURNEY_V2_NATIVE_RECOVERY_POSTGRES_PASS")
