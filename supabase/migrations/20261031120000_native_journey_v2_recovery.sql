-- One fenced recovery for a V2 journey whose original planning call returned
-- no actionable work before exact-SHA source evidence was available.  This is
-- not a legacy retry and never reuses a task, run, or artifact from another
-- journey.  Review and apply only through the existing human migration gate.
BEGIN;

CREATE OR REPLACE FUNCTION public.factory_resume_failed_journey_v2(p_journey_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path TO '' AS $fn$
DECLARE
  j public.factory_journeys%rowtype; p public.factory_projects%rowtype;
  c public.factory_project_execution_controls%rowtype; source public.factory_runs%rowtype;
  t public.factory_tasks%rowtype; prior uuid; new_run uuid; checkpoint jsonb;
  reconciliation jsonb; gap jsonb;
BEGIN
  IF p_journey_id IS NULL THEN RAISE EXCEPTION 'journey identity is required' USING errcode='PT400'; END IF;
  -- Project lock is the serialization point for pause/stop/resume and duplicate callers.
  SELECT p0.* INTO p FROM public.factory_projects p0 JOIN public.factory_journeys j0 ON j0.project_id=p0.id
   WHERE j0.id=p_journey_id AND p0.is_active=true FOR UPDATE OF p0;
  IF p.id IS NULL THEN RAISE EXCEPTION 'journey project is unavailable' USING errcode='PT409'; END IF;
  SELECT * INTO c FROM public.factory_project_execution_controls WHERE project_id=p.id FOR SHARE;
  SELECT * INTO j FROM public.factory_journeys WHERE id=p_journey_id AND project_id=p.id FOR UPDATE;
  IF c.state IS DISTINCT FROM 'running' OR c.generation IS NULL OR c.generation<1
     OR j.state NOT IN ('source_bound','executing') OR j.execution_generation IS DISTINCT FROM c.generation
     OR j.source_commit !~ '^[0-9a-f]{40}$' OR j.candidate_commit IS NOT NULL THEN
    RAISE EXCEPTION 'journey recovery epoch or state is not eligible' USING errcode='PT409';
  END IF;
  SELECT r.* INTO source FROM public.factory_runs r WHERE r.journey_id=j.id
   AND r.status='failed' ORDER BY r.created_at DESC LIMIT 1 FOR UPDATE;
  SELECT * INTO t FROM public.factory_tasks WHERE id=source.task_id AND project_id=p.id FOR UPDATE;
  IF source.id IS NULL OR t.id IS NULL OR t.journey_id IS DISTINCT FROM j.id
     OR source.execution_route IS DISTINCT FROM 'direct' OR source.source_commit IS DISTINCT FROM j.source_commit
     OR source.metadata->>'error' IS DISTINCT FROM 'planning has no actionable tasks or decisions'
     OR source.metadata->'stages' IS DISTINCT FROM '["reconciliation","gap_analysis","planning"]'::jsonb
     OR source.metadata->>'execution_generation' IS DISTINCT FROM c.generation::text
     OR source.metadata->'journey_binding_v2' IS DISTINCT FROM j.binding THEN
    RAISE EXCEPTION 'journey has no recoverable empty planning source' USING errcode='PT409';
  END IF;
  -- A prior recovery is final for this exact source.  This prevents a paid loop.
  SELECT r.id INTO prior FROM public.factory_runs r WHERE r.journey_id=j.id
   AND r.metadata#>>'{resume_checkpoint,schema}'='journey_v2_planning_recovery_v1'
   AND r.metadata#>>'{resume_checkpoint,source_run_id}'=source.id::text ORDER BY r.created_at DESC LIMIT 1;
  IF prior IS NOT NULL THEN RETURN jsonb_build_object('created',false,'journey_id',j.id,'run_id',prior,'source_run_id',source.id); END IF;
  IF EXISTS(SELECT 1 FROM public.factory_runs other JOIN public.factory_tasks other_task ON other_task.id=other.task_id
     WHERE other_task.project_id=p.id AND other.status IN ('created','queued','running')
       AND other.journey_id IS DISTINCT FROM j.id) THEN
    RAISE EXCEPTION 'project has active incompatible work' USING errcode='PT409';
  END IF;
  IF EXISTS(SELECT 1 FROM public.factory_change_sets cs WHERE cs.journey_id=j.id)
     OR EXISTS(SELECT 1 FROM public.factory_tasks child WHERE child.parent_task_id=t.id) THEN
    RAISE EXCEPTION 'journey already has delivery artifacts' USING errcode='PT409';
  END IF;
  reconciliation:=source.metadata#>'{stage_evidence,reconciliation,output}';
  gap:=source.metadata#>'{stage_evidence,gap_analysis,output}';
  IF jsonb_typeof(reconciliation) IS DISTINCT FROM 'object' OR length(btrim(coalesce(reconciliation->>'summary','')))=0
     OR jsonb_typeof(gap) IS DISTINCT FROM 'object' OR jsonb_typeof(gap->'recommended_next_work') IS DISTINCT FROM 'array'
     OR jsonb_array_length(gap->'recommended_next_work')<1 THEN
    RAISE EXCEPTION 'journey source stage evidence is incomplete' USING errcode='PT409';
  END IF;
  checkpoint:=jsonb_build_object('schema','journey_v2_planning_recovery_v1','journey_id',j.id,
    'project_id',p.id,'source_run_id',source.id,'generation',c.generation,'source_commit',j.source_commit,
    'reconciliation',reconciliation,'gap_analysis',gap);
  INSERT INTO public.factory_runs(task_id,journey_id,status,execution_route,source_commit,branch_name,metadata)
  VALUES(t.id,j.id,'queued','direct',j.source_commit,j.binding->>'integration_branch',
    (source.metadata-'worker_id'-'claimed_at'-'error'-'stage_evidence') || jsonb_build_object(
      'stages',jsonb_build_array('planning'),'execution_generation',c.generation,
      'journey_binding_v2',j.binding,'journey_request',j.request_snapshot,'resume_checkpoint',checkpoint)) RETURNING id INTO new_run;
  UPDATE public.factory_tasks SET status='queued',updated_at=now() WHERE id=t.id;
  UPDATE public.factory_journeys SET state='executing',updated_at=now() WHERE id=j.id;
  INSERT INTO public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
  VALUES(p.id,t.id,new_run,'system','journey-v2-recovery','journey.planning.recovery_queued',
    jsonb_build_object('journey_id',j.id,'source_run_id',source.id,'source_commit',j.source_commit,
      'execution_generation',c.generation,'paid_calls',0));
  RETURN jsonb_build_object('created',true,'journey_id',j.id,'run_id',new_run,'source_run_id',source.id,
    'task_id',t.id,'generation',c.generation,'stages',jsonb_build_array('planning'));
END $fn$;

REVOKE ALL ON FUNCTION public.factory_resume_failed_journey_v2(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.factory_resume_failed_journey_v2(uuid) TO service_role;
COMMIT;
