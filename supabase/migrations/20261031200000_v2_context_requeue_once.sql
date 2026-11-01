BEGIN;
CREATE OR REPLACE FUNCTION public.factory_retry_v2_context_once(p_set uuid,p_run uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=''
AS $body$
DECLARE s public.factory_change_sets%ROWTYPE;
u public.factory_change_set_work_units%ROWTYPE;
r public.factory_runs%ROWTYPE;
t public.factory_tasks%ROWTYPE;
j public.factory_journeys%ROWTYPE;
c public.factory_project_execution_controls%ROWTYPE;
BEGIN
 SELECT * INTO s FROM public.factory_change_sets WHERE id=p_set FOR UPDATE;
 IF s.id IS NULL OR s.status<>'blocked' OR s.journey_id IS NULL
 OR s.metadata#>>'{blocker,type}' IS DISTINCT FROM 'implementation_preflight_error'
 OR s.metadata#>>'{blocker,reason}' IS DISTINCT FROM 'PermissionError: journey context cross-project'
 OR s.metadata#>>'{blocker,run_id}' IS DISTINCT FROM p_run::text
 OR s.attempt_count>1 OR s.lease_owner IS NOT NULL OR s.lease_expires_at IS NOT NULL
 OR s.candidate_commit IS NOT NULL OR s.release_run_id IS NOT NULL
 THEN RAISE EXCEPTION 'ineligible change set' USING ERRCODE='PT409'; END IF;
 SELECT * INTO c FROM public.factory_project_execution_controls WHERE project_id=s.project_id FOR SHARE;
 SELECT * INTO j FROM public.factory_journeys WHERE id=s.journey_id AND project_id=s.project_id FOR SHARE;
 IF c.project_id IS NULL OR c.state<>'running' OR j.id IS NULL
 OR j.state NOT IN ('source_bound','executing')
 OR j.execution_generation IS DISTINCT FROM c.generation
 OR j.binding->>'journey_id' IS DISTINCT FROM j.id::text
 OR j.binding->>'project_id' IS DISTINCT FROM s.project_id::text
 OR j.binding->>'source_commit' IS DISTINCT FROM j.source_commit
 THEN RAISE EXCEPTION 'V2 epoch or binding mismatch' USING ERRCODE='PT409'; END IF;
 IF (SELECT count(*) FROM public.factory_change_set_work_units WHERE change_set_id=p_set)<>1
 THEN RAISE EXCEPTION 'multiple work units' USING ERRCODE='PT409'; END IF;
 SELECT * INTO u FROM public.factory_change_set_work_units WHERE change_set_id=p_set FOR UPDATE;
 SELECT * INTO r FROM public.factory_runs WHERE id=p_run FOR UPDATE;
 SELECT * INTO t FROM public.factory_tasks WHERE id=u.task_id FOR UPDATE;
 IF u.id IS NULL OR u.status<>'blocked' OR u.run_id IS DISTINCT FROM p_run
 OR s.metadata#>>'{blocker,work_unit_id}' IS DISTINCT FROM u.id::text
 OR u.base_commit IS NOT NULL OR u.branch_name IS NOT NULL OR u.output_commit IS NOT NULL
 OR u.changed_files IS DISTINCT FROM '[]'::jsonb
 OR r.id IS NULL OR r.status<>'blocked' OR r.task_id IS DISTINCT FROM t.id
 OR r.last_error IS DISTINCT FROM 'PermissionError: journey context cross-project'
 OR r.metadata->>'execution_generation' IS DISTINCT FROM c.generation::text
 OR r.source_commit IS DISTINCT FROM j.source_commit
 OR r.lease_owner IS NOT NULL OR r.lease_expires_at IS NOT NULL OR r.attempt_count>2
 OR r.candidate_commit IS NOT NULL OR r.branch_name IS NOT NULL
 OR t.status<>'blocked' OR t.project_id IS DISTINCT FROM s.project_id
 OR t.journey_id IS DISTINCT FROM j.id OR t.parent_task_id IS DISTINCT FROM s.root_task_id
 OR EXISTS(SELECT 1 FROM public.factory_audit_events a WHERE a.run_id=p_run AND a.event_type='change_set.v2_context_requeued')
 THEN RAISE EXCEPTION 'ineligible run or work unit' USING ERRCODE='PT409'; END IF;
 UPDATE public.factory_runs SET status='queued',last_error=NULL WHERE id=p_run;
 UPDATE public.factory_tasks SET status='queued_execution',updated_at=now() WHERE id=t.id;
 UPDATE public.factory_change_set_work_units SET status='queued',updated_at=now() WHERE id=u.id;
 UPDATE public.factory_change_sets SET status='building',updated_at=now(),
 metadata=(metadata-'blocker')||jsonb_build_object('v2_context_recovery_at',now()) WHERE id=p_set;
 INSERT INTO public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 VALUES(s.project_id,t.id,r.id,'system','v2-context-recovery','change_set.v2_context_requeued',
 jsonb_build_object('change_set_id',s.id,'work_unit_id',u.id,'generation',c.generation));
 RETURN jsonb_build_object('run_id',r.id,'work_unit_id',u.id,'status','building');
END;
$body$;
REVOKE ALL ON FUNCTION public.factory_retry_v2_context_once(uuid,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.factory_retry_v2_context_once(uuid,uuid) TO service_role;
COMMIT;
