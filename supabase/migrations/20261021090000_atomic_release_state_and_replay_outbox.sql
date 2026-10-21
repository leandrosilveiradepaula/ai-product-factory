-- A human merge observed in GitHub is not a complete project-state handoff.
-- Preserve this proof in a durable outbox and atomically commit project, snapshot,
-- readiness obligations and audit for the exact already-merged run.
-- Existing mark-released RPC is tightened, not granted merge authority.
-- This migration is code-only until explicit human production authorization.
BEGIN;

CREATE OR REPLACE FUNCTION public.factory_mark_release_report_released(
 p_run_id uuid,p_merge_sha text
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path TO ''
AS $function$
DECLARE
 v_report public.factory_release_reports%rowtype;
 v_project_id uuid;
 v_was_released boolean;
BEGIN
 IF p_merge_sha !~ '^[0-9a-f]{40}$' THEN
  RAISE EXCEPTION 'invalid human merge sha' USING errcode='PT409';
 END IF;
 SELECT * INTO v_report FROM public.factory_release_reports
 WHERE run_id=p_run_id FOR UPDATE;
 IF NOT FOUND OR v_report.status NOT IN ('ready_for_human_release','released') THEN
  RAISE EXCEPTION 'release report is not authorized for a human release' USING errcode='PT409';
 END IF;
 SELECT t.project_id INTO v_project_id
 FROM public.factory_runs r JOIN public.factory_tasks t ON t.id=r.task_id
 WHERE r.id=p_run_id AND r.status='merged' AND r.candidate_commit=p_merge_sha
   AND t.project_id=v_report.project_id FOR SHARE OF r,t;
 IF NOT FOUND THEN RAISE EXCEPTION 'run is not a merged release for project' USING errcode='PT409'; END IF;
 IF NOT EXISTS(
  SELECT 1 FROM public.factory_audit_events e
  WHERE e.run_id=p_run_id AND e.event_type='release.human_merge_observed'
    AND e.payload->>'merge_sha'=p_merge_sha
 ) THEN RAISE EXCEPTION 'human merge observation missing' USING errcode='PT409'; END IF;
 IF v_report.status='released'
    AND v_report.report->>'merge_sha' IS DISTINCT FROM p_merge_sha THEN
  RAISE EXCEPTION 'conflicting prior human release' USING errcode='PT409';
 END IF;
 v_was_released:=v_report.status='released';
 IF NOT v_was_released THEN
  UPDATE public.factory_release_reports
  SET status='released',report=report||jsonb_build_object(
        'merge_sha',p_merge_sha,'released_by','observed_manual_merge'),
      updated_at=now()
  WHERE id=v_report.id;
 END IF;
 -- The report row lock serializes repeated observations, so this marker is
 -- unique without weakening the existing fail-closed audit table/RLS.
 IF NOT EXISTS(
  SELECT 1 FROM public.factory_audit_events e
  WHERE e.project_id=v_project_id AND e.run_id=p_run_id
   AND e.event_type='release.reconciliation_requested'
   AND e.payload->>'merge_sha'=p_merge_sha
 ) THEN
  INSERT INTO public.factory_audit_events(
   project_id,run_id,actor_type,actor_ref,event_type,payload)
  VALUES(v_project_id,p_run_id,'system','release-followup',
   'release.reconciliation_requested',
   jsonb_build_object('merge_sha',p_merge_sha,'automatic_merge',false));
 END IF;
 RETURN jsonb_build_object('id',v_report.id,'status','released',
   'merge_sha',p_merge_sha,'idempotent',v_was_released);
END;
$function$;

CREATE OR REPLACE FUNCTION public.factory_pending_release_reconciliations_v1(
 p_after_event_id bigint DEFAULT 0,p_limit integer DEFAULT 16
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path TO ''
AS $function$
DECLARE v_result jsonb;
BEGIN
 IF p_after_event_id<0 OR p_after_event_id IS NULL
   OR p_limit IS NULL OR p_limit<1 OR p_limit>32 THEN
  RAISE EXCEPTION 'invalid bounded release scan' USING errcode='PT409';
 END IF;
 SELECT COALESCE(jsonb_agg(jsonb_build_object(
  'event_id',q.id,'project_id',q.project_id,
  'run_id',q.run_id,'merge_sha',q.merge_sha) ORDER BY q.id),'[]'::jsonb)
 INTO v_result
 FROM (
  SELECT e.id,e.project_id,e.run_id,e.payload->>'merge_sha' merge_sha
  FROM public.factory_audit_events e
  JOIN public.factory_projects p ON p.id=e.project_id AND p.is_active=true
  JOIN public.factory_project_execution_controls c ON c.project_id=e.project_id
    AND c.state='running' AND c.generation>0
  WHERE e.event_type='release.reconciliation_requested' AND e.id>p_after_event_id
    AND e.project_id IS NOT NULL AND e.run_id IS NOT NULL
    AND NOT EXISTS(
      SELECT 1 FROM public.factory_audit_events done
      WHERE done.project_id=e.project_id AND done.run_id=e.run_id
       AND done.event_type='project.state.reconciled_after_release'
       AND done.payload->>'merge_sha'=e.payload->>'merge_sha'
    )
    AND NOT EXISTS(
      SELECT 1 FROM public.factory_audit_events reviewed
      WHERE reviewed.project_id=e.project_id AND reviewed.run_id=e.run_id
       AND reviewed.event_type='release.reconciliation_needs_review'
       AND reviewed.payload->>'merge_sha'=e.payload->>'merge_sha'
       AND reviewed.payload->>'event_id'=e.id::text
    )
  ORDER BY e.id ASC LIMIT p_limit
 ) q;
 RETURN v_result;
END;
$function$;

CREATE OR REPLACE FUNCTION public.factory_reconcile_observed_release_v1(
 p_project_id uuid,p_run_id uuid,p_merge_sha text,
 p_release_report jsonb,p_followup jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path TO ''
AS $function$
DECLARE
 v_project public.factory_projects%rowtype;
 v_report public.factory_release_reports%rowtype;
 v_old_manifest jsonb;
 v_new_manifest jsonb;
 v_runtime jsonb;
 v_gaps jsonb;
 v_snapshot_done boolean;
 v_audit_done boolean;
 v_project_done boolean;
 v_written_snapshot boolean:=false;
 v_written_audit boolean:=false;
 v_generation bigint;
 v_set public.factory_change_sets%rowtype;
 v_set_count integer;
 v_set_updated boolean:=false;
BEGIN
 IF p_merge_sha IS NULL OR p_merge_sha !~ '^[0-9a-f]{40}$'
    OR jsonb_typeof(p_release_report) IS DISTINCT FROM 'object'
    OR jsonb_typeof(p_followup) IS DISTINCT FROM 'object'
    OR p_followup->>'scope' IS DISTINCT FROM 'current_product_after_release'
    OR p_followup->>'release_run_id' IS DISTINCT FROM p_run_id::text
    OR p_followup->>'merge_sha' IS DISTINCT FROM p_merge_sha
    OR p_followup->'ready' IS DISTINCT FROM 'false'::jsonb
    OR p_followup->'report_verified' IS DISTINCT FROM 'true'::jsonb
    OR COALESCE(p_followup->>'status','') NOT IN ('not_assessed','not_ready','candidate_only','unknown')
    OR COALESCE(p_followup->>'reason_code','') NOT IN (
       'global_readiness_not_assessed','candidate_readiness_not_ready',
       'candidate_assessment_not_current_head','global_readiness_evidence_incomplete'
     )
    OR jsonb_typeof(p_followup->'pending_domains') IS DISTINCT FROM 'array'
    OR jsonb_typeof(p_followup->'candidate_assessed_domains') IS DISTINCT FROM 'array' THEN
  RAISE EXCEPTION 'invalid fail-closed product readiness handoff' USING errcode='PT409';
 END IF;
 -- Reject a forged subset: the global auditor has exactly six domains.
 IF p_followup->'pending_domains' IS DISTINCT FROM
    '["security","observability_operations","test_strategy","product_experience","documentation","functional_completeness"]'::jsonb THEN
  RAISE EXCEPTION 'global readiness domains incomplete' USING errcode='PT409';
 END IF;
 IF jsonb_array_length(p_followup->'pending_domains')<1
    OR jsonb_array_length(p_followup->'pending_domains')>16
    OR EXISTS (
      SELECT 1 FROM jsonb_array_elements_text(p_followup->'pending_domains') x(domain)
      WHERE domain IS NULL OR domain !~ '^[a-z][a-z_0-9]{0,63}$'
    )
    OR (SELECT count(*) FROM jsonb_array_elements_text(p_followup->'pending_domains')) <>
       (SELECT count(DISTINCT domain) FROM jsonb_array_elements_text(p_followup->'pending_domains') x(domain)) THEN
  RAISE EXCEPTION 'invalid bounded readiness domains' USING errcode='PT409';
 END IF;

 -- Pause/Stop serializes against this lock. The outbox selector also
 -- excludes paused projects so they cannot starve other eligible projects.
 SELECT c.generation INTO v_generation
 FROM public.factory_project_execution_controls c
 WHERE c.project_id=p_project_id AND c.state='running' AND c.generation>0
 FOR SHARE OF c;
 IF NOT FOUND THEN RAISE EXCEPTION 'project release waiting for Start/Resume'
   USING errcode='PT423'; END IF;
 SELECT * INTO v_project FROM public.factory_projects
 WHERE id=p_project_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'release project not found' USING errcode='PT409'; END IF;
 IF v_project.is_active IS NOT TRUE THEN
  RAISE EXCEPTION 'release project inactive' USING errcode='PT423';
 END IF;

 SELECT rp.* INTO v_report FROM public.factory_release_reports rp
 JOIN public.factory_runs r ON r.id=rp.run_id
 JOIN public.factory_tasks t ON t.id=r.task_id
 WHERE rp.project_id=p_project_id AND rp.run_id=p_run_id
   AND rp.status='released' AND t.project_id=p_project_id
   AND r.status='merged' AND r.candidate_commit=p_merge_sha
   AND (r.metadata->>'execution_generation' IS NULL
        OR r.metadata->>'execution_generation'=v_generation::text)
   AND rp.candidate_commit ~ '^[0-9a-f]{40}$'
   AND rp.report=p_release_report
   AND rp.report->>'merge_sha'=p_merge_sha
   AND rp.report->>'released_by'='observed_manual_merge'
 FOR SHARE OF rp,r,t;
 IF NOT FOUND THEN
  RAISE EXCEPTION 'released report or merged run provenance not verified'
   USING errcode='PT409';
 END IF;
 IF NOT EXISTS(
  SELECT 1 FROM public.factory_audit_events e
  WHERE e.run_id=p_run_id AND e.event_type='release.human_merge_observed'
    AND e.payload->>'merge_sha'=p_merge_sha
 ) THEN RAISE EXCEPTION 'missing human merge receipt' USING errcode='PT409'; END IF;
 IF EXISTS(
  SELECT 1 FROM public.factory_release_reports newer
  WHERE newer.project_id=p_project_id AND newer.status='released'
    AND newer.id<>v_report.id AND newer.updated_at>v_report.updated_at
 ) THEN RAISE EXCEPTION 'stale release cannot overwrite newer observation'
    USING errcode='PT409';
 END IF;
 SELECT COALESCE(jsonb_agg(jsonb_build_object(
   'kind','global_readiness_evidence_required',
   'domain',domain,'reason_code',p_followup->>'reason_code'
  ) ORDER BY ord),'[]'::jsonb)
 INTO v_gaps
 FROM jsonb_array_elements_text(p_followup->'pending_domains')
      WITH ORDINALITY AS d(domain,ord);

 v_old_manifest:=COALESCE(v_project.manifest,'{}'::jsonb);
 v_runtime:=v_old_manifest->'runtime_readiness';
 IF jsonb_typeof(v_runtime)='object'
    AND v_runtime->>'current_scope'='read_only_verification' THEN
  v_runtime:=v_runtime-'current_scope';
 END IF;
 v_new_manifest:=(v_old_manifest-'current_task')||jsonb_build_object(
  'head_sha',p_merge_sha,
  'reported_stage','operations',
  'last_release',jsonb_build_object(
    'run_id',p_run_id,'merge_sha',p_merge_sha,'source','observed_human_merge'),
  'product_readiness_followup',p_followup
 );
 IF v_new_manifest->>'autonomy'='read_only_verification' THEN
  v_new_manifest:=v_new_manifest-'autonomy';
 END IF;
 IF jsonb_typeof(v_runtime)='object' THEN
  v_new_manifest:=jsonb_set(v_new_manifest,'{runtime_readiness}',v_runtime,true);
 END IF;
 -- A completed project with a ci_pending Change Set is still incomplete.
 -- Finalize its Change Set inside this very same release transaction.
 SELECT count(*) INTO v_set_count FROM public.factory_change_sets cs
 WHERE cs.release_run_id=p_run_id;
 IF v_set_count>1 THEN
  RAISE EXCEPTION 'multiple Change Sets reference release run' USING errcode='PT409';
 END IF;
 IF v_set_count=1 THEN
  SELECT * INTO v_set FROM public.factory_change_sets cs
  WHERE cs.release_run_id=p_run_id FOR UPDATE;
  IF v_set.project_id IS DISTINCT FROM p_project_id THEN
   RAISE EXCEPTION 'release Change Set project mismatch' USING errcode='PT409';
  END IF;
  IF v_set.status='ci_pending' THEN
   UPDATE public.factory_change_sets
   SET status='completed',
       metadata=coalesce(metadata,'{}'::jsonb)||jsonb_build_object(
         'release',jsonb_build_object('run_id',p_run_id,
            'merge_sha',p_merge_sha,'observed',true)),
       updated_at=now()
   WHERE id=v_set.id;
   v_set_updated:=true;
  ELSIF v_set.status='completed' THEN
   IF v_set.metadata->'release'->>'run_id' IS DISTINCT FROM p_run_id::text
      OR v_set.metadata->'release'->>'merge_sha' IS DISTINCT FROM p_merge_sha
      OR v_set.metadata->'release'->'observed' IS DISTINCT FROM 'true'::jsonb THEN
    RAISE EXCEPTION 'completed Change Set release receipt conflicts' USING errcode='PT409';
   END IF;
  ELSE
   RAISE EXCEPTION 'Change Set release is not eligible' USING errcode='PT409';
  END IF;
 END IF;

 v_project_done:=v_project.lifecycle_stage='operations'
   AND v_project.manifest=v_new_manifest;

 SELECT EXISTS(
  SELECT 1 FROM public.factory_project_state_snapshots s
  WHERE s.project_id=p_project_id AND s.run_id=p_run_id
    AND s.observed_stage='operations' AND s.gaps=v_gaps
    AND s.evidence @> jsonb_build_array(jsonb_build_object(
      'type','human_release','merge_sha',p_merge_sha))
    AND s.source_status->>'product_readiness'=p_followup->>'status'
    AND s.source_status->>'product_readiness_scope'='current_product_after_release'
 ) INTO v_snapshot_done;
 SELECT EXISTS(
  SELECT 1 FROM public.factory_audit_events e
  WHERE e.project_id=p_project_id AND e.run_id=p_run_id
    AND e.event_type='project.state.reconciled_after_release'
    AND e.payload->>'merge_sha'=p_merge_sha
 ) INTO v_audit_done;

 IF NOT v_project_done THEN
  UPDATE public.factory_projects
  SET lifecycle_stage='operations',manifest=v_new_manifest,updated_at=now()
  WHERE id=p_project_id;
 END IF;
 IF NOT v_snapshot_done THEN
  INSERT INTO public.factory_project_state_snapshots(
   project_id,run_id,observed_stage,summary,evidence,gaps,constraints,source_status)
  VALUES(
   p_project_id,p_run_id,'operations',
   'Release humano observado; estado do projeto reconciliado com a entrega real.',
   jsonb_build_array(jsonb_build_object('type','human_release','merge_sha',p_merge_sha)),
   v_gaps,'[]'::jsonb,jsonb_build_object(
    'release','merged',
    'product_readiness',p_followup->>'status',
    'product_readiness_scope','current_product_after_release',
    'product_readiness_report_verified',true)
  );
  v_written_snapshot:=true;
 END IF;
 IF NOT v_audit_done THEN
  INSERT INTO public.factory_audit_events(
   project_id,run_id,actor_type,actor_ref,event_type,payload)
  VALUES(p_project_id,p_run_id,'system','release-followup',
   'project.state.reconciled_after_release',jsonb_build_object(
    'merge_sha',p_merge_sha,'lifecycle_stage','operations',
    'product_readiness',p_followup->>'status',
    'product_readiness_reason_code',p_followup->>'reason_code'
   ));
  v_written_audit:=true;
 END IF;
 RETURN jsonb_build_object(
  'project_id',p_project_id,'run_id',p_run_id,
  'lifecycle_stage','operations','merge_sha',p_merge_sha,
  'product_ready',false,'pending_domains',jsonb_array_length(v_gaps),
  'idempotent',v_project_done AND v_snapshot_done AND v_audit_done,
  'snapshot_written',v_written_snapshot,'audit_written',v_written_audit,
  'change_set_status',CASE WHEN v_set_count=0 THEN 'not_change_set' ELSE 'completed' END,
  'change_set_updated',v_set_updated
 );
END;
$function$;


-- An unreconcilable, previously observed merge is not executable work.
-- Park its exact outbox event for explicit review; never retry it ahead
-- of another eligible project forever, never infer release permission.
CREATE OR REPLACE FUNCTION public.factory_defer_release_reconciliation_v1(
 p_event_id bigint
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path TO ''
AS $function$
DECLARE
 v_event public.factory_audit_events%rowtype;
 v_already boolean;
BEGIN
 IF p_event_id IS NULL OR p_event_id<1 THEN
  RAISE EXCEPTION 'invalid human release outbox identity' USING errcode='PT409';
 END IF;
 SELECT * INTO v_event FROM public.factory_audit_events
 WHERE id=p_event_id AND event_type='release.reconciliation_requested'
 FOR UPDATE;
 IF NOT FOUND OR v_event.project_id IS NULL OR v_event.run_id IS NULL
    OR COALESCE(v_event.payload->>'merge_sha','') !~ '^[0-9a-f]{40}$' THEN
  RAISE EXCEPTION 'human release outbox receipt missing' USING errcode='PT409';
 END IF;
 SELECT EXISTS(
  SELECT 1 FROM public.factory_audit_events e
  WHERE e.project_id=v_event.project_id AND e.run_id=v_event.run_id
    AND e.event_type='release.reconciliation_needs_review'
    AND e.payload->>'event_id'=p_event_id::text
    AND e.payload->>'merge_sha'=v_event.payload->>'merge_sha'
 ) INTO v_already;
 IF NOT v_already THEN
  INSERT INTO public.factory_audit_events(
   project_id,run_id,actor_type,actor_ref,event_type,payload
  ) VALUES(
   v_event.project_id,v_event.run_id,'system','release-reconciliation',
   'release.reconciliation_needs_review',
   jsonb_build_object('event_id',p_event_id,
                      'merge_sha',v_event.payload->>'merge_sha',
                      'reason_code','release_provenance_requires_review',
                      'automatic_replay',false)
  );
 END IF;
 RETURN jsonb_build_object(
  'event_id',p_event_id,'status','needs_review','idempotent',v_already);
END;
$function$;

REVOKE ALL ON FUNCTION public.factory_defer_release_reconciliation_v1(bigint)
 FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.factory_defer_release_reconciliation_v1(bigint)
 TO service_role;
REVOKE ALL ON FUNCTION public.factory_mark_release_report_released(uuid,text)
 FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.factory_mark_release_report_released(uuid,text)
 TO service_role;
REVOKE ALL ON FUNCTION public.factory_pending_release_reconciliations_v1(bigint,integer)
 FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.factory_pending_release_reconciliations_v1(bigint,integer)
 TO service_role;
REVOKE ALL ON FUNCTION public.factory_reconcile_observed_release_v1(uuid,uuid,text,jsonb,jsonb)
 FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.factory_reconcile_observed_release_v1(uuid,uuid,text,jsonb,jsonb)
 TO service_role;
COMMIT;
