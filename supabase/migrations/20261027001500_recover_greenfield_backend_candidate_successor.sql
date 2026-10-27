-- INERT UNTIL HUMAN-AUTHORIZED CONTROL PLANE MIGRATION AND EXPLICIT OPERATOR RPC.
-- Recover one failed environmental F6 browser run after a later reviewed PR SHA.
-- Re-run CI, quality, specialists and browser for the NEW SHA; preserve all
-- original evaluations and original create_pr receipt. No release or auto-merge.
BEGIN;
CREATE OR REPLACE FUNCTION public.factory_recover_greenfield_backend_successor_v1(
  p_run_id uuid, p_previous_commit text, p_new_commit text,
  p_pr_number integer, p_verified_github jsonb, p_environment_probe jsonb
) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $recover$
DECLARE
  v_set public.factory_change_sets%ROWTYPE;
  v_run public.factory_runs%ROWTYPE;
  v_task public.factory_tasks%ROWTYPE;
  v_project public.factory_projects%ROWTYPE;
  v_state record;
  v_original record;
  v_last record;
  v_browser record;
  v_new_url text;
  v_checked timestamptz;
  v_count integer;
  v_hop record;
  v_sha text;
  v_seen text[];
BEGIN
  IF p_run_id IS NULL OR p_previous_commit !~ '^[0-9a-f]{40}$'
     OR p_new_commit !~ '^[0-9a-f]{40}$' OR p_new_commit = p_previous_commit
     OR p_pr_number IS NULL OR p_pr_number < 1
     OR jsonb_typeof(p_verified_github) IS DISTINCT FROM 'object'
     OR jsonb_typeof(p_environment_probe) IS DISTINCT FROM 'object'
     OR p_verified_github->>'source' IS DISTINCT FROM 'github_actions_exact_sha'
     OR p_verified_github->>'old_sha' IS DISTINCT FROM p_previous_commit
     OR p_verified_github->>'new_sha' IS DISTINCT FROM p_new_commit
     OR p_verified_github->>'head_sha' IS DISTINCT FROM p_new_commit
     OR p_verified_github->>'pr_number' IS DISTINCT FROM p_pr_number::text
     OR p_verified_github->>'pr_state' IS DISTINCT FROM 'open'
     OR p_verified_github->>'merged' IS DISTINCT FROM 'false'
     OR p_verified_github->>'draft' IS DISTINCT FROM 'false'
     OR p_verified_github->>'base_ref' IS DISTINCT FROM 'main'
     OR p_verified_github->>'compare_status' IS DISTINCT FROM 'ahead'
     OR (p_verified_github->>'behind_by') IS DISTINCT FROM '0'
     OR coalesce((p_verified_github->>'ahead_by') ~ '^[1-9][0-9]{0,5}$',false) IS NOT TRUE
     OR coalesce((p_verified_github->>'ci_run_id') ~ '^[1-9][0-9]{0,14}$',false) IS NOT TRUE
     OR p_verified_github->>'ci_conclusion' IS DISTINCT FROM 'success'
     OR p_verified_github->>'vercel_state' IS DISTINCT FROM 'success'
     OR coalesce((p_verified_github->>'vercel_deployment_id') ~ '^dpl_[a-zA-Z0-9]{10,48}$',false) IS NOT TRUE
  THEN
    RAISE EXCEPTION 'current native GitHub and Vercel SHA proof required' USING errcode='PT400';
  END IF;

  SELECT * INTO v_set FROM public.factory_change_sets
  WHERE release_run_id=p_run_id FOR UPDATE;
  IF NOT FOUND OR v_set.status IS DISTINCT FROM 'ci_pending'
    OR v_set.candidate_commit IS DISTINCT FROM p_previous_commit
    OR v_set.lease_owner IS NOT NULL OR v_set.lease_expires_at IS NOT NULL
    OR v_set.integration_branch IS NULL
  THEN RAISE EXCEPTION 'Change Set candidate or lease drift' USING errcode='PT409'; END IF;

  SELECT * INTO v_project FROM public.factory_projects WHERE id=v_set.project_id;
  IF NOT FOUND OR v_project.is_active IS NOT TRUE
     OR v_project.project_kind IS DISTINCT FROM 'greenfield'
     OR v_project.repository IS DISTINCT FROM p_verified_github->>'repository'
     OR ((v_project.manifest->'preview')->>'required') IS DISTINCT FROM 'true'
  THEN RAISE EXCEPTION 'not an active greenfield with required Preview' USING errcode='PT409'; END IF;

  SELECT state,generation INTO v_state FROM public.factory_project_execution_controls
  WHERE project_id=v_project.id FOR SHARE;
  IF NOT FOUND OR v_state.state IS DISTINCT FROM 'running'
    OR v_state.generation IS NULL OR v_state.generation < 1
    OR v_set.metadata->'integration_epoch_receipt'->>'generation'
          IS DISTINCT FROM v_state.generation::text
  THEN RAISE EXCEPTION 'project epoch or control state drift' USING errcode='PT409'; END IF;

  SELECT * INTO v_run FROM public.factory_runs WHERE id=p_run_id FOR UPDATE;
  IF NOT FOUND OR v_run.status IS DISTINCT FROM 'failed'
    OR v_run.candidate_commit IS DISTINCT FROM p_previous_commit
    OR v_run.branch_name IS DISTINCT FROM v_set.integration_branch
    OR v_run.branch_name IS DISTINCT FROM p_verified_github->>'head_ref'
    OR v_run.metadata->>'change_set_id' IS DISTINCT FROM v_set.id::text
    OR v_run.metadata->>'execution_generation' IS DISTINCT FROM v_state.generation::text
    OR v_run.lease_owner IS NOT NULL OR v_run.lease_expires_at IS NOT NULL
  THEN RAISE EXCEPTION 'failed run provenance changed' USING errcode='PT409'; END IF;

  SELECT * INTO v_task FROM public.factory_tasks WHERE id=v_run.task_id FOR UPDATE;
  IF NOT FOUND OR v_task.status IS DISTINCT FROM 'failed'
    OR v_task.project_id IS DISTINCT FROM v_set.project_id
  THEN RAISE EXCEPTION 'failed task linkage changed' USING errcode='PT409'; END IF;

  IF v_set.metadata->'integration_release_request'->>'candidate_commit'
         IS DISTINCT FROM p_previous_commit
    OR v_set.metadata->'integration_release_request'->>'pr_number'
         IS DISTINCT FROM p_pr_number::text
    OR v_set.metadata->'integration_release_request'->>'branch'
         IS DISTINCT FROM v_set.integration_branch
    OR v_set.metadata->'integration_epoch_receipt'->>'candidate_commit'
         IS DISTINCT FROM p_previous_commit
    OR v_set.metadata->'integration_epoch_receipt'->>'project_id'
         IS DISTINCT FROM v_project.id::text
  THEN RAISE EXCEPTION 'immutable release request lineage drift' USING errcode='PT409'; END IF;

  SELECT u.metadata INTO v_original FROM public.factory_tool_usage u
  WHERE u.run_id=p_run_id AND u.operation='create_pr' ORDER BY u.id DESC LIMIT 1;
  IF NOT FOUND OR v_original.metadata->>'pr' IS DISTINCT FROM p_pr_number::text
    OR v_original.metadata->>'change_set_id' IS DISTINCT FROM v_set.id::text
    OR coalesce(v_original.metadata->>'head_sha','') !~ '^[0-9a-f]{40}$'
  THEN RAISE EXCEPTION 'original PR creation receipt missing' USING errcode='PT409'; END IF;

  SELECT u.metadata INTO v_last FROM public.factory_tool_usage u
  WHERE u.run_id=p_run_id AND u.operation='reconcile_pr_candidate'
  ORDER BY u.id DESC LIMIT 1;
  IF NOT FOUND OR v_last.metadata->>'candidate_commit' IS DISTINCT FROM p_previous_commit
    OR v_last.metadata->>'new_sha' IS DISTINCT FROM p_previous_commit
    OR v_last.metadata->>'pr_number' IS DISTINCT FROM p_pr_number::text
    OR v_last.metadata->>'change_set_id' IS DISTINCT FROM v_set.id::text
  THEN RAISE EXCEPTION 'prior audited SHA reconciliation missing' USING errcode='PT409'; END IF;

  SELECT count(*) INTO v_count FROM public.factory_tool_usage
  WHERE run_id=p_run_id AND operation='reconcile_pr_candidate';
  IF v_count < 1 OR v_count >= 8 THEN
    RAISE EXCEPTION 'bounded candidate lineage budget exhausted' USING errcode='PT409';
  END IF;

  -- Verify every audited transition, not merely the latest receipt.
  v_sha := p_previous_commit;
  v_seen := ARRAY[v_sha];
  FOR v_hop IN SELECT metadata AS proof FROM public.factory_tool_usage
    WHERE run_id=p_run_id AND operation='reconcile_pr_candidate'
    ORDER BY id DESC
  LOOP
    IF v_hop.proof->>'candidate_commit' IS DISTINCT FROM v_sha
      OR v_hop.proof->>'new_sha' IS DISTINCT FROM v_sha
      OR v_hop.proof->>'old_sha' IS DISTINCT FROM v_hop.proof->>'previous_commit'
      OR v_hop.proof->>'pr_number' IS DISTINCT FROM p_pr_number::text
      OR v_hop.proof->>'change_set_id' IS DISTINCT FROM v_set.id::text
      OR v_hop.proof->>'compare_status' IS DISTINCT FROM 'ahead'
      OR v_hop.proof->>'behind_by' IS DISTINCT FROM '0'
      OR coalesce((v_hop.proof->>'ahead_by') ~ '^[1-9][0-9]{0,5}$',false) IS NOT TRUE
    THEN RAISE EXCEPTION 'disconnected audited SHA chain' USING errcode='PT409'; END IF;
    v_sha := v_hop.proof->>'previous_commit';
    IF coalesce(v_sha,'') !~ '^[0-9a-f]{40}$' OR v_sha=ANY(v_seen) THEN
      RAISE EXCEPTION 'invalid audited SHA chain' USING errcode='PT409';
    END IF;
    v_seen := array_append(v_seen,v_sha);
  END LOOP;
  IF v_sha IS DISTINCT FROM v_original.metadata->>'head_sha' THEN
    RAISE EXCEPTION 'audited SHA chain does not reach original PR' USING errcode='PT409';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM public.factory_evaluations e
    WHERE e.run_id=p_run_id AND e.eval_type='github_ci' AND e.status='success'
      AND e.baseline_ref=p_previous_commit AND e.result->>'head_sha'=p_previous_commit)
    OR NOT EXISTS (SELECT 1 FROM public.factory_evaluations e
    WHERE e.run_id=p_run_id AND e.eval_type='quality_gate' AND e.status='success'
      AND e.baseline_ref=p_previous_commit AND e.result->>'passed'='true')
    OR NOT EXISTS (SELECT 1 FROM public.factory_specialist_lane_jobs j
    WHERE j.run_id=p_run_id AND j.required AND j.candidate_commit=p_previous_commit)
    OR EXISTS (SELECT 1 FROM public.factory_specialist_lane_jobs j
    WHERE j.run_id=p_run_id AND j.required
      AND (j.candidate_commit IS DISTINCT FROM p_previous_commit OR j.status <> 'passed'))
  THEN RAISE EXCEPTION 'prior exact-SHA CI/quality/specialists are not valid' USING errcode='PT409'; END IF;

  SELECT id,status,baseline_ref,result INTO v_browser
    FROM public.factory_evaluations
    WHERE run_id=p_run_id AND eval_type='browser_e2e'
    ORDER BY created_at DESC,id DESC LIMIT 1;
  IF NOT FOUND OR v_browser.status IS DISTINCT FROM 'failure'
    OR position('http_503: fetch /api/session' IN coalesce(v_browser.result->>'detail',''))=0
    OR v_browser.result->>'preview_url' IS DISTINCT FROM v_browser.baseline_ref
    OR EXISTS (SELECT 1 FROM public.factory_evaluations
      WHERE run_id=p_run_id AND eval_type='browser_e2e' AND status='success')
    OR NOT EXISTS (SELECT 1 FROM public.factory_deployments d
      WHERE d.run_id=p_run_id AND d.environment='preview' AND d.status='success'
        AND d.metadata->>'candidate_commit'=p_previous_commit
        AND d.metadata->>'preview_url'=v_browser.baseline_ref)
  THEN RAISE EXCEPTION 'historical environmental failure is not exact' USING errcode='PT409'; END IF;

  v_new_url:=p_verified_github->>'preview_url';
  IF v_new_url IS NULL OR
     v_new_url !~ '^https://[a-z0-9][a-z0-9-]*[.]vercel[.]app$'
     OR p_environment_probe->>'kind' IS DISTINCT FROM 'unauthenticated_json_session_probe'
     OR p_environment_probe->>'candidate_commit' IS DISTINCT FROM p_new_commit
     OR p_environment_probe->>'url' IS DISTINCT FROM v_new_url||'/api/session'
     OR coalesce(p_environment_probe->>'http_status','') NOT IN ('200','401')
     OR coalesce(p_environment_probe->>'content_type','') !~ '^application/json(;.*)?$'
     OR coalesce(p_environment_probe->>'checked_at','') !~
       '^20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}'
  THEN RAISE EXCEPTION 'new SHA Preview backend is not ready' USING errcode='PT400'; END IF;
  BEGIN
    v_checked:=(p_environment_probe->>'checked_at')::timestamptz;
  EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow THEN
    RAISE EXCEPTION 'invalid backend probe timestamp' USING errcode='PT400';
  END;
  IF v_checked > now()+interval '5 seconds'
     OR v_checked < now()-interval '10 minutes'
  THEN RAISE EXCEPTION 'backend readiness proof is stale' USING errcode='PT400'; END IF;

  -- Original rows and evaluations stay intact. New SHA must re-pass native
  -- CI, quality, all specialists and a FRESH browser E2E before release.
  UPDATE public.factory_runs SET candidate_commit=p_new_commit,status='ci_pending',
    finished_at=NULL,last_error=NULL,
    metadata=metadata||jsonb_build_object('greenfield_successor_recovery',
      jsonb_build_object('previous_commit',p_previous_commit,
        'historical_browser_failure_id',v_browser.id,
        'backend_probe_at',p_environment_probe->>'checked_at'))
  WHERE id=p_run_id;

  UPDATE public.factory_tasks SET status='integrated',updated_at=now()
    WHERE id=v_task.id;
  UPDATE public.factory_change_sets SET candidate_commit=p_new_commit,
    metadata=jsonb_set(
      jsonb_set(v_set.metadata,'{integration_release_request,candidate_commit}',
        to_jsonb(p_new_commit),false),
      '{integration_epoch_receipt,candidate_commit}',to_jsonb(p_new_commit),false),
    updated_at=now() WHERE id=v_set.id;

  INSERT INTO public.factory_tool_usage(
    run_id,tool_family,operation,usage_units,estimated_cost,metadata)
  VALUES (p_run_id,'github','reconcile_pr_candidate',1,0,
    p_verified_github||jsonb_build_object(
      'change_set_id',v_set.id,'previous_commit',p_previous_commit,
      'candidate_commit',p_new_commit,'old_sha',p_previous_commit,
      'new_sha',p_new_commit,'pr_number',p_pr_number::text));

  -- This is a *pending* E2E, never an invented PASS or proof of deployment.
  INSERT INTO public.factory_evaluations(
    run_id,eval_type,status,baseline_ref,result)
  VALUES (p_run_id,'browser_e2e','pending',v_new_url,
    jsonb_build_object('candidate_commit',p_new_commit,
      'reason','fresh_browser_required_after_greenfield_successor',
      'historical_browser_failure_id',v_browser.id,'browser_verified',false));

  INSERT INTO public.factory_audit_events(
    project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
  VALUES (v_project.id,v_task.id,p_run_id,'system',
    'greenfield-preview-environment-successor',
    'preview.backend_successor.requeued',
    jsonb_build_object('old_sha',p_previous_commit,'new_sha',p_new_commit,
      'pr_number',p_pr_number,'previous_browser_eval_id',v_browser.id,
      'new_browser_verified',false,'ci_verified_for_new_sha',false,
      'release_authorized',false,'ci_run_id',p_verified_github->>'ci_run_id'));
  RETURN jsonb_build_object('status','ci_pending','run_id',p_run_id,
    'candidate_commit',p_new_commit,'old_failure_preserved',true,
    'ci_quality_specialists_browser_must_rerun',true,'release_authorized',false);
END;
$recover$;
REVOKE ALL ON FUNCTION public.factory_recover_greenfield_backend_successor_v1(
 uuid,text,text,integer,jsonb,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.factory_recover_greenfield_backend_successor_v1(
 uuid,text,text,integer,jsonb,jsonb) TO service_role;
COMMIT;
