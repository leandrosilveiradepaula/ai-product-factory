-- Operator-verified human release: single transaction for project/snapshot/audit.
-- New endpoint: code deployed before SQL fails closed. No auto-merge/paid calls.
BEGIN;
CREATE OR REPLACE FUNCTION public.factory_reconcile_project_release_atomic(
 p_project_id uuid,p_run_id uuid,p_merge_sha text,p_followup jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path TO ''
AS $fn$
DECLARE proj public.factory_projects%rowtype;
 ctl public.factory_project_execution_controls%rowtype;
 run public.factory_runs%rowtype;
 rel public.factory_release_reports%rowtype;
 v_manifest jsonb; existing jsonb;
BEGIN
 IF p_merge_sha !~ '^[0-9a-f]{40}$'
 OR jsonb_typeof(p_followup)<>'object'
 OR p_followup->>'ready' IS DISTINCT FROM 'false'
 OR p_followup->>'scope' IS DISTINCT FROM 'current_product_after_release'
 OR p_followup->>'release_run_id' IS DISTINCT FROM p_run_id::text
 OR p_followup->>'merge_sha' IS DISTINCT FROM p_merge_sha
 OR p_followup->>'status' NOT IN ('not_assessed','not_ready','candidate_only','unknown')
 OR jsonb_typeof(p_followup->'pending_domains')<>'array'
 OR jsonb_array_length(p_followup->'pending_domains')<>6
 THEN RAISE EXCEPTION 'invalid product handoff' USING ERRCODE='PT409'; END IF;
 SELECT * INTO proj FROM public.factory_projects WHERE id=p_project_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'project not found' USING ERRCODE='PT409'; END IF;
 SELECT * INTO ctl FROM public.factory_project_execution_controls
 WHERE project_id=p_project_id FOR SHARE;
 IF NOT FOUND OR ctl.state <> 'running' OR ctl.generation<1
 THEN RAISE EXCEPTION 'project is not running' USING ERRCODE='PT409'; END IF;
 SELECT r.* INTO run FROM public.factory_runs r
 JOIN public.factory_tasks t ON t.id=r.task_id
 WHERE r.id=p_run_id AND t.project_id=p_project_id FOR UPDATE OF r;
 IF NOT FOUND OR run.status <> 'merged'
 THEN RAISE EXCEPTION 'human merge not observed on run' USING ERRCODE='PT409'; END IF;
 SELECT * INTO rel FROM public.factory_release_reports
 WHERE run_id=p_run_id AND project_id=p_project_id FOR SHARE;
 IF NOT FOUND OR rel.status <> 'released'
 OR rel.report->>'merge_sha' IS DISTINCT FROM p_merge_sha
 THEN RAISE EXCEPTION 'verified release report missing' USING ERRCODE='PT409'; END IF;
 IF run.candidate_commit IS DISTINCT FROM p_merge_sha
 AND run.candidate_commit IS DISTINCT FROM rel.candidate_commit
 THEN RAISE EXCEPTION 'candidate mismatch' USING ERRCODE='PT409'; END IF;
 v_manifest:=coalesce(proj.manifest,'{}'::jsonb);
 existing:=v_manifest->'last_release';
 IF existing->>'merge_sha'=p_merge_sha AND existing->>'run_id'=p_run_id::text
 AND proj.lifecycle_stage='operations' THEN
  RETURN jsonb_build_object('project_id',p_project_id,'merge_sha',p_merge_sha,
   'lifecycle_stage','operations','idempotent',true);
 END IF;
 IF existing->>'merge_sha' IS NOT NULL AND existing->>'merge_sha'<>p_merge_sha
 AND proj.lifecycle_stage='operations' THEN
  RAISE EXCEPTION 'new release requires new transition' USING ERRCODE='PT409';
 END IF;
 v_manifest:=(v_manifest-'current_task')||
 jsonb_build_object('head_sha',p_merge_sha,'reported_stage','operations',
  'last_release',jsonb_build_object('run_id',p_run_id,'merge_sha',p_merge_sha,'source','observed_human_merge'),
  'product_readiness_followup',p_followup);
 IF v_manifest->>'autonomy'='read_only_verification'
 THEN v_manifest:=v_manifest-'autonomy'; END IF;
 IF v_manifest->'runtime_readiness'->>'current_scope'='read_only_verification' THEN
  v_manifest:=jsonb_set(v_manifest,'{runtime_readiness}',
   (v_manifest->'runtime_readiness')-'current_scope');
 END IF;
 UPDATE public.factory_projects SET lifecycle_stage='operations',manifest=v_manifest
 WHERE id=p_project_id;
 INSERT INTO public.factory_project_state_snapshots(
 project_id,run_id,observed_stage,summary,evidence,gaps,constraints,source_status)
 VALUES(p_project_id,p_run_id,'operations',
 'Release humano observado; estado do projeto reconciliado com a entrega real.',
 jsonb_build_array(jsonb_build_object('type','human_release','merge_sha',p_merge_sha)),
 (SELECT coalesce(jsonb_agg(jsonb_build_object('kind','global_readiness_evidence_required',
  'domain',v.value,'reason_code',p_followup->>'reason_code')),'[]'::jsonb)
  FROM jsonb_array_elements_text(p_followup->'pending_domains') v(value)),
 '[]'::jsonb,jsonb_build_object('release','merged','product_readiness',
 p_followup->>'status','product_readiness_scope','current_product_after_release',
 'product_readiness_report_verified',p_followup->'report_verified'));
 INSERT INTO public.factory_audit_events(project_id,run_id,actor_type,actor_ref,event_type,payload)
 VALUES(p_project_id,p_run_id,'system','release-followup',
 'project.state.reconciled_after_release',
 jsonb_build_object('merge_sha',p_merge_sha,'lifecycle_stage','operations',
  'product_readiness',p_followup->>'status',
  'product_readiness_reason_code',p_followup->>'reason_code'));
 RETURN jsonb_build_object('project_id',p_project_id,'merge_sha',p_merge_sha,
  'lifecycle_stage','operations','idempotent',false);
END;
$fn$;
REVOKE ALL ON FUNCTION public.factory_reconcile_project_release_atomic(uuid,uuid,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.factory_reconcile_project_release_atomic(uuid,uuid,text,jsonb) TO service_role;
COMMIT;
