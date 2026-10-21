-- Recover only the CURRENT, already-human-merged release whose historical
-- REST handoff left product-readiness evidence incomplete. Versioned add-on to
-- the authorized 20261021090000 migration. Not applied to production by CI.
BEGIN;

CREATE OR REPLACE FUNCTION public.factory_pending_legacy_release_readiness_v1(
 p_after_project_id uuid DEFAULT NULL,p_limit integer DEFAULT 16
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path TO ''
AS $function$
DECLARE v_result jsonb;
BEGIN
 IF p_limit IS NULL OR p_limit<1 OR p_limit>16 THEN
  RAISE EXCEPTION 'invalid bounded legacy release scan' USING errcode='PT409';
 END IF;
 SELECT COALESCE(jsonb_agg(jsonb_build_object(
    'project_id',q.project_id,'run_id',q.run_id,'merge_sha',q.merge_sha
 ) ORDER BY q.project_id),'[]'::jsonb)
 INTO v_result
 FROM (
  SELECT p.id AS project_id,rr.run_id,rr.report->>'merge_sha' AS merge_sha
  FROM public.factory_projects p
  JOIN public.factory_project_execution_controls c
    ON c.project_id=p.id AND c.state='running' AND c.generation>0
  JOIN public.factory_release_reports rr
    ON rr.project_id=p.id
   AND rr.run_id::text=(p.manifest #>> '{last_release,run_id}')
  JOIN public.factory_runs r
    ON r.id=rr.run_id AND r.status='merged'
   AND r.candidate_commit=rr.report->>'merge_sha'
  JOIN public.factory_tasks t
    ON t.id=r.task_id AND t.project_id=p.id
  WHERE p.is_active IS TRUE AND p.lifecycle_stage='operations'
    AND (p_after_project_id IS NULL OR p.id>p_after_project_id)
    AND rr.status='released'
    AND rr.candidate_commit ~ '^[0-9a-f]{40}$'
    AND rr.report->>'released_by'='observed_manual_merge'
    AND rr.report->>'merge_sha' ~ '^[0-9a-f]{40}$'
    AND rr.report->>'merge_sha'=(p.manifest #>> '{last_release,merge_sha}')
    AND (p.manifest #>> '{last_release,source}')='observed_human_merge'
    AND (r.metadata->>'execution_generation' IS NULL
      OR r.metadata->>'execution_generation'=c.generation::text)
    -- Legacy audit rows may have project_id NULL. Run + exact SHA is binding.
    AND EXISTS(
      SELECT 1 FROM public.factory_audit_events e
      WHERE e.run_id=rr.run_id
       AND e.event_type='release.human_merge_observed'
       AND e.payload->>'merge_sha'=rr.report->>'merge_sha'
    )
    -- A historical release can never replace a newer human release.
    AND NOT EXISTS(
      SELECT 1 FROM public.factory_release_reports newer
      WHERE newer.project_id=p.id AND newer.status='released'
       AND newer.id<>rr.id
       AND (newer.updated_at,newer.id)>(rr.updated_at,rr.id)
    )
    AND NOT EXISTS(
      SELECT 1 FROM public.factory_audit_events parked
      WHERE parked.project_id=p.id AND parked.run_id=rr.run_id
       AND parked.event_type='release.legacy_readiness_needs_review'
       AND parked.payload->>'merge_sha'=rr.report->>'merge_sha'
    )
    AND (
      jsonb_typeof(p.manifest->'product_readiness_followup') IS DISTINCT FROM 'object'
      OR p.manifest #>> '{product_readiness_followup,scope}'
        IS DISTINCT FROM 'current_product_after_release'
      OR p.manifest #>> '{product_readiness_followup,release_run_id}'
        IS DISTINCT FROM rr.run_id::text
      OR p.manifest #>> '{product_readiness_followup,merge_sha}'
        IS DISTINCT FROM rr.report->>'merge_sha'
      OR p.manifest #> '{product_readiness_followup,ready}'
        IS DISTINCT FROM 'false'::jsonb
      OR p.manifest #> '{product_readiness_followup,report_verified}'
        IS DISTINCT FROM 'true'::jsonb
      OR p.manifest #> '{product_readiness_followup,pending_domains}'
        IS DISTINCT FROM '["security","observability_operations","test_strategy","product_experience","documentation","functional_completeness"]'::jsonb
      OR NOT EXISTS(
       SELECT 1 FROM public.factory_project_state_snapshots s
       WHERE s.project_id=p.id AND s.run_id=rr.run_id
         AND s.observed_stage='operations'
         AND s.source_status->>'product_readiness_scope'='current_product_after_release'
         AND s.source_status->>'product_readiness_report_verified'='true'
         AND s.evidence @> jsonb_build_array(jsonb_build_object(
           'type','human_release','merge_sha',rr.report->>'merge_sha'))
         AND jsonb_typeof(s.gaps)='array'
         AND jsonb_array_length(s.gaps)=6
         AND s.gaps @> '[
            {"kind":"global_readiness_evidence_required","domain":"security"},
            {"kind":"global_readiness_evidence_required","domain":"observability_operations"},
            {"kind":"global_readiness_evidence_required","domain":"test_strategy"},
            {"kind":"global_readiness_evidence_required","domain":"product_experience"},
            {"kind":"global_readiness_evidence_required","domain":"documentation"},
            {"kind":"global_readiness_evidence_required","domain":"functional_completeness"}
          ]'::jsonb
      )
    )
  ORDER BY p.id LIMIT p_limit
 ) q;
 RETURN v_result;
END;
$function$;

-- The project-control row is locked FIRST, then the project row. A pause
-- cannot race this transaction and a newer release cannot be overwritten.
-- The original v1 RPC remains the only writer of manifest/snapshot state.
CREATE OR REPLACE FUNCTION public.factory_reconcile_latest_legacy_release_v1(
 p_project_id uuid,p_run_id uuid,p_merge_sha text,
 p_release_report jsonb,p_followup jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path TO ''
AS $function$
DECLARE
 v_project public.factory_projects%rowtype;
 v_latest uuid;
 v_ctl_generation bigint;
 v_receipt jsonb;
 v_prior boolean;
 v_audit_written boolean:=false;
BEGIN
 IF p_merge_sha IS NULL OR p_merge_sha !~ '^[0-9a-f]{40}$' THEN
  RAISE EXCEPTION 'invalid legacy release SHA' USING errcode='PT409';
 END IF;
 SELECT generation INTO v_ctl_generation
 FROM public.factory_project_execution_controls
 WHERE project_id=p_project_id AND state='running' AND generation>0
 FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'legacy reconciliation waiting for Start/Resume'
  USING errcode='PT423'; END IF;
 SELECT * INTO v_project FROM public.factory_projects WHERE id=p_project_id FOR UPDATE;
 IF NOT FOUND OR v_project.is_active IS NOT TRUE
  OR v_project.lifecycle_stage<>'operations'
  OR v_project.manifest #>> '{last_release,run_id}' IS DISTINCT FROM p_run_id::text
  OR v_project.manifest #>> '{last_release,merge_sha}' IS DISTINCT FROM p_merge_sha
  OR v_project.manifest #>> '{last_release,source}' IS DISTINCT FROM 'observed_human_merge'
 THEN RAISE EXCEPTION 'legacy release no longer current' USING errcode='PT409'; END IF;
 SELECT rr.run_id INTO v_latest FROM public.factory_release_reports rr
 WHERE rr.project_id=p_project_id AND rr.status='released'
 ORDER BY rr.updated_at DESC,rr.id DESC LIMIT 1;
 IF v_latest IS DISTINCT FROM p_run_id THEN
  RAISE EXCEPTION 'newer human release exists' USING errcode='PT409';
 END IF;
 IF NOT EXISTS(
   SELECT 1 FROM public.factory_audit_events e
   WHERE e.run_id=p_run_id AND e.event_type='release.human_merge_observed'
    AND e.payload->>'merge_sha'=p_merge_sha
 ) THEN
  RAISE EXCEPTION 'legacy human merge evidence missing' USING errcode='PT409';
 END IF;
 SELECT EXISTS(
   SELECT 1 FROM public.factory_audit_events e
   WHERE e.project_id=p_project_id AND e.run_id=p_run_id
    AND e.event_type='release.legacy_readiness_backfilled'
    AND e.payload->>'merge_sha'=p_merge_sha
 ) INTO v_prior;
 -- A single SQL transaction now repairs the current manifest and appends a
 -- correct six-domain snapshot (and audit) without touching old evidence.
 v_receipt:=public.factory_reconcile_observed_release_v1(
    p_project_id,p_run_id,p_merge_sha,p_release_report,p_followup);
 IF v_receipt->'product_ready' IS DISTINCT FROM 'false'::jsonb
    OR v_receipt->>'run_id' IS DISTINCT FROM p_run_id::text
    OR v_receipt->>'merge_sha' IS DISTINCT FROM p_merge_sha
    OR v_receipt->>'lifecycle_stage' IS DISTINCT FROM 'operations' THEN
  RAISE EXCEPTION 'atomic legacy receipt inconsistent' USING errcode='PT409';
 END IF;
 IF v_receipt->'idempotent'='false'::jsonb AND NOT v_prior THEN
  INSERT INTO public.factory_audit_events(
   project_id,run_id,actor_type,actor_ref,event_type,payload
  ) VALUES(p_project_id,p_run_id,'system','legacy-release-readiness-recovery',
    'release.legacy_readiness_backfilled',
    jsonb_build_object('merge_sha',p_merge_sha,
      'original_human_merge_only',true,'product_ready',false,
      'pending_domains',6,'model_invoked',false,'automatic_merge',false));
  v_audit_written:=true;
 END IF;
 RETURN v_receipt||jsonb_build_object(
  'legacy_backfill',true,'backfill_audit_written',v_audit_written);
END;
$function$;

CREATE OR REPLACE FUNCTION public.factory_defer_legacy_release_readiness_v1(
 p_project_id uuid,p_run_id uuid,p_merge_sha text
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path TO ''
AS $function$
DECLARE
 v_project public.factory_projects%rowtype;
 v_already boolean;
 v_generation bigint;
BEGIN
 IF p_merge_sha IS NULL OR p_merge_sha !~ '^[0-9a-f]{40}$' THEN
  RAISE EXCEPTION 'invalid legacy deferral identity' USING errcode='PT409';
 END IF;
 SELECT generation INTO v_generation
 FROM public.factory_project_execution_controls
 WHERE project_id=p_project_id AND state='running' AND generation>0 FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'legacy deferral waiting for Start/Resume'
  USING errcode='PT423'; END IF;
 SELECT * INTO v_project FROM public.factory_projects WHERE id=p_project_id FOR UPDATE;
 IF NOT FOUND OR v_project.manifest #>> '{last_release,run_id}' IS DISTINCT FROM p_run_id::text
    OR v_project.manifest #>> '{last_release,merge_sha}' IS DISTINCT FROM p_merge_sha
    OR v_project.lifecycle_stage<>'operations'
 THEN RAISE EXCEPTION 'legacy deferral identity does not match latest release' USING errcode='PT409'; END IF;
 IF NOT EXISTS(
   SELECT 1 FROM public.factory_release_reports rr
   WHERE rr.project_id=p_project_id AND rr.run_id=p_run_id
    AND rr.status='released' AND rr.report->>'merge_sha'=p_merge_sha
 ) OR NOT EXISTS (
   SELECT 1 FROM public.factory_audit_events e
   WHERE e.run_id=p_run_id AND e.event_type='release.human_merge_observed'
    AND e.payload->>'merge_sha'=p_merge_sha
 ) THEN RAISE EXCEPTION 'legacy deferral release provenance missing' USING errcode='PT409'; END IF;
 SELECT EXISTS(
  SELECT 1 FROM public.factory_audit_events e
  WHERE e.project_id=p_project_id AND e.run_id=p_run_id
   AND e.event_type='release.legacy_readiness_needs_review'
   AND e.payload->>'merge_sha'=p_merge_sha
 ) INTO v_already;
 IF NOT v_already THEN
  INSERT INTO public.factory_audit_events(
    project_id,run_id,actor_type,actor_ref,event_type,payload)
  VALUES(p_project_id,p_run_id,'system','legacy-release-readiness-recovery',
    'release.legacy_readiness_needs_review',jsonb_build_object(
      'merge_sha',p_merge_sha,'automatic_replay',false,
      'reason_code','current_human_release_evidence_inconsistent'));
 END IF;
 RETURN jsonb_build_object(
   'project_id',p_project_id,'run_id',p_run_id,'merge_sha',p_merge_sha,
   'status','needs_review','idempotent',v_already);
END;
$function$;

REVOKE ALL ON FUNCTION public.factory_pending_legacy_release_readiness_v1(uuid,integer)
 FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.factory_pending_legacy_release_readiness_v1(uuid,integer)
 TO service_role;
REVOKE ALL ON FUNCTION public.factory_reconcile_latest_legacy_release_v1(uuid,uuid,text,jsonb,jsonb)
 FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.factory_reconcile_latest_legacy_release_v1(uuid,uuid,text,jsonb,jsonb)
 TO service_role;
REVOKE ALL ON FUNCTION public.factory_defer_legacy_release_readiness_v1(uuid,uuid,text)
 FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.factory_defer_legacy_release_readiness_v1(uuid,uuid,text)
 TO service_role;
COMMIT;
