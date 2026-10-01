create or replace function public.factory_resume_resolved_decisions()
returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
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
    where r.status = 'completed'
      and coalesce((r.metadata->>'decision_only')::boolean,false)
      and r.metadata->>'decision_outcome' = 'approved'
      and jsonb_typeof(r.metadata->'resume_plan') = 'object'
      and coalesce(r.metadata->>'resume_plan_status','') not in ('materialized','blocked_invalid')
    order by r.finished_at nulls last, r.created_at
    for update of r
  loop
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
$$;

revoke all on function public.factory_resume_resolved_decisions() from public,anon,authenticated;
grant execute on function public.factory_resume_resolved_decisions() to service_role;
