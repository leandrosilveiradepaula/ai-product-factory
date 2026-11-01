-- Audited, one-time requeue of a V2 Work Unit blocked solely by stale
-- task-specific repository governance. GitHub PR/commit evidence is independently
-- validated by Direct and integration workers before any repository writes.
-- This RPC does not modify the immutable source binding, plan, or write scopes.
BEGIN;
CREATE OR REPLACE FUNCTION public.factory_retry_v2_governance_once(
 p_set uuid,p_run uuid,p_unit uuid,p_pr_number integer,p_issue_number integer,
 p_source_commit text,p_merge_commit text,p_reason text
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path TO ''
AS $body$
DECLARE
 s public.factory_change_sets%ROWTYPE;
 u public.factory_change_set_work_units%ROWTYPE;
 r public.factory_runs%ROWTYPE;
 t public.factory_tasks%ROWTYPE;
 j public.factory_journeys%ROWTYPE;
 c public.factory_project_execution_controls%ROWTYPE;
 p public.factory_projects%ROWTYPE;
 evidence jsonb;
BEGIN
 IF p_set IS NULL OR p_run IS NULL OR p_unit IS NULL
 OR p_source_commit IS NULL OR p_merge_commit IS NULL
 OR p_pr_number IS NULL OR p_pr_number<1 OR p_issue_number IS NULL OR p_issue_number<1
 OR p_source_commit !~ '^[0-9a-f]{40}$' OR p_merge_commit !~ '^[0-9a-f]{40}$'
 OR p_merge_commit=p_source_commit OR nullif(btrim(p_reason),'') IS NULL
 OR length(p_reason)>300
 THEN RAISE EXCEPTION 'invalid V2 governance retry identity' USING ERRCODE='PT409'; END IF;
 SELECT * INTO s FROM public.factory_change_sets WHERE id=p_set FOR UPDATE;
 IF s.id IS NULL OR s.status<>'blocked' OR s.journey_id IS NULL
 OR s.metadata#>>'{blocker,type}' IS DISTINCT FROM 'repository_governance'
 OR s.metadata#>>'{blocker,run_id}' IS DISTINCT FROM p_run::text
 OR s.metadata#>>'{blocker,work_unit_id}' IS DISTINCT FROM p_unit::text
 OR s.metadata#>>'{blocker,reason}' NOT LIKE '%CURRENT_TASK.md%'
 OR s.metadata#>>'{blocker,reason}' NOT LIKE '%issue #171%'
 OR s.metadata ? 'governance_amendment'
 OR s.attempt_count<>0 OR s.lease_owner IS NOT NULL OR s.lease_expires_at IS NOT NULL
 OR s.source_commit IS DISTINCT FROM p_source_commit
 OR s.candidate_commit IS DISTINCT FROM p_source_commit
 OR s.release_run_id IS NOT NULL
 OR s.current_wave<>1
 THEN RAISE EXCEPTION 'Change Set is not eligible for governance recovery' USING ERRCODE='PT409'; END IF;
 SELECT * INTO p FROM public.factory_projects WHERE id=s.project_id FOR SHARE;
 SELECT * INTO c FROM public.factory_project_execution_controls WHERE project_id=s.project_id FOR SHARE;
 SELECT * INTO j FROM public.factory_journeys
 WHERE id=s.journey_id AND project_id=s.project_id FOR SHARE;
 IF p.id IS NULL OR p.project_key<>'crm-infodive'
 OR p.repository<>'leandrosilveiradepaula/crm-infodive' OR p.is_active IS NOT TRUE
 OR c.project_id IS NULL OR c.state<>'running' OR c.generation<>16
 OR j.id IS NULL OR j.state<>'executing' OR j.execution_generation<>c.generation
 OR j.source_commit IS DISTINCT FROM p_source_commit
 OR j.binding->>'source_commit' IS DISTINCT FROM p_source_commit
 OR j.binding->>'source_ref' IS DISTINCT FROM 'main'
 OR j.binding->>'source_mode' IS DISTINCT FROM 'main_snapshot'
 OR j.binding->>'repository' IS DISTINCT FROM p.repository
 OR j.binding->>'journey_id' IS DISTINCT FROM j.id::text
 OR j.binding->>'request_id' IS DISTINCT FROM j.request_id::text
 OR j.binding->>'execution_generation' IS DISTINCT FROM c.generation::text
 OR j.request_snapshot->>'text' NOT LIKE '%issue #171%'
 OR p_issue_number<>171 OR p_pr_number<>208
 THEN RAISE EXCEPTION 'V2 journey epoch, scope or policy mismatch' USING ERRCODE='PT409'; END IF;
 IF (SELECT count(*) FROM public.factory_change_set_work_units WHERE change_set_id=s.id)<>1
 THEN RAISE EXCEPTION 'expected exactly one Work Unit' USING ERRCODE='PT409'; END IF;
 SELECT * INTO u FROM public.factory_change_set_work_units
 WHERE id=p_unit AND change_set_id=s.id FOR UPDATE;
 SELECT * INTO r FROM public.factory_runs WHERE id=p_run FOR UPDATE;
 SELECT * INTO t FROM public.factory_tasks WHERE id=u.task_id FOR UPDATE;
 IF u.id IS NULL OR u.status<>'blocked' OR u.wave<>1
 OR u.run_id IS DISTINCT FROM r.id
 OR u.base_commit IS DISTINCT FROM p_source_commit
 OR u.output_commit IS NOT NULL OR u.changed_files IS DISTINCT FROM '[]'::jsonb
 OR u.branch_name IS DISTINCT FROM 'factory/cs-c105550f/issue171-contracts-scalable-read'
 OR r.id IS NULL OR r.status<>'blocked' OR r.task_id IS DISTINCT FROM t.id
 OR r.source_commit IS DISTINCT FROM p_source_commit
 OR r.candidate_commit IS NOT NULL OR r.branch_name IS NOT NULL
 OR r.last_error IS DISTINCT FROM s.metadata#>>'{blocker,reason}'
 OR r.metadata->>'execution_generation' IS DISTINCT FROM c.generation::text
 OR r.attempt_count<>2 OR r.lease_owner IS NOT NULL OR r.lease_expires_at IS NOT NULL
 OR t.id IS NULL OR t.status<>'blocked' OR t.project_id IS DISTINCT FROM p.id
 OR t.journey_id IS DISTINCT FROM j.id OR t.parent_task_id IS DISTINCT FROM s.root_task_id
 OR NOT (t.scope_keys @> '["src/services/ContractService.ts"]'::jsonb)
 OR NOT (t.scope_keys @> '["src/services/ContractService.test.ts"]'::jsonb)
 OR EXISTS (
   SELECT 1 FROM public.factory_audit_events a
   WHERE a.run_id=p_run AND a.event_type='change_set.v2_governance_requeued'
 )
 THEN RAISE EXCEPTION 'Work Unit not eligible for one-time governance recovery' USING ERRCODE='PT409'; END IF;
 evidence:=jsonb_build_object(
   'version',1,'pr_number',p_pr_number,'issue_number',p_issue_number,
   'source_commit',p_source_commit,'merge_commit',p_merge_commit,
   'journey_id',j.id,'request_id',j.request_id,
   'change_set_id',s.id,'run_id',r.id,'work_unit_id',u.id);
 UPDATE public.factory_runs SET status='queued',last_error=NULL WHERE id=p_run;
 UPDATE public.factory_tasks SET status='queued_execution',updated_at=now() WHERE id=t.id;
 UPDATE public.factory_change_set_work_units SET status='queued',updated_at=now()
 WHERE id=u.id;
 UPDATE public.factory_change_sets SET status='building',updated_at=now(),
 metadata=(metadata-'blocker')||jsonb_build_object(
   'governance_amendment',evidence,
   'governance_recovery',jsonb_build_object('reason',p_reason,'at',now()))
 WHERE id=s.id;
 INSERT INTO public.factory_audit_events(
    project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 VALUES(p.id,t.id,r.id,'system','v2-governance-recovery',
   'change_set.v2_governance_requeued',
   jsonb_build_object('evidence',evidence,'reason',p_reason,'generation',c.generation));
 RETURN jsonb_build_object('change_set_id',s.id,'work_unit_id',u.id,
   'run_id',r.id,'status','building','source_commit',p_source_commit,
   'document_merge_commit',p_merge_commit,'generation',c.generation);
END;
$body$;
REVOKE ALL ON FUNCTION public.factory_retry_v2_governance_once(
 uuid,uuid,uuid,integer,integer,text,text,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.factory_retry_v2_governance_once(
 uuid,uuid,uuid,integer,integer,text,text,text) TO service_role;
COMMIT;
