-- One-time data-only recovery of the exact exhausted Dark Channel preflight.
-- Execute only AFTER the human-reviewed source fix is merged, its main CI
-- succeeds, and exact source proof is rechecked. No schema or ACL change.
-- This does not reset the general retry limit, mint another run, or admit
-- an unverified source. The usual worker, provider budget and gates remain.
BEGIN;
DO $recover$
DECLARE
  p public.factory_projects%rowtype;
  c public.factory_project_execution_controls%rowtype;
  j public.factory_journeys%rowtype;
  s public.factory_runs%rowtype;
  r public.factory_runs%rowtype;
  t public.factory_tasks%rowtype;
  incident text := 'dark-greenfield-merge-source-preflight-45626839179-v1';
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
    WHERE a.project_id=p.id AND a.run_id=r.id AND a.event_type='journey.planning.merge_source_preflight_requeued'
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
     OR r.last_error IS DISTINCT FROM 'planning_resume_provenance_preflight_failed'
     OR r.metadata->>'error' IS DISTINCT FROM r.last_error
     OR r.metadata->>'worker_id' IS DISTINCT FROM 'gha-45626839179'
     OR r.metadata->'stages' IS DISTINCT FROM '["planning"]'::jsonb
     OR r.metadata ? 'stage_evidence'
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
     OR EXISTS(SELECT 1 FROM public.factory_tool_usage x WHERE x.run_id=r.id)
     OR EXISTS(SELECT 1 FROM public.factory_human_gates x WHERE x.run_id IN (s.id,r.id))
     OR EXISTS(SELECT 1 FROM public.factory_deployments x WHERE x.run_id IN (s.id,r.id))
     OR EXISTS(SELECT 1 FROM public.factory_evaluations x WHERE x.run_id IN (s.id,r.id))
     OR EXISTS(SELECT 1 FROM public.factory_release_reports x WHERE x.run_id IN (s.id,r.id))
     OR (SELECT count(*) FROM public.factory_audit_events a WHERE a.run_id=r.id AND a.event_type='run.claimed')<>2
     OR (SELECT count(*) FROM public.factory_audit_events a WHERE a.run_id=r.id AND a.event_type='run.failed'
         AND a.payload->>'error'='planning_resume_provenance_preflight_failed')<>2
     OR NOT EXISTS(SELECT 1 FROM public.factory_audit_events a WHERE a.run_id=r.id
         AND a.event_type='run.claimed' AND a.actor_ref='gha-45626839179')
     OR NOT EXISTS(SELECT 1 FROM public.factory_audit_events a WHERE a.run_id=r.id
         AND a.event_type='run.claimed' AND a.actor_ref='factory-vps-infodive-product')
     OR (SELECT count(*) FROM public.factory_audit_events a WHERE a.run_id=r.id
         AND a.event_type='journey.planning.preflight_requeued')<>1
     OR EXISTS(SELECT 1 FROM public.factory_audit_events a WHERE a.run_id=r.id
         AND a.event_type NOT IN ('journey.planning.recovery_queued','run.claimed','run.failed','journey.planning.preflight_requeued'))
  THEN RAISE EXCEPTION 'Unexpected execution effects or active work prevent recovery'; END IF;

  UPDATE public.factory_runs SET status='queued',last_error=NULL,finished_at=NULL,
    metadata=(metadata-'worker_id'-'claimed_at'-'error') ||
      jsonb_build_object('merge_source_preflight_recovery',incident)
    WHERE id=r.id AND status='failed';
  IF NOT FOUND THEN RAISE EXCEPTION 'Run CAS lost'; END IF;
  UPDATE public.factory_tasks SET status='queued',updated_at=now()
    WHERE id=t.id AND status='failed';
  IF NOT FOUND THEN RAISE EXCEPTION 'Task CAS lost'; END IF;

  INSERT INTO public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
  VALUES(p.id,t.id,r.id,'system','audited-source-preflight-recovery','journey.planning.merge_source_preflight_requeued',
    jsonb_build_object('incident',incident,'journey_id',j.id,'source_run_id',s.id,
      'source_commit',source_sha,'source_parent_count',2,'failed_factory_sha','3affbb4ab3090da6984969178f9ecbb62de87698',
      'failed_factory_workflow_id',45626839179,'execution_generation',c.generation,
      'paid_calls',0,'new_run_created',false,'release_authorized',false));
END $recover$;
COMMIT;
