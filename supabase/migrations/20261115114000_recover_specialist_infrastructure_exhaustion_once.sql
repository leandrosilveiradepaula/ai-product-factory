-- B4: bounded, one-time infrastructure recovery for an unchanged, independently
-- verified Change Set candidate. This migration alone NEVER queues a recovery.
-- Its service-role RPC is deliberately inert until a trusted caller proves
-- the GitHub source fix and original PR + current candidate SHA + CI identity.
--
-- Not a retry-policy increase. Ordinary specialists still get only three
-- attempts. A single explicit infrastructure-recovery grant can create one
-- additional three-attempt window for the same original specialist jobs.
-- No production merge, release, paid call, RLS policy or public access.
BEGIN;
CREATE OR REPLACE FUNCTION public.factory_resume_specialist_infrastructure_once_v1(
  p_run_id uuid,
  p_expected_candidate_sha text,
  p_expected_generation bigint,
  p_verified_factory_sha text,
  p_evidence_digest text,
  p_reason_code text
) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path TO ''
AS $function$
DECLARE
  v_run public.factory_runs%rowtype;
  v_project_id uuid;
  v_generation bigint;
  v_set public.factory_change_sets%rowtype;
  v_previous jsonb;
  v_details jsonb;
  v_jobs integer;
  v_eligible integer;
  v_marker jsonb;
BEGIN
  IF p_run_id IS NULL
    OR p_expected_candidate_sha IS NULL
    OR p_verified_factory_sha IS NULL
    OR p_evidence_digest IS NULL
    OR p_expected_candidate_sha !~ '^[0-9a-f]{40}
    OR p_expected_generation IS NULL OR p_expected_generation < 1
    OR coalesce(p_reason_code, '') !~ '^[a-z][a-z0-9_]{3,63}$'
  THEN
    RAISE EXCEPTION 'invalid specialist infrastructure recovery identity'
      USING errcode='PT400';
  END IF;

  -- Operator Stop/Pause/Resume cannot race a recovery or resurrect a stale
  -- execution epoch. Hold project-control locks through both writes and audit.
  SELECT t.project_id INTO v_project_id
  FROM public.factory_runs r JOIN public.factory_tasks t ON t.id=r.task_id
  WHERE r.id=p_run_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'source run not found' USING errcode='PT409';
  END IF;

  SELECT c.generation INTO v_generation
  FROM public.factory_project_execution_controls c
  JOIN public.factory_projects p ON p.id=c.project_id
  WHERE c.project_id=v_project_id
    AND p.is_active=true AND c.state='running' AND c.generation=p_expected_generation
  FOR SHARE OF c,p;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'source project is stopped, paused or in a different epoch'
      USING errcode='PT409';
  END IF;

  SELECT * INTO v_run FROM public.factory_runs WHERE id=p_run_id FOR UPDATE;
  IF v_run.task_id IS NULL OR v_run.candidate_commit IS DISTINCT FROM p_expected_candidate_sha
    OR v_run.metadata->>'execution_generation' IS DISTINCT FROM v_generation::text
    OR v_run.metadata->>'source' IS DISTINCT FROM 'change-set'
  THEN
    RAISE EXCEPTION 'source run candidate or execution epoch changed'
      USING errcode='PT409';
  END IF;

  v_marker:=jsonb_build_object(
    'candidate_sha',p_expected_candidate_sha,
    'factory_sha',p_verified_factory_sha,
    'evidence_digest',p_evidence_digest,
    'reason_code',p_reason_code
  );
  v_previous:=v_run.metadata->'specialist_infrastructure_recovery_v1';
  IF v_previous IS NOT NULL THEN
    IF v_previous = v_marker THEN
      RETURN jsonb_build_object('run_id',p_run_id,'requeued',false,
        'idempotent',true,'status',v_run.status,'release_authorized',false);
    END IF;
    RAISE EXCEPTION 'specialist infrastructure recovery already consumed'
      USING errcode='PT409';
  END IF;

  IF v_run.status IS DISTINCT FROM 'specialist_review_failed'
    OR v_run.metadata->'specialist_lanes'->>'required' IS DISTINCT FROM 'true'
    OR v_run.metadata->'specialist_lanes'->>'candidate_commit' IS DISTINCT FROM p_expected_candidate_sha
  THEN
    RAISE EXCEPTION 'source is not a failed required specialist review'
      USING errcode='PT409';
  END IF;

  -- Only a single original Change Set, same run/SHA, still awaiting its
  -- pre-release review. A released, superseded or leased Change Set is denied.
  SELECT * INTO v_set
  FROM public.factory_change_sets
  WHERE release_run_id=p_run_id AND project_id=v_project_id
    AND candidate_commit=p_expected_candidate_sha
  FOR UPDATE;
  IF NOT FOUND OR v_set.status IS DISTINCT FROM 'ci_pending'
    OR v_set.lease_owner IS NOT NULL OR v_set.lease_expires_at IS NOT NULL
  THEN
    RAISE EXCEPTION 'source Change Set is not the unchanged CI candidate'
      USING errcode='PT409';
  END IF;
  IF EXISTS(SELECT 1 FROM public.factory_repair_jobs WHERE source_run_id=p_run_id)
    OR EXISTS(SELECT 1 FROM public.factory_evaluations
              WHERE run_id=p_run_id AND eval_type LIKE 'specialist_%')
  THEN
    RAISE EXCEPTION 'completed reviews or repairs cannot be replayed'
      USING errcode='PT409';
  END IF;

  -- Strictly the original three roles, exactly three failed infrastructure
  -- leases each. A real review failure, mixed-SHA history or unexpired claim
  -- cannot be relabeled as infrastructure failure.
  SELECT count(*),
    count(*) FILTER (WHERE
      j.role IN ('qa','security','operations')
      AND j.required=true
      AND j.candidate_commit=p_expected_candidate_sha
      AND j.status='blocked' AND j.attempt_count=3
      AND j.lease_owner IS NULL AND j.lease_expires_at IS NULL
      AND j.completed_at IS NOT NULL
      AND j.evidence->>'_factory_epoch'=v_generation::text
      AND jsonb_typeof(j.findings)='array'
      AND jsonb_array_length(j.findings)=1
      AND j.findings->0->>'code'='specialist_retry_exhausted')
    INTO v_jobs,v_eligible
  FROM public.factory_specialist_lane_jobs j WHERE j.run_id=p_run_id;
  IF v_jobs<>3 OR v_eligible<>3 THEN
    RAISE EXCEPTION 'source specialist jobs are not exactly infrastructure-exhausted'
      USING errcode='PT409';
  END IF;

  SELECT jsonb_agg(jsonb_build_object('job_id',j.id,'role',j.role,
      'previous_attempts',j.attempt_count) ORDER BY j.role)
  INTO v_details
  FROM public.factory_specialist_lane_jobs j WHERE j.run_id=p_run_id;

  -- Invalidate old claim tokens; preserve original epoch and immutable audit
  -- history. The ordinary claim path will issue a NEW token for each role.
  UPDATE public.factory_specialist_lane_jobs j
  SET status='queued',attempt_count=0,
    lease_owner=NULL,lease_expires_at=NULL,completed_at=NULL,
    findings='[]'::jsonb,
    evidence=(j.evidence-'_factory_claim_token')
       || jsonb_build_object('_factory_infra_replay_sha',p_verified_factory_sha),
    updated_at=now()
  WHERE j.run_id=p_run_id
    AND j.candidate_commit=p_expected_candidate_sha
    AND j.status='blocked';

  UPDATE public.factory_runs
  SET status='specialist_review_pending',
      metadata=metadata||jsonb_build_object(
        'specialist_infrastructure_recovery_v1',v_marker)
  WHERE id=p_run_id;

  INSERT INTO public.factory_audit_events(
    project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
  VALUES(v_project_id,v_run.task_id,p_run_id,'system','specialist-infra-recovery',
    'specialist.lanes.infrastructure_requeued',
    jsonb_build_object('change_set_id',v_set.id,'candidate_sha',p_expected_candidate_sha,
      'factory_sha',p_verified_factory_sha,'evidence_digest',p_evidence_digest,
      'reason_code',p_reason_code,'old_jobs',v_details,'requeued',3,
      'release_authorized',false,'paid_calls',0));

  RETURN jsonb_build_object('run_id',p_run_id,'requeued',true,
    'roles',3,'status','specialist_review_pending','release_authorized',false);
END;
$function$;
REVOKE ALL ON FUNCTION public.factory_resume_specialist_infrastructure_once_v1(
  uuid,text,bigint,text,text,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.factory_resume_specialist_infrastructure_once_v1(
  uuid,text,bigint,text,text,text) TO service_role;
COMMIT;

    OR p_verified_factory_sha !~ '^[0-9a-f]{40}
    OR p_expected_generation IS NULL OR p_expected_generation < 1
    OR coalesce(p_reason_code, '') !~ '^[a-z][a-z0-9_]{3,63}$'
  THEN
    RAISE EXCEPTION 'invalid specialist infrastructure recovery identity'
      USING errcode='PT400';
  END IF;

  -- Operator Stop/Pause/Resume cannot race a recovery or resurrect a stale
  -- execution epoch. Hold project-control locks through both writes and audit.
  SELECT t.project_id INTO v_project_id
  FROM public.factory_runs r JOIN public.factory_tasks t ON t.id=r.task_id
  WHERE r.id=p_run_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'source run not found' USING errcode='PT409';
  END IF;

  SELECT c.generation INTO v_generation
  FROM public.factory_project_execution_controls c
  JOIN public.factory_projects p ON p.id=c.project_id
  WHERE c.project_id=v_project_id
    AND p.is_active=true AND c.state='running' AND c.generation=p_expected_generation
  FOR SHARE OF c,p;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'source project is stopped, paused or in a different epoch'
      USING errcode='PT409';
  END IF;

  SELECT * INTO v_run FROM public.factory_runs WHERE id=p_run_id FOR UPDATE;
  IF v_run.task_id IS NULL OR v_run.candidate_commit IS DISTINCT FROM p_expected_candidate_sha
    OR v_run.metadata->>'execution_generation' IS DISTINCT FROM v_generation::text
    OR v_run.metadata->>'source' IS DISTINCT FROM 'change-set'
  THEN
    RAISE EXCEPTION 'source run candidate or execution epoch changed'
      USING errcode='PT409';
  END IF;

  v_marker:=jsonb_build_object(
    'candidate_sha',p_expected_candidate_sha,
    'factory_sha',p_verified_factory_sha,
    'evidence_digest',p_evidence_digest,
    'reason_code',p_reason_code
  );
  v_previous:=v_run.metadata->'specialist_infrastructure_recovery_v1';
  IF v_previous IS NOT NULL THEN
    IF v_previous = v_marker THEN
      RETURN jsonb_build_object('run_id',p_run_id,'requeued',false,
        'idempotent',true,'status',v_run.status,'release_authorized',false);
    END IF;
    RAISE EXCEPTION 'specialist infrastructure recovery already consumed'
      USING errcode='PT409';
  END IF;

  IF v_run.status IS DISTINCT FROM 'specialist_review_failed'
    OR v_run.metadata->'specialist_lanes'->>'required' IS DISTINCT FROM 'true'
    OR v_run.metadata->'specialist_lanes'->>'candidate_commit' IS DISTINCT FROM p_expected_candidate_sha
  THEN
    RAISE EXCEPTION 'source is not a failed required specialist review'
      USING errcode='PT409';
  END IF;

  -- Only a single original Change Set, same run/SHA, still awaiting its
  -- pre-release review. A released, superseded or leased Change Set is denied.
  SELECT * INTO v_set
  FROM public.factory_change_sets
  WHERE release_run_id=p_run_id AND project_id=v_project_id
    AND candidate_commit=p_expected_candidate_sha
  FOR UPDATE;
  IF NOT FOUND OR v_set.status IS DISTINCT FROM 'ci_pending'
    OR v_set.lease_owner IS NOT NULL OR v_set.lease_expires_at IS NOT NULL
  THEN
    RAISE EXCEPTION 'source Change Set is not the unchanged CI candidate'
      USING errcode='PT409';
  END IF;
  IF EXISTS(SELECT 1 FROM public.factory_repair_jobs WHERE source_run_id=p_run_id)
    OR EXISTS(SELECT 1 FROM public.factory_evaluations
              WHERE run_id=p_run_id AND eval_type LIKE 'specialist_%')
  THEN
    RAISE EXCEPTION 'completed reviews or repairs cannot be replayed'
      USING errcode='PT409';
  END IF;

  -- Strictly the original three roles, exactly three failed infrastructure
  -- leases each. A real review failure, mixed-SHA history or unexpired claim
  -- cannot be relabeled as infrastructure failure.
  SELECT count(*),
    count(*) FILTER (WHERE
      j.role IN ('qa','security','operations')
      AND j.required=true
      AND j.candidate_commit=p_expected_candidate_sha
      AND j.status='blocked' AND j.attempt_count=3
      AND j.lease_owner IS NULL AND j.lease_expires_at IS NULL
      AND j.completed_at IS NOT NULL
      AND j.evidence->>'_factory_epoch'=v_generation::text
      AND jsonb_typeof(j.findings)='array'
      AND jsonb_array_length(j.findings)=1
      AND j.findings->0->>'code'='specialist_retry_exhausted')
    INTO v_jobs,v_eligible
  FROM public.factory_specialist_lane_jobs j WHERE j.run_id=p_run_id;
  IF v_jobs<>3 OR v_eligible<>3 THEN
    RAISE EXCEPTION 'source specialist jobs are not exactly infrastructure-exhausted'
      USING errcode='PT409';
  END IF;

  SELECT jsonb_agg(jsonb_build_object('job_id',j.id,'role',j.role,
      'previous_attempts',j.attempt_count) ORDER BY j.role)
  INTO v_details
  FROM public.factory_specialist_lane_jobs j WHERE j.run_id=p_run_id;

  -- Invalidate old claim tokens; preserve original epoch and immutable audit
  -- history. The ordinary claim path will issue a NEW token for each role.
  UPDATE public.factory_specialist_lane_jobs j
  SET status='queued',attempt_count=0,
    lease_owner=NULL,lease_expires_at=NULL,completed_at=NULL,
    findings='[]'::jsonb,
    evidence=(j.evidence-'_factory_claim_token')
       || jsonb_build_object('_factory_infra_replay_sha',p_verified_factory_sha),
    updated_at=now()
  WHERE j.run_id=p_run_id
    AND j.candidate_commit=p_expected_candidate_sha
    AND j.status='blocked';

  UPDATE public.factory_runs
  SET status='specialist_review_pending',
      metadata=metadata||jsonb_build_object(
        'specialist_infrastructure_recovery_v1',v_marker)
  WHERE id=p_run_id;

  INSERT INTO public.factory_audit_events(
    project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
  VALUES(v_project_id,v_run.task_id,p_run_id,'system','specialist-infra-recovery',
    'specialist.lanes.infrastructure_requeued',
    jsonb_build_object('change_set_id',v_set.id,'candidate_sha',p_expected_candidate_sha,
      'factory_sha',p_verified_factory_sha,'evidence_digest',p_evidence_digest,
      'reason_code',p_reason_code,'old_jobs',v_details,'requeued',3,
      'release_authorized',false,'paid_calls',0));

  RETURN jsonb_build_object('run_id',p_run_id,'requeued',true,
    'roles',3,'status','specialist_review_pending','release_authorized',false);
END;
$function$;
REVOKE ALL ON FUNCTION public.factory_resume_specialist_infrastructure_once_v1(
  uuid,text,bigint,text,text,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.factory_resume_specialist_infrastructure_once_v1(
  uuid,text,bigint,text,text,text) TO service_role;
COMMIT;

    OR p_evidence_digest !~ '^[0-9a-f]{64}
    OR p_expected_generation IS NULL OR p_expected_generation < 1
    OR coalesce(p_reason_code, '') !~ '^[a-z][a-z0-9_]{3,63}$'
  THEN
    RAISE EXCEPTION 'invalid specialist infrastructure recovery identity'
      USING errcode='PT400';
  END IF;

  -- Operator Stop/Pause/Resume cannot race a recovery or resurrect a stale
  -- execution epoch. Hold project-control locks through both writes and audit.
  SELECT t.project_id INTO v_project_id
  FROM public.factory_runs r JOIN public.factory_tasks t ON t.id=r.task_id
  WHERE r.id=p_run_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'source run not found' USING errcode='PT409';
  END IF;

  SELECT c.generation INTO v_generation
  FROM public.factory_project_execution_controls c
  JOIN public.factory_projects p ON p.id=c.project_id
  WHERE c.project_id=v_project_id
    AND p.is_active=true AND c.state='running' AND c.generation=p_expected_generation
  FOR SHARE OF c,p;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'source project is stopped, paused or in a different epoch'
      USING errcode='PT409';
  END IF;

  SELECT * INTO v_run FROM public.factory_runs WHERE id=p_run_id FOR UPDATE;
  IF v_run.task_id IS NULL OR v_run.candidate_commit IS DISTINCT FROM p_expected_candidate_sha
    OR v_run.metadata->>'execution_generation' IS DISTINCT FROM v_generation::text
    OR v_run.metadata->>'source' IS DISTINCT FROM 'change-set'
  THEN
    RAISE EXCEPTION 'source run candidate or execution epoch changed'
      USING errcode='PT409';
  END IF;

  v_marker:=jsonb_build_object(
    'candidate_sha',p_expected_candidate_sha,
    'factory_sha',p_verified_factory_sha,
    'evidence_digest',p_evidence_digest,
    'reason_code',p_reason_code
  );
  v_previous:=v_run.metadata->'specialist_infrastructure_recovery_v1';
  IF v_previous IS NOT NULL THEN
    IF v_previous = v_marker THEN
      RETURN jsonb_build_object('run_id',p_run_id,'requeued',false,
        'idempotent',true,'status',v_run.status,'release_authorized',false);
    END IF;
    RAISE EXCEPTION 'specialist infrastructure recovery already consumed'
      USING errcode='PT409';
  END IF;

  IF v_run.status IS DISTINCT FROM 'specialist_review_failed'
    OR v_run.metadata->'specialist_lanes'->>'required' IS DISTINCT FROM 'true'
    OR v_run.metadata->'specialist_lanes'->>'candidate_commit' IS DISTINCT FROM p_expected_candidate_sha
  THEN
    RAISE EXCEPTION 'source is not a failed required specialist review'
      USING errcode='PT409';
  END IF;

  -- Only a single original Change Set, same run/SHA, still awaiting its
  -- pre-release review. A released, superseded or leased Change Set is denied.
  SELECT * INTO v_set
  FROM public.factory_change_sets
  WHERE release_run_id=p_run_id AND project_id=v_project_id
    AND candidate_commit=p_expected_candidate_sha
  FOR UPDATE;
  IF NOT FOUND OR v_set.status IS DISTINCT FROM 'ci_pending'
    OR v_set.lease_owner IS NOT NULL OR v_set.lease_expires_at IS NOT NULL
  THEN
    RAISE EXCEPTION 'source Change Set is not the unchanged CI candidate'
      USING errcode='PT409';
  END IF;
  IF EXISTS(SELECT 1 FROM public.factory_repair_jobs WHERE source_run_id=p_run_id)
    OR EXISTS(SELECT 1 FROM public.factory_evaluations
              WHERE run_id=p_run_id AND eval_type LIKE 'specialist_%')
  THEN
    RAISE EXCEPTION 'completed reviews or repairs cannot be replayed'
      USING errcode='PT409';
  END IF;

  -- Strictly the original three roles, exactly three failed infrastructure
  -- leases each. A real review failure, mixed-SHA history or unexpired claim
  -- cannot be relabeled as infrastructure failure.
  SELECT count(*),
    count(*) FILTER (WHERE
      j.role IN ('qa','security','operations')
      AND j.required=true
      AND j.candidate_commit=p_expected_candidate_sha
      AND j.status='blocked' AND j.attempt_count=3
      AND j.lease_owner IS NULL AND j.lease_expires_at IS NULL
      AND j.completed_at IS NOT NULL
      AND j.evidence->>'_factory_epoch'=v_generation::text
      AND jsonb_typeof(j.findings)='array'
      AND jsonb_array_length(j.findings)=1
      AND j.findings->0->>'code'='specialist_retry_exhausted')
    INTO v_jobs,v_eligible
  FROM public.factory_specialist_lane_jobs j WHERE j.run_id=p_run_id;
  IF v_jobs<>3 OR v_eligible<>3 THEN
    RAISE EXCEPTION 'source specialist jobs are not exactly infrastructure-exhausted'
      USING errcode='PT409';
  END IF;

  SELECT jsonb_agg(jsonb_build_object('job_id',j.id,'role',j.role,
      'previous_attempts',j.attempt_count) ORDER BY j.role)
  INTO v_details
  FROM public.factory_specialist_lane_jobs j WHERE j.run_id=p_run_id;

  -- Invalidate old claim tokens; preserve original epoch and immutable audit
  -- history. The ordinary claim path will issue a NEW token for each role.
  UPDATE public.factory_specialist_lane_jobs j
  SET status='queued',attempt_count=0,
    lease_owner=NULL,lease_expires_at=NULL,completed_at=NULL,
    findings='[]'::jsonb,
    evidence=(j.evidence-'_factory_claim_token')
       || jsonb_build_object('_factory_infra_replay_sha',p_verified_factory_sha),
    updated_at=now()
  WHERE j.run_id=p_run_id
    AND j.candidate_commit=p_expected_candidate_sha
    AND j.status='blocked';

  UPDATE public.factory_runs
  SET status='specialist_review_pending',
      metadata=metadata||jsonb_build_object(
        'specialist_infrastructure_recovery_v1',v_marker)
  WHERE id=p_run_id;

  INSERT INTO public.factory_audit_events(
    project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
  VALUES(v_project_id,v_run.task_id,p_run_id,'system','specialist-infra-recovery',
    'specialist.lanes.infrastructure_requeued',
    jsonb_build_object('change_set_id',v_set.id,'candidate_sha',p_expected_candidate_sha,
      'factory_sha',p_verified_factory_sha,'evidence_digest',p_evidence_digest,
      'reason_code',p_reason_code,'old_jobs',v_details,'requeued',3,
      'release_authorized',false,'paid_calls',0));

  RETURN jsonb_build_object('run_id',p_run_id,'requeued',true,
    'roles',3,'status','specialist_review_pending','release_authorized',false);
END;
$function$;
REVOKE ALL ON FUNCTION public.factory_resume_specialist_infrastructure_once_v1(
  uuid,text,bigint,text,text,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.factory_resume_specialist_infrastructure_once_v1(
  uuid,text,bigint,text,text,text) TO service_role;
COMMIT;

    OR p_expected_generation IS NULL OR p_expected_generation < 1
    OR coalesce(p_reason_code, '') !~ '^[a-z][a-z0-9_]{3,63}$'
  THEN
    RAISE EXCEPTION 'invalid specialist infrastructure recovery identity'
      USING errcode='PT400';
  END IF;

  -- Operator Stop/Pause/Resume cannot race a recovery or resurrect a stale
  -- execution epoch. Hold project-control locks through both writes and audit.
  SELECT t.project_id INTO v_project_id
  FROM public.factory_runs r JOIN public.factory_tasks t ON t.id=r.task_id
  WHERE r.id=p_run_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'source run not found' USING errcode='PT409';
  END IF;

  SELECT c.generation INTO v_generation
  FROM public.factory_project_execution_controls c
  JOIN public.factory_projects p ON p.id=c.project_id
  WHERE c.project_id=v_project_id
    AND p.is_active=true AND c.state='running' AND c.generation=p_expected_generation
  FOR SHARE OF c,p;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'source project is stopped, paused or in a different epoch'
      USING errcode='PT409';
  END IF;

  SELECT * INTO v_run FROM public.factory_runs WHERE id=p_run_id FOR UPDATE;
  IF v_run.task_id IS NULL OR v_run.candidate_commit IS DISTINCT FROM p_expected_candidate_sha
    OR v_run.metadata->>'execution_generation' IS DISTINCT FROM v_generation::text
    OR v_run.metadata->>'source' IS DISTINCT FROM 'change-set'
  THEN
    RAISE EXCEPTION 'source run candidate or execution epoch changed'
      USING errcode='PT409';
  END IF;

  v_marker:=jsonb_build_object(
    'candidate_sha',p_expected_candidate_sha,
    'factory_sha',p_verified_factory_sha,
    'evidence_digest',p_evidence_digest,
    'reason_code',p_reason_code
  );
  v_previous:=v_run.metadata->'specialist_infrastructure_recovery_v1';
  IF v_previous IS NOT NULL THEN
    IF v_previous = v_marker THEN
      RETURN jsonb_build_object('run_id',p_run_id,'requeued',false,
        'idempotent',true,'status',v_run.status,'release_authorized',false);
    END IF;
    RAISE EXCEPTION 'specialist infrastructure recovery already consumed'
      USING errcode='PT409';
  END IF;

  IF v_run.status IS DISTINCT FROM 'specialist_review_failed'
    OR v_run.metadata->'specialist_lanes'->>'required' IS DISTINCT FROM 'true'
    OR v_run.metadata->'specialist_lanes'->>'candidate_commit' IS DISTINCT FROM p_expected_candidate_sha
  THEN
    RAISE EXCEPTION 'source is not a failed required specialist review'
      USING errcode='PT409';
  END IF;

  -- Only a single original Change Set, same run/SHA, still awaiting its
  -- pre-release review. A released, superseded or leased Change Set is denied.
  SELECT * INTO v_set
  FROM public.factory_change_sets
  WHERE release_run_id=p_run_id AND project_id=v_project_id
    AND candidate_commit=p_expected_candidate_sha
  FOR UPDATE;
  IF NOT FOUND OR v_set.status IS DISTINCT FROM 'ci_pending'
    OR v_set.lease_owner IS NOT NULL OR v_set.lease_expires_at IS NOT NULL
  THEN
    RAISE EXCEPTION 'source Change Set is not the unchanged CI candidate'
      USING errcode='PT409';
  END IF;
  IF EXISTS(SELECT 1 FROM public.factory_repair_jobs WHERE source_run_id=p_run_id)
    OR EXISTS(SELECT 1 FROM public.factory_evaluations
              WHERE run_id=p_run_id AND eval_type LIKE 'specialist_%')
  THEN
    RAISE EXCEPTION 'completed reviews or repairs cannot be replayed'
      USING errcode='PT409';
  END IF;

  -- Strictly the original three roles, exactly three failed infrastructure
  -- leases each. A real review failure, mixed-SHA history or unexpired claim
  -- cannot be relabeled as infrastructure failure.
  SELECT count(*),
    count(*) FILTER (WHERE
      j.role IN ('qa','security','operations')
      AND j.required=true
      AND j.candidate_commit=p_expected_candidate_sha
      AND j.status='blocked' AND j.attempt_count=3
      AND j.lease_owner IS NULL AND j.lease_expires_at IS NULL
      AND j.completed_at IS NOT NULL
      AND j.evidence->>'_factory_epoch'=v_generation::text
      AND jsonb_typeof(j.findings)='array'
      AND jsonb_array_length(j.findings)=1
      AND j.findings->0->>'code'='specialist_retry_exhausted')
    INTO v_jobs,v_eligible
  FROM public.factory_specialist_lane_jobs j WHERE j.run_id=p_run_id;
  IF v_jobs<>3 OR v_eligible<>3 THEN
    RAISE EXCEPTION 'source specialist jobs are not exactly infrastructure-exhausted'
      USING errcode='PT409';
  END IF;

  SELECT jsonb_agg(jsonb_build_object('job_id',j.id,'role',j.role,
      'previous_attempts',j.attempt_count) ORDER BY j.role)
  INTO v_details
  FROM public.factory_specialist_lane_jobs j WHERE j.run_id=p_run_id;

  -- Invalidate old claim tokens; preserve original epoch and immutable audit
  -- history. The ordinary claim path will issue a NEW token for each role.
  UPDATE public.factory_specialist_lane_jobs j
  SET status='queued',attempt_count=0,
    lease_owner=NULL,lease_expires_at=NULL,completed_at=NULL,
    findings='[]'::jsonb,
    evidence=(j.evidence-'_factory_claim_token')
       || jsonb_build_object('_factory_infra_replay_sha',p_verified_factory_sha),
    updated_at=now()
  WHERE j.run_id=p_run_id
    AND j.candidate_commit=p_expected_candidate_sha
    AND j.status='blocked';

  UPDATE public.factory_runs
  SET status='specialist_review_pending',
      metadata=metadata||jsonb_build_object(
        'specialist_infrastructure_recovery_v1',v_marker)
  WHERE id=p_run_id;

  INSERT INTO public.factory_audit_events(
    project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
  VALUES(v_project_id,v_run.task_id,p_run_id,'system','specialist-infra-recovery',
    'specialist.lanes.infrastructure_requeued',
    jsonb_build_object('change_set_id',v_set.id,'candidate_sha',p_expected_candidate_sha,
      'factory_sha',p_verified_factory_sha,'evidence_digest',p_evidence_digest,
      'reason_code',p_reason_code,'old_jobs',v_details,'requeued',3,
      'release_authorized',false,'paid_calls',0));

  RETURN jsonb_build_object('run_id',p_run_id,'requeued',true,
    'roles',3,'status','specialist_review_pending','release_authorized',false);
END;
$function$;
REVOKE ALL ON FUNCTION public.factory_resume_specialist_infrastructure_once_v1(
  uuid,text,bigint,text,text,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.factory_resume_specialist_infrastructure_once_v1(
  uuid,text,bigint,text,text,text) TO service_role;
COMMIT;
