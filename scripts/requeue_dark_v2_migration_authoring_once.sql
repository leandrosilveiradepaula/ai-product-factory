-- Run only after exact human-merged Factory CI + worker pin and source/work ref verification.
-- This is a data-only recovery of an authorized, zero-model-call preflight failure.
-- No migration, plan replay, access expansion, new run or production release.
BEGIN;
DO $recover$
DECLARE
 p public.factory_projects%rowtype;
 c public.factory_project_execution_controls%rowtype;
 j public.factory_journeys%rowtype;
 cs public.factory_change_sets%rowtype;
 u public.factory_change_set_work_units%rowtype;
 r public.factory_runs%rowtype;
 t public.factory_tasks%rowtype;
 plan public.factory_execution_team_plans%rowtype;
 parent_run public.factory_runs%rowtype;
 source_sha text := '55e8e8d8422ee044eb1112ab678cb0223e987742';
 reason text := 'PermissionError: exact new-file scope lacks a verified populated parent: supabase/migrations/20261126160500_studio_editorial_lifecycle.sql';
 incident text := 'dark-v2-candidate-migration-authoring-20261127-v1';
BEGIN
 SELECT * INTO STRICT p FROM public.factory_projects WHERE id='19f0f200-3777-46c6-969a-acf0d3426ff1' AND is_active AND project_key='dark-channel-studio' AND project_kind='greenfield' AND repository='leandrosilveiradepaula/dark-channel-studio' FOR UPDATE;
 SELECT * INTO STRICT c FROM public.factory_project_execution_controls WHERE project_id=p.id FOR SHARE;
 SELECT * INTO STRICT j FROM public.factory_journeys WHERE id='c43e7781-7cb9-49fd-8459-cc358880df0a' AND project_id=p.id FOR UPDATE;
 SELECT * INTO STRICT cs FROM public.factory_change_sets WHERE id='13d7646f-ba42-4318-8f3c-2d643f00887d' AND project_id=p.id AND journey_id=j.id FOR UPDATE;
 SELECT * INTO STRICT u FROM public.factory_change_set_work_units WHERE id='04474327-c371-4e28-86ef-70921d44c76d' AND change_set_id=cs.id FOR UPDATE;
 SELECT * INTO STRICT r FROM public.factory_runs WHERE id='5b089f53-df63-4636-92ec-0d6d5b10b3ec' AND task_id=u.task_id AND journey_id=j.id FOR UPDATE;
 SELECT * INTO STRICT t FROM public.factory_tasks WHERE id='d1585e39-decf-4725-877a-a1d9cd361869' AND project_id=p.id AND journey_id=j.id FOR UPDATE;
 SELECT * INTO STRICT plan FROM public.factory_execution_team_plans WHERE id='e6412855-1ff8-47f0-a382-e63b4fefef05' AND project_id=p.id AND source_run_id='13fc575b-af98-4eb3-a5b8-01dce69ec8af' FOR SHARE;
 SELECT * INTO STRICT parent_run FROM public.factory_runs WHERE id=plan.source_run_id AND journey_id=j.id AND task_id=t.parent_task_id FOR SHARE;
 IF EXISTS(SELECT 1 FROM public.factory_audit_events WHERE run_id=r.id AND event_type='change_set.migration_authoring_requeued' AND payload->>'incident'=incident) THEN
  RAISE NOTICE 'Already recovered; no change'; RETURN;
 END IF;
 IF c.state IS DISTINCT FROM 'running' OR c.generation IS DISTINCT FROM 1 OR c.version IS DISTINCT FROM 1
 OR j.state IS DISTINCT FROM 'executing' OR j.execution_generation IS DISTINCT FROM 1
 OR j.source_commit IS DISTINCT FROM source_sha OR j.candidate_commit IS NOT NULL OR j.preview_merge_sha IS NOT NULL OR j.production_release_sha IS NOT NULL
 OR j.request_id IS DISTINCT FROM '0b6ab27d-11eb-acf6-1392-50857d8d854c'::uuid OR j.request_source IS DISTINCT FROM 'github-owner'
 OR j.auth_event_id IS DISTINCT FROM '7162981651'
 OR cs.status IS DISTINCT FROM 'blocked' OR cs.source_commit IS DISTINCT FROM source_sha OR cs.candidate_commit IS DISTINCT FROM source_sha
 OR cs.current_wave IS DISTINCT FROM 1 OR cs.team_plan_id IS DISTINCT FROM plan.id
 OR cs.integration_branch IS DISTINCT FROM 'factory/journey-c43e7781-7cb9-49fd-8459-cc358880df0a'
 OR cs.release_run_id IS NOT NULL OR cs.lease_owner IS NOT NULL OR cs.lease_expires_at IS NOT NULL
 OR cs.metadata#>>'{blocker,type}' IS DISTINCT FROM 'implementation_preflight_error'
 OR cs.metadata#>>'{blocker,reason}' IS DISTINCT FROM reason
 OR cs.metadata#>>'{blocker,run_id}' IS DISTINCT FROM r.id::text OR cs.metadata#>>'{blocker,work_unit_id}' IS DISTINCT FROM u.id::text
 OR u.status IS DISTINCT FROM 'blocked' OR u.wave IS DISTINCT FROM 1 OR u.plan_task_key IS DISTINCT FROM 'studio-lifecycle-contract'
 OR u.run_id IS DISTINCT FROM r.id OR u.task_id IS DISTINCT FROM t.id
 OR u.base_commit IS DISTINCT FROM source_sha OR u.output_commit IS NOT NULL OR u.changed_files IS DISTINCT FROM '[]'::jsonb
 OR u.branch_name IS DISTINCT FROM 'factory/cs-13d7646f/studio-lifecycle-contract'
 OR r.status IS DISTINCT FROM 'blocked' OR r.execution_route IS DISTINCT FROM 'direct' OR r.attempt_count IS DISTINCT FROM 1
 OR r.source_commit IS DISTINCT FROM source_sha OR r.candidate_commit IS NOT NULL OR r.lease_owner IS NOT NULL OR r.lease_expires_at IS NOT NULL
 OR r.last_error IS DISTINCT FROM reason OR r.finished_at IS DISTINCT FROM '2026-11-27T11:32:30.642273Z'::timestamptz
 OR r.metadata->>'execution_worker_id' IS DISTINCT FROM 'factory-vps-infodive-direct'
 OR r.metadata->>'execution_generation' IS DISTINCT FROM '1' OR r.metadata->'journey_binding_v2' IS DISTINCT FROM j.binding
 OR r.metadata->>'human_gate_required' IS DISTINCT FROM 'false'
 OR r.metadata->>'blocker_type' IS DISTINCT FROM 'implementation_preflight_error'
 OR r.metadata->>'blocker_reason' IS DISTINCT FROM reason
 OR t.status IS DISTINCT FROM 'blocked' OR t.agent_role IS DISTINCT FROM 'development'
 OR t.required_capabilities IS DISTINCT FROM '["implementation","migration_authoring"]'::jsonb
 OR t.scope_keys IS DISTINCT FROM '["supabase/migrations/20261126160500_studio_editorial_lifecycle.sql","supabase/tests/tenant_persistence_rls.sql",".github/workflows/validate.yml","scripts/verify_migration_forward_recovery.sh","docs/PERSISTENCE_RLS_OPERATIONS.md"]'::jsonb
 OR plan.status IS DISTINCT FROM 'ready' OR parent_run.status IS DISTINCT FROM 'completed'
 OR parent_run.metadata->>'reviewed_plan_recovery' IS DISTINCT FROM 'dark-greenfield-reviewed-plan-20261126-v1'
 OR parent_run.metadata#>>'{stage_evidence,planning,status}' IS DISTINCT FROM 'completed'
 THEN RAISE EXCEPTION 'Exact candidate migration recovery identity or epoch changed' USING ERRCODE='PT409'; END IF;
 IF (SELECT count(*) FROM public.factory_change_set_work_units x WHERE x.change_set_id=cs.id)<>4
 OR EXISTS(SELECT 1 FROM public.factory_change_set_work_units x WHERE x.change_set_id=cs.id AND x.id<>u.id
   AND (x.status IS DISTINCT FROM 'pending' OR x.wave<=1 OR x.run_id IS NOT NULL OR x.base_commit IS NOT NULL OR x.output_commit IS NOT NULL))
 OR EXISTS(SELECT 1 FROM public.factory_tool_usage x WHERE x.run_id=r.id)
 OR EXISTS(SELECT 1 FROM public.factory_work_unit_context_packets x WHERE x.run_id=r.id)
 OR EXISTS(SELECT 1 FROM public.factory_human_gates x WHERE x.run_id=r.id)
 OR EXISTS(SELECT 1 FROM public.factory_runs x JOIN public.factory_tasks xt ON xt.id=x.task_id WHERE xt.project_id=p.id AND x.id<>r.id AND (x.status IN ('created','queued','queued_execution','running','implementing') OR x.lease_owner IS NOT NULL))
 OR (SELECT count(*) FROM public.factory_audit_events x WHERE x.run_id=r.id AND x.event_type='change_set.work_unit.blocked' AND x.payload->>'reason'=reason)<>1
 THEN RAISE EXCEPTION 'Unexpected side effects or concurrent work prevent recovery' USING ERRCODE='PT409'; END IF;

 UPDATE public.factory_runs SET status='queued',last_error=NULL,finished_at=NULL,
 metadata=(metadata-'blocker_type'-'blocker_reason'-'implementation_blocked')||jsonb_build_object('migration_authoring_recovery',incident)
 WHERE id=r.id AND status='blocked' AND lease_owner IS NULL;
 IF NOT FOUND THEN RAISE EXCEPTION 'run CAS lost'; END IF;
 UPDATE public.factory_tasks SET status='queued_execution',updated_at=now() WHERE id=t.id AND status='blocked';
 IF NOT FOUND THEN RAISE EXCEPTION 'task CAS lost'; END IF;
 UPDATE public.factory_change_set_work_units SET status='queued',updated_at=now() WHERE id=u.id AND status='blocked' AND output_commit IS NULL;
 IF NOT FOUND THEN RAISE EXCEPTION 'unit CAS lost'; END IF;
 UPDATE public.factory_change_sets SET status='building',updated_at=now(),
 metadata=(metadata-'blocker')||jsonb_build_object('migration_authoring_recovery',incident)
 WHERE id=cs.id AND status='blocked';
 IF NOT FOUND THEN RAISE EXCEPTION 'set CAS lost'; END IF;
 INSERT INTO public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 VALUES(p.id,t.id,r.id,'system','candidate-migration-preflight-recovery','change_set.migration_authoring_requeued',
 jsonb_build_object('incident',incident,'journey_id',j.id,'change_set_id',cs.id,'work_unit_id',u.id,'source_sha',source_sha,
 'prior_blocker',cs.metadata->'blocker','generation',c.generation,'model_calls_in_recovery',0,'release_authorized',false));
END $recover$;
COMMIT;
