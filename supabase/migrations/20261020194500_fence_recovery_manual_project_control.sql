-- Live-function preservation with operator-controlled recovery.
-- Captured against Supabase project fjplmxfcshhbmzgvyqlm on 2026-10-20.
-- Only the human-control assertions/filters/locks are added; preserve
-- security invoker, service-role-only grants and every existing output shape.
-- Expired-agent-slot release remains a cleanup path, never a new run claim.
BEGIN;
CREATE OR REPLACE FUNCTION public.factory_assert_project_running(p_project_id uuid)
 RETURNS void
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare v_state text;
begin
 select c.state into v_state
 from public.factory_project_execution_controls c
 join public.factory_projects p on p.id=c.project_id
 where c.project_id=p_project_id and c.generation>0 and p.is_active=true
 for share of c,p;
 if v_state is distinct from 'running' then
   raise exception 'project execution not authorized (%).',coalesce(v_state,'missing')
    using errcode='PT409';
 end if;
end;
$function$;

CREATE OR REPLACE FUNCTION public.factory_recover_expired_runs(p_max_attempts integer DEFAULT 3)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare
  rec record;
  v_requeued integer:=0;
  v_failed integer:=0;
  v_task_status text;
begin
  if p_max_attempts<1 then
    raise exception 'max attempts must be positive';
  end if;

  for rec in
    select r.id,r.task_id,r.execution_route,r.metadata,r.attempt_count,r.status,t.project_id
    from public.factory_runs r
    join public.factory_tasks t on t.id=r.task_id
    join public.factory_projects p on p.id=t.project_id and p.is_active=true
    join public.factory_project_execution_controls c on c.project_id=p.id and c.state='running' and c.generation>0
    where r.status in ('running','implementing','preparing_codex_manual')
      and r.lease_expires_at is not null
      and r.lease_expires_at<now()
    for update of r skip locked
  loop
    -- If Pause/Stop committed while the candidate row was locked,
    -- skip this project. Otherwise retain a shared control lock until
    -- the whole recovery transaction commits.
    perform 1 from public.factory_project_execution_controls c
    join public.factory_projects p on p.id=c.project_id
    where c.project_id=rec.project_id and c.state='running'
      and c.generation>0 and p.is_active=true for share of c,p;
    if not found then continue; end if;
    if rec.attempt_count>=p_max_attempts then
      update public.factory_runs
      set status='failed',finished_at=now(),lease_owner=null,lease_expires_at=null,
          last_error='lease expired after maximum attempts'
      where id=rec.id;
      update public.factory_tasks
      set status='failed',updated_at=now()
      where id=rec.task_id;
      v_failed:=v_failed+1;
    else
      v_task_status:=case when rec.metadata ? 'stages' then 'queued' else 'queued_execution' end;
      update public.factory_runs
      set status='queued',lease_owner=null,lease_expires_at=null,
          last_error='worker lease expired; requeued'
      where id=rec.id;
      update public.factory_tasks
      set status=v_task_status,updated_at=now()
      where id=rec.task_id;
      v_requeued:=v_requeued+1;
    end if;

    insert into public.factory_audit_events(
      project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
    )
    values(
      rec.project_id,rec.task_id,rec.id,'system','lease-recovery',
      'run.lease_recovered',
      jsonb_build_object(
        'attempt_count',rec.attempt_count,
        'max_attempts',p_max_attempts,
        'terminal',rec.attempt_count>=p_max_attempts,
        'recovered_status',rec.status
      )
    );
  end loop;

  return jsonb_build_object('requeued',v_requeued,'failed',v_failed);
end;
$function$;

CREATE OR REPLACE FUNCTION public.factory_recover_change_sets(p_max_attempts integer DEFAULT 3)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare
  v_requeued integer:=0;
  v_stale_direct_requeued integer:=0;
  v_blocked integer:=0;
  v_integrators integer:=0;
  v_blocked_integrations integer:=0;
  v_row record;
begin
  if p_max_attempts<1 or p_max_attempts>10 then raise exception 'invalid max attempts'; end if;
  perform 1 from public.factory_project_execution_controls c
  join public.factory_projects p on p.id=c.project_id
  where c.state='running' and c.generation>0 and p.is_active=true
  order by c.project_id for share of c,p;

  for v_row in
    select
      u.id as work_unit_id,
      u.task_id,
      u.change_set_id,
      r.id as run_id,
      t.project_id
    from public.factory_change_set_work_units u
    join public.factory_runs r on r.id=u.run_id
    join public.factory_tasks t on t.id=u.task_id
    join public.factory_projects p on p.id=t.project_id and p.is_active=true
    join public.factory_project_execution_controls c on c.project_id=p.id and c.state='running' and c.generation>0
    where u.status='running'
      and r.status='implementing'
      and r.lease_expires_at<=now()
      and r.attempt_count<p_max_attempts
    order by r.lease_expires_at,u.id
    for update of u
  loop
    update public.factory_runs
    set status='queued',
        lease_owner=null,
        lease_expires_at=null,
        metadata=metadata||jsonb_build_object(
          'execution_recovered',true,
          'execution_recovered_at',now(),
          'execution_recovery_reason','expired_implementing_lease'
        )
    where id=v_row.run_id
      and status='implementing';

    update public.factory_tasks
    set status='queued_execution',updated_at=now()
    where id=v_row.task_id
      and status='implementing';

    update public.factory_change_set_work_units
    set status='queued',updated_at=now()
    where id=v_row.work_unit_id
      and status='running';

    insert into public.factory_audit_events(
      project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
    )
    values(
      v_row.project_id,v_row.task_id,v_row.run_id,
      'system','change-set-recovery','execution.direct.requeued_after_expired_lease',
      jsonb_build_object(
        'change_set_id',v_row.change_set_id,
        'work_unit_id',v_row.work_unit_id,
        'reason','expired_implementing_lease'
      )
    );
    v_stale_direct_requeued:=v_stale_direct_requeued+1;
  end loop;

  update public.factory_change_set_work_units u
  set status='queued',updated_at=now()
  from public.factory_runs r
  where u.run_id=r.id and u.status='running' and r.status='queued'
    and exists(select 1 from public.factory_tasks t join public.factory_projects p on p.id=t.project_id join public.factory_project_execution_controls c on c.project_id=p.id where t.id=u.task_id and p.is_active=true and c.state='running' and c.generation>0 for share of c,p);
  get diagnostics v_requeued=row_count;

  update public.factory_change_set_work_units u
  set status='failed',updated_at=now()
  from public.factory_runs r
  where u.run_id=r.id and u.status in ('running','queued') and r.status='failed'
    and exists(select 1 from public.factory_tasks t join public.factory_projects p on p.id=t.project_id join public.factory_project_execution_controls c on c.project_id=p.id where t.id=u.task_id and p.is_active=true and c.state='running' and c.generation>0 for share of c,p);

  update public.factory_change_sets s
  set status='blocked',lease_owner=null,lease_expires_at=null,updated_at=now(),
      metadata=metadata||jsonb_build_object('blocker','builder_retry_exhausted')
  where s.status in ('planned','building','integrating')
    and exists(
      select 1 from public.factory_change_set_work_units u
      where u.change_set_id=s.id and u.status in ('failed','blocked')
    ) and exists(select 1 from public.factory_projects p join public.factory_project_execution_controls c on c.project_id=p.id where p.id=s.project_id and p.is_active=true and c.state='running' and c.generation>0 for share of c,p);
  get diagnostics v_blocked=row_count;

  update public.factory_change_sets s
  set status='building',lease_owner=null,lease_expires_at=null,updated_at=now()
  where s.status='integrating' and s.lease_expires_at<=now() and s.attempt_count<p_max_attempts
    and exists(select 1 from public.factory_projects p join public.factory_project_execution_controls c on c.project_id=p.id where p.id=s.project_id and p.is_active=true and c.state='running' and c.generation>0 for share of c,p);
  get diagnostics v_integrators=row_count;

  update public.factory_change_sets s
  set status='blocked',lease_owner=null,lease_expires_at=null,updated_at=now(),
      metadata=metadata||jsonb_build_object('blocker','integration_retry_exhausted')
  where s.status='integrating' and s.lease_expires_at<=now() and s.attempt_count>=p_max_attempts
    and exists(select 1 from public.factory_projects p join public.factory_project_execution_controls c on c.project_id=p.id where p.id=s.project_id and p.is_active=true and c.state='running' and c.generation>0 for share of c,p);
  get diagnostics v_blocked_integrations=row_count;
  v_blocked:=v_blocked+v_blocked_integrations;

  return jsonb_build_object(
    'work_units_requeued',v_requeued,
    'stale_direct_requeued',v_stale_direct_requeued,
    'integrations_requeued',v_integrators,
    'blocked',v_blocked
  );
end;
$function$;

CREATE OR REPLACE FUNCTION public.factory_recover_specialist_lanes(p_max_attempts integer DEFAULT 3)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare v_requeued integer:=0;v_blocked integer:=0;
begin
 if p_max_attempts<1 or p_max_attempts>10 then raise exception 'invalid max attempts'; end if;
  perform 1 from public.factory_project_execution_controls c
  join public.factory_projects p on p.id=c.project_id
  where c.state='running' and c.generation>0 and p.is_active=true
  order by c.project_id for share of c,p;

 update public.factory_specialist_lane_jobs
 set status='queued',lease_owner=null,lease_expires_at=null,updated_at=now()
 where status='claimed' and lease_expires_at<=now() and attempt_count<p_max_attempts
   and exists(select 1 from public.factory_projects p join public.factory_project_execution_controls c on c.project_id=p.id where p.id=public.factory_specialist_lane_jobs.project_id and p.is_active=true and c.state='running' and c.generation>0 for share of c,p);
 get diagnostics v_requeued=row_count;

 update public.factory_specialist_lane_jobs
 set status='blocked',lease_owner=null,lease_expires_at=null,completed_at=now(),updated_at=now(),
     findings=case when findings='[]'::jsonb then jsonb_build_array(jsonb_build_object(
       'code','specialist_retry_exhausted','severity','critical','message','specialist lane exhausted retry attempts'
     )) else findings end
 where status='claimed' and lease_expires_at<=now() and attempt_count>=p_max_attempts
   and exists(select 1 from public.factory_projects p join public.factory_project_execution_controls c on c.project_id=p.id where p.id=public.factory_specialist_lane_jobs.project_id and p.is_active=true and c.state='running' and c.generation>0 for share of c,p);
 get diagnostics v_blocked=row_count;

 update public.factory_runs r
 set status='specialist_review_failed'
 where exists(
   select 1 from public.factory_specialist_lane_jobs j
   where j.run_id=r.id and j.required and j.status='blocked'
 ) and exists(select 1 from public.factory_tasks t where t.id=r.task_id and exists(select 1 from public.factory_projects p join public.factory_project_execution_controls c on c.project_id=p.id where p.id=t.project_id and p.is_active=true and c.state='running' and c.generation>0 for share of c,p));

 return jsonb_build_object('requeued',v_requeued,'blocked',v_blocked);
end;
$function$;

CREATE OR REPLACE FUNCTION public.factory_resume_resolved_decisions()
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare
  v_run record;
  v_plan jsonb;
  v_external_key text;
  v_title text;
  v_description text;
  v_complexity text;
  v_risk jsonb;
  v_acceptance jsonb;
  v_task_id uuid;
  v_was_created boolean;
  v_created integer := 0;
  v_existing integer := 0;
  v_blocked integer := 0;
begin
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtext('factory_resume_resolved_decisions'));

  for v_run in
    select
      r.id as run_id,
      r.task_id as source_task_id,
      r.metadata,
      t.project_id
    from public.factory_runs r
    join public.factory_tasks t on t.id = r.task_id
    join public.factory_projects p on p.id=t.project_id and p.is_active=true
    join public.factory_project_execution_controls c on c.project_id=p.id and c.state='running' and c.generation>0
    where r.status = 'completed'
      and coalesce((r.metadata->>'decision_only')::boolean,false)
      and r.metadata->>'decision_outcome' = 'approved'
      and jsonb_typeof(r.metadata->'resume_plan') = 'object'
      and coalesce(r.metadata->>'resume_plan_status','') not in ('materialized','blocked_invalid')
    order by r.finished_at nulls last, r.created_at
    for update of r
  loop
    perform 1 from public.factory_project_execution_controls c
    join public.factory_projects p on p.id=c.project_id
    where c.project_id=v_run.project_id and c.state='running'
      and c.generation>0 and p.is_active=true for share of c,p;
    if not found then continue; end if;
    v_plan := v_run.metadata->'resume_plan';
    v_external_key := nullif(btrim(v_plan->>'external_key'),'');
    v_title := nullif(btrim(v_plan->>'title'),'');
    v_description := coalesce(v_plan->>'description','');
    v_complexity := coalesce(nullif(btrim(v_plan->>'complexity'),''),'medium');
    v_risk := coalesce(v_plan->'risk','{}'::jsonb);
    v_acceptance := coalesce(v_plan->'acceptance_criteria','[]'::jsonb);
    v_was_created := false;

    if v_external_key is null
       or v_title is null
       or v_complexity not in ('low','medium','high')
       or jsonb_typeof(v_risk) <> 'object'
       or jsonb_typeof(v_acceptance) <> 'array'
       or jsonb_typeof(coalesce(v_plan->'depends_on','[]'::jsonb)) <> 'array'
       or jsonb_typeof(coalesce(v_plan->'required_capabilities','[]'::jsonb)) <> 'array'
       or jsonb_typeof(coalesce(v_plan->'scope_keys','[]'::jsonb)) <> 'array'
    then
      update public.factory_runs
      set metadata = metadata || jsonb_build_object(
        'resume_plan_status','blocked_invalid',
        'resume_plan_error','invalid or incomplete resume_plan'
      )
      where id = v_run.run_id;

      insert into public.factory_audit_events(
        project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
      )
      values(
        v_run.project_id,v_run.source_task_id,v_run.run_id,
        'system','decision-resume-recovery','decision.resume.blocked',
        jsonb_build_object('reason','invalid_resume_plan')
      );
      v_blocked := v_blocked + 1;
      continue;
    end if;

    select id into v_task_id
    from public.factory_tasks
    where project_id = v_run.project_id
      and external_key = v_external_key
    order by created_at
    limit 1;

    if v_task_id is null then
      insert into public.factory_tasks(
        project_id,parent_task_id,external_key,title,description,status,complexity,
        risk,acceptance_criteria,depends_on,required_capabilities,scope_keys
      )
      values(
        v_run.project_id,
        v_run.source_task_id,
        v_external_key,
        v_title,
        v_description,
        'queued',
        v_complexity,
        v_risk,
        v_acceptance,
        coalesce(v_plan->'depends_on','[]'::jsonb),
        coalesce(v_plan->'required_capabilities','[]'::jsonb),
        coalesce(v_plan->'scope_keys','[]'::jsonb)
      )
      returning id into v_task_id;
      v_was_created := true;
      v_created := v_created + 1;
    else
      v_existing := v_existing + 1;
    end if;

    update public.factory_runs
    set metadata = metadata || jsonb_build_object(
      'resume_plan_status','materialized',
      'resume_task_id',v_task_id
    )
    where id = v_run.run_id;

    insert into public.factory_audit_events(
      project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
    )
    values(
      v_run.project_id,v_run.source_task_id,v_run.run_id,
      'system','decision-resume-recovery','decision.resume.materialized',
      jsonb_build_object(
        'resume_task_id',v_task_id,
        'external_key',v_external_key,
        'created',v_was_created
      )
    );
  end loop;

  return jsonb_build_object(
    'created',v_created,
    'existing',v_existing,
    'blocked',v_blocked
  );
end;
$function$;

CREATE OR REPLACE FUNCTION public.factory_retry_failed_run(p_source_run_id uuid, p_reason text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare
  v_source public.factory_runs%rowtype;
  v_task public.factory_tasks%rowtype;
  v_project_id uuid;
  v_new_run_id uuid;
  v_existing_retry_id uuid;
  v_task_status text;
  v_reason text;
  v_metadata jsonb;
begin
  v_reason:=nullif(btrim(p_reason),'');
  if v_reason is null then raise exception 'retry reason is required'; end if;
  if length(v_reason)>1000 then raise exception 'retry reason is too long'; end if;

  select * into v_source from public.factory_runs where id=p_source_run_id for update;
  if not found then raise exception 'source run not found'; end if;
  if v_source.status<>'failed' then raise exception 'source run is not failed'; end if;

  select id into v_existing_retry_id
  from public.factory_runs
  where task_id=v_source.task_id
    and metadata->>'retry_of'=p_source_run_id::text
  order by created_at desc limit 1;
  if v_existing_retry_id is not null then raise exception 'retry already exists for source run'; end if;

  select * into v_task from public.factory_tasks where id=v_source.task_id for update;
  if not found then raise exception 'source task not found'; end if;
  v_project_id:=v_task.project_id;
  perform public.factory_assert_project_running(v_project_id);
  v_task_status:=case when v_source.execution_route is null or v_source.metadata ? 'stages' then 'queued' else 'queued_execution' end;

  v_metadata:=(v_source.metadata
    - 'worker_id' - 'claimed_at' - 'execution_worker_id' - 'execution_claimed_at' - 'error'
  ) || jsonb_build_object(
    'retry_of',p_source_run_id::text,
    'retry_reason',v_reason,
    'retry_source_commit',v_source.source_commit,
    'retry_queued_at',now()
  );

  insert into public.factory_runs(
    task_id,status,execution_route,source_commit,candidate_commit,branch_name,
    metadata,lease_owner,lease_expires_at,attempt_count,last_error
  ) values(
    v_source.task_id,'queued',v_source.execution_route,v_source.source_commit,null,null,
    v_metadata,null,null,0,null
  ) returning id into v_new_run_id;

  update public.factory_tasks set status=v_task_status,updated_at=now() where id=v_source.task_id;

  insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
  values(
    v_project_id,v_source.task_id,v_new_run_id,'system','runtime-retry','run.retry_queued',
    jsonb_build_object(
      'source_run_id',p_source_run_id,
      'reason',v_reason,
      'source_commit',v_source.source_commit,
      'execution_route',v_source.execution_route
    )
  );

  return jsonb_build_object(
    'source_run_id',p_source_run_id,
    'run_id',v_new_run_id,
    'task_id',v_source.task_id,
    'status','queued',
    'task_status',v_task_status,
    'execution_route',v_source.execution_route,
    'source_commit',v_source.source_commit
  );
end;
$function$;
COMMIT;
