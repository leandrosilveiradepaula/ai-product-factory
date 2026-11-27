-- Exact one-time assisted planning handoff after a completed paid empty plan.
-- Run only after human merge, green main CI and verified native VPS checkout/pin.
-- No schema change, fabricated plan, deleted ledger entry or new journey/run.
BEGIN;
DO $recover$
DECLARE
  p public.factory_projects%rowtype;
  c public.factory_project_execution_controls%rowtype;
  j public.factory_journeys%rowtype;
  s public.factory_runs%rowtype;
  r public.factory_runs%rowtype;
  t public.factory_tasks%rowtype;
  incident text := 'dark-greenfield-reviewed-plan-20261126-v1';
  source_sha text := '55e8e8d8422ee044eb1112ab678cb0223e987742';
BEGIN
  SELECT * INTO STRICT p FROM public.factory_projects
    WHERE id='19f0f200-3777-46c6-969a-acf0d3426ff1'::uuid
      AND project_key='dark-channel-studio'
      AND repository='leandrosilveiradepaula/dark-channel-studio'
      AND project_kind='greenfield' AND is_active FOR UPDATE;
  SELECT * INTO STRICT c FROM public.factory_project_execution_controls
    WHERE project_id=p.id FOR SHARE;
  SELECT * INTO STRICT j FROM public.factory_journeys
    WHERE id='c43e7781-7cb9-49fd-8459-cc358880df0a'::uuid AND project_id=p.id FOR UPDATE;
  SELECT * INTO STRICT r FROM public.factory_runs
    WHERE id='13fc575b-af98-4eb3-a5b8-01dce69ec8af'::uuid AND journey_id=j.id FOR UPDATE;
  SELECT * INTO STRICT s FROM public.factory_runs
    WHERE id='1ed3c5d1-fc2a-4bab-a4a9-12f53bc83c29'::uuid AND journey_id=j.id FOR UPDATE;
  SELECT * INTO STRICT t FROM public.factory_tasks
    WHERE id='e30ee0cb-0be3-4ddc-a10e-d653d25fa266'::uuid AND project_id=p.id FOR UPDATE;

  IF EXISTS(SELECT 1 FROM public.factory_audit_events a
    WHERE a.project_id=p.id AND a.run_id=r.id AND a.event_type='journey.planning.reviewed_plan_requeued'
      AND a.payload->>'incident'=incident) THEN
    RAISE NOTICE 'Already recovered; no change';
    RETURN;
  END IF;

  IF c.state IS DISTINCT FROM 'running' OR c.generation IS DISTINCT FROM 1 OR c.version IS DISTINCT FROM 1
     OR j.state IS DISTINCT FROM 'executing' OR j.execution_generation IS DISTINCT FROM c.generation
     OR j.source_commit IS DISTINCT FROM source_sha
     OR j.request_id IS DISTINCT FROM '0b6ab27d-11eb-acf6-1392-50857d8d854c'::uuid
     OR j.request_source IS DISTINCT FROM 'github-owner' OR j.auth_event_id IS DISTINCT FROM '7162981651'
     OR j.candidate_commit IS NOT NULL OR j.work_unit_output_commit IS NOT NULL
     OR j.preview_merge_sha IS NOT NULL OR j.production_release_sha IS NOT NULL
     OR t.journey_id IS DISTINCT FROM j.id OR t.status IS DISTINCT FROM 'failed'
     OR r.task_id IS DISTINCT FROM t.id OR s.task_id IS DISTINCT FROM t.id
     OR r.status IS DISTINCT FROM 'failed' OR s.status IS DISTINCT FROM 'failed'
     OR r.execution_route IS DISTINCT FROM 'direct' OR s.execution_route IS DISTINCT FROM 'direct'
     OR r.source_commit IS DISTINCT FROM source_sha OR s.source_commit IS DISTINCT FROM source_sha
     OR r.candidate_commit IS NOT NULL OR s.candidate_commit IS NOT NULL
     OR r.lease_owner IS NOT NULL OR r.lease_expires_at IS NOT NULL
     OR s.lease_owner IS NOT NULL OR s.lease_expires_at IS NOT NULL
     OR r.attempt_count IS DISTINCT FROM 0
     OR r.last_error IS DISTINCT FROM 'planning has no actionable tasks or decisions'
     OR r.metadata->>'error' IS DISTINCT FROM r.last_error
     OR r.metadata->>'worker_id' IS DISTINCT FROM 'gha-45822639911'
     OR r.metadata->>'claimed_at' IS DISTINCT FROM '2026-11-26T12:46:27.931388+00:00'
     OR r.finished_at IS DISTINCT FROM '2026-11-26T12:46:54.032911Z'::timestamptz
     OR r.metadata->>'merge_source_preflight_recovery' IS DISTINCT FROM 'dark-greenfield-merge-source-preflight-45626839179-v1'
     OR r.metadata->>'worker_sync_recovery' IS DISTINCT FROM 'dark-greenfield-worker-sync-4d5efbe9-v1'
     OR r.metadata->>'bounded_planning_output_recovery' IS DISTINCT FROM 'dark-greenfield-bounded-plan-output-382-v1'
     OR r.metadata ? 'reviewed_plan_recovery'
     OR j.request_snapshot->>'digest' IS DISTINCT FROM '6325ff172bc0e73417bd365767deef78136ed016333e3d591adf921e8833888d'
     OR r.metadata->'stages' IS DISTINCT FROM '["planning"]'::jsonb
     OR r.metadata->'stage_evidence' IS DISTINCT FROM '{"planning":{"output":{"reason_code":"planning_non_actionable","tasks_count":0,"assessed_commit":"55e8e8d8422ee044eb1112ab678cb0223e987742","decisions_count":0,"observed_model_response":true,"implementation_completed":false,"requires_scope_reconciliation":true},"status":"failed","recorded_at":"2026-11-26T12:46:53.409338+00:00"}}'::jsonb
     OR r.metadata->'journey_binding_v2' IS DISTINCT FROM j.binding
     OR s.metadata->'journey_binding_v2' IS DISTINCT FROM j.binding
     OR r.metadata->'journey_request' IS DISTINCT FROM j.request_snapshot
     OR s.metadata->'journey_request' IS DISTINCT FROM j.request_snapshot
     OR r.metadata->>'execution_generation' IS DISTINCT FROM '1'
     OR s.metadata->>'execution_generation' IS DISTINCT FROM '1'
     OR r.metadata#>>'{resume_checkpoint,schema}' IS DISTINCT FROM 'journey_v2_planning_recovery_v1'
     OR r.metadata#>>'{resume_checkpoint,prior_kind}' IS DISTINCT FROM 'greenfield'
     OR r.metadata#>>'{resume_checkpoint,source_run_id}' IS DISTINCT FROM s.id::text
     OR r.metadata#>>'{resume_checkpoint,journey_id}' IS DISTINCT FROM j.id::text
     OR r.metadata#>>'{resume_checkpoint,project_id}' IS DISTINCT FROM p.id::text
     OR r.metadata#>>'{resume_checkpoint,generation}' IS DISTINCT FROM '1'
     OR r.metadata#>>'{resume_checkpoint,source_commit}' IS DISTINCT FROM source_sha
     OR s.metadata->>'error' IS DISTINCT FROM 'planning has no actionable tasks or decisions'
     OR s.metadata->'stages' IS DISTINCT FROM '["discovery","specification","planning"]'::jsonb
     OR s.metadata#>>'{stage_evidence,discovery,status}' IS DISTINCT FROM 'completed'
     OR s.metadata#>>'{stage_evidence,specification,status}' IS DISTINCT FROM 'completed'
     OR r.metadata#>'{resume_checkpoint,discovery}' IS DISTINCT FROM s.metadata#>'{stage_evidence,discovery,output}'
     OR r.metadata#>'{resume_checkpoint,specification}' IS DISTINCT FROM s.metadata#>'{stage_evidence,specification,output}'
     OR nullif(s.metadata#>>'{stage_evidence,discovery,output,_evidence,provider_ref}','') IS NULL
     OR nullif(s.metadata#>>'{stage_evidence,specification,output,_evidence,provider_ref}','') IS NULL
  THEN RAISE EXCEPTION 'Exact recovery identity/checkpoint/state no longer matches'; END IF;

  IF (SELECT count(*) FROM public.factory_runs x WHERE x.journey_id=j.id)<>2
     OR EXISTS(SELECT 1 FROM public.factory_runs x JOIN public.factory_tasks xt ON xt.id=x.task_id
       WHERE xt.project_id=p.id AND (x.status IN ('created','queued','running') OR x.lease_owner IS NOT NULL))
     OR EXISTS(SELECT 1 FROM public.factory_tasks x WHERE x.parent_task_id=t.id)
     OR EXISTS(SELECT 1 FROM public.factory_change_sets x WHERE x.journey_id=j.id)
     OR EXISTS(SELECT 1 FROM public.factory_execution_team_plans x WHERE x.source_run_id=r.id)
     OR (SELECT count(*) FROM public.factory_tool_usage x WHERE x.run_id=r.id)<>2
     OR NOT EXISTS(SELECT 1 FROM public.factory_tool_usage x WHERE x.run_id=r.id
         AND x.id=382 AND x.tool_family='model' AND x.operation='private_sql_completed'
         AND x.estimated_cost=0 AND x.usage_units=20482
         AND x.metadata->>'provider'='infodive_ibm_cloud' AND x.metadata->>'model'='SQL-InfoDive'
         AND x.metadata->>'status'='completed' AND x.metadata->>'input_tokens'='16386'
         AND x.metadata->>'output_tokens'='4096' AND x.metadata->>'cost_usd'='0')
     OR NOT EXISTS(SELECT 1 FROM public.factory_tool_usage x WHERE x.run_id=r.id
         AND x.id=383 AND x.tool_family='openai' AND x.operation='model_call'
         AND x.estimated_cost=0.06076 AND x.usage_units=26830
         AND x.metadata->>'provider'='openai' AND x.metadata->>'model'='gpt-5.6-terra'
         AND x.metadata->>'status'='completed' AND x.metadata->>'input_tokens'='26120'
         AND x.metadata->>'output_tokens'='710')
     OR EXISTS(SELECT 1 FROM public.factory_human_gates x WHERE x.run_id IN (s.id,r.id))
     OR EXISTS(SELECT 1 FROM public.factory_deployments x WHERE x.run_id IN (s.id,r.id))
     OR EXISTS(SELECT 1 FROM public.factory_evaluations x WHERE x.run_id IN (s.id,r.id))
     OR EXISTS(SELECT 1 FROM public.factory_release_reports x WHERE x.run_id IN (s.id,r.id))
     OR (SELECT count(*) FROM public.factory_audit_events a WHERE a.run_id=r.id AND a.event_type='run.claimed')<>5
     OR (SELECT count(*) FROM public.factory_audit_events a WHERE a.run_id=r.id AND a.event_type='run.failed'
         AND a.payload->>'error'='planning_resume_provenance_preflight_failed')<>3
     OR (SELECT count(*) FROM public.factory_audit_events a WHERE a.run_id=r.id AND a.event_type='run.failed')<>5
     OR NOT EXISTS(SELECT 1 FROM public.factory_audit_events a WHERE a.run_id=r.id
         AND a.event_type='run.claimed' AND a.actor_ref='factory-vps-infodive-product'
         AND a.created_at='2026-11-25T15:41:17.774498Z'::timestamptz)
     OR NOT EXISTS(SELECT 1 FROM public.factory_audit_events a WHERE a.run_id=r.id
         AND a.event_type='run.failed' AND a.payload->>'error'='planning returned invalid JSON'
         AND a.created_at='2026-11-25T15:42:47.971687Z'::timestamptz)
     OR (SELECT count(*) FROM public.factory_audit_events a WHERE a.run_id=r.id AND a.event_type='run.stage.recorded')<>4
     OR NOT EXISTS(SELECT 1 FROM public.factory_audit_events a WHERE a.run_id=r.id
         AND a.event_type='run.stage.recorded' AND a.payload->>'stage'='planning'
         AND a.payload->>'status'='started' AND a.created_at='2026-11-25T15:41:26.268422Z'::timestamptz)
     OR NOT EXISTS(SELECT 1 FROM public.factory_audit_events a WHERE a.run_id=r.id
         AND a.event_type='run.stage.recorded' AND a.payload->>'stage'='planning'
         AND a.payload->>'status'='failed' AND a.created_at='2026-11-25T15:42:47.724676Z'::timestamptz)
     OR NOT EXISTS(SELECT 1 FROM public.factory_audit_events a WHERE a.run_id=r.id
         AND a.event_type='run.claimed' AND a.actor_ref='gha-45626839179')
     OR NOT EXISTS(SELECT 1 FROM public.factory_audit_events a WHERE a.run_id=r.id
         AND a.event_type='run.claimed' AND a.actor_ref='factory-vps-infodive-product')
     OR (SELECT count(*) FROM public.factory_audit_events a WHERE a.run_id=r.id
         AND a.event_type='journey.planning.preflight_requeued')<>1
     OR (SELECT count(*) FROM public.factory_audit_events a WHERE a.run_id=r.id
         AND a.event_type='journey.planning.merge_source_preflight_requeued'
         AND a.payload->>'incident'='dark-greenfield-merge-source-preflight-45626839179-v1')<>1
     OR (SELECT count(*) FROM public.factory_audit_events a WHERE a.run_id=r.id
         AND a.event_type='journey.planning.worker_sync_requeued'
         AND a.payload->>'incident'='dark-greenfield-worker-sync-4d5efbe9-v1')<>1
     OR (SELECT count(*) FROM public.factory_audit_events a WHERE a.run_id=r.id
         AND a.event_type='journey.planning.bounded_output_requeued'
         AND a.payload->>'incident'='dark-greenfield-bounded-plan-output-382-v1')<>1
     OR NOT EXISTS(SELECT 1 FROM public.factory_audit_events a WHERE a.run_id=r.id
         AND a.event_type='run.claimed' AND a.actor_ref='gha-45822639911'
         AND a.created_at='2026-11-26T12:46:27.931388Z'::timestamptz)
     OR NOT EXISTS(SELECT 1 FROM public.factory_audit_events a WHERE a.run_id=r.id
         AND a.event_type='run.failed' AND a.payload->>'error'='planning has no actionable tasks or decisions'
         AND a.created_at='2026-11-26T12:46:54.032911Z'::timestamptz)
     OR EXISTS(SELECT 1 FROM public.factory_audit_events a WHERE a.run_id=r.id
         AND a.event_type NOT IN ('journey.planning.recovery_queued','run.claimed','run.failed','journey.planning.preflight_requeued','journey.planning.merge_source_preflight_requeued','journey.planning.worker_sync_requeued','journey.planning.bounded_output_requeued','run.stage.recorded'))
  THEN RAISE EXCEPTION 'Unexpected execution effects or active work prevent recovery'; END IF;

  UPDATE public.factory_runs SET status='queued',last_error=NULL,finished_at=NULL,
    metadata=(metadata-'worker_id'-'claimed_at'-'error'-'stage_evidence') ||
      jsonb_build_object('reviewed_plan_recovery',incident)
    WHERE id=r.id AND status='failed';
  IF NOT FOUND THEN RAISE EXCEPTION 'Run CAS lost'; END IF;
  UPDATE public.factory_tasks SET status='queued',updated_at=now()
    WHERE id=t.id AND status='failed';
  IF NOT FOUND THEN RAISE EXCEPTION 'Task CAS lost'; END IF;

  INSERT INTO public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
  VALUES(p.id,t.id,r.id,'system','audited-reviewed-plan-recovery','journey.planning.reviewed_plan_requeued',
    jsonb_build_object('incident',incident,'journey_id',j.id,'source_run_id',s.id,
      'source_commit',source_sha,'failed_factory_sha','58b2fc6282ef245bc1750e504a005c8180425674',
      'prior_usage_ids',jsonb_build_array(382,383),'prior_stage_evidence',r.metadata->'stage_evidence',
      'prior_estimated_cost_usd',0.06076,'prior_model_calls_preserved',true,
      'assisted_planning',true,'autonomous_model_planning',false,
      'execution_generation',c.generation,'paid_calls',0,'new_run_created',false,
      'release_authorized',false));
END $recover$;
COMMIT;
