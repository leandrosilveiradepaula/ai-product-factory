create or replace function public.factory_claim_next_run(p_worker_id text)
returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
  v_run public.factory_runs%rowtype;
  v_task public.factory_tasks%rowtype;
  v_project public.factory_projects%rowtype;
  v_spec jsonb;
  v_snapshot jsonb;
begin
  if nullif(btrim(p_worker_id),'') is null then raise exception 'worker_id is required'; end if;
  select r.* into v_run
  from public.factory_runs r
  join public.factory_tasks t on t.id=r.task_id
  where r.status in ('created','queued') and t.status='queued'
  order by r.created_at
  for update of r skip locked
  limit 1;
  if v_run.id is null then return null; end if;
  select * into v_task from public.factory_tasks where id=v_run.task_id for update;
  select * into v_project from public.factory_projects where id=v_task.project_id;
  select ps.spec into v_spec from public.factory_product_specs ps where ps.project_id=v_project.id order by ps.version desc limit 1;
  select jsonb_build_object(
    'id',s.id,'observed_stage',s.observed_stage,'summary',s.summary,'evidence',s.evidence,
    'gaps',s.gaps,'constraints',s.constraints,'source_status',s.source_status,'created_at',s.created_at
  ) into v_snapshot
  from public.factory_project_state_snapshots s
  where s.project_id=v_project.id
  order by s.created_at desc
  limit 1;
  update public.factory_runs
  set status='running',started_at=coalesce(started_at,now()),lease_owner=p_worker_id,
      lease_expires_at=now()+interval '15 minutes',attempt_count=attempt_count+1,last_error=null,
      metadata=metadata||jsonb_build_object('worker_id',p_worker_id,'claimed_at',now())
  where id=v_run.id;
  update public.factory_tasks set status='running',updated_at=now() where id=v_task.id;
  insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
  values(v_project.id,v_task.id,v_run.id,'system',p_worker_id,'run.claimed',jsonb_build_object('lease_minutes',15));
  return jsonb_build_object(
    'run_id',v_run.id,'task_id',v_task.id,'project_id',v_project.id,'project_key',v_project.project_key,
    'stages',coalesce(v_run.metadata->'stages','[]'::jsonb),
    'context',jsonb_build_object(
      'task',v_task.description,'manifest',v_project.manifest,'intake_spec',coalesce(v_spec,'{}'::jsonb),'state_snapshot',v_snapshot
    )
  );
end;
$$;
revoke all on function public.factory_claim_next_run(text) from public,anon,authenticated;
grant execute on function public.factory_claim_next_run(text) to service_role;

create or replace function public.factory_persist_product_stage(p_run_id uuid,p_stage text,p_output jsonb)
returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
  v_task_id uuid;
  v_project_id uuid;
  v_version integer;
  v_created_tasks integer := 0;
  v_item jsonb;
  v_external_key text;
  v_snapshot_id uuid;
begin
  if p_stage not in ('discovery','specification','reconciliation','gap_analysis','planning') then
    raise exception 'unsupported product stage';
  end if;
  select r.task_id,t.project_id into v_task_id,v_project_id
  from public.factory_runs r join public.factory_tasks t on t.id=r.task_id
  where r.id=p_run_id;
  if v_project_id is null then raise exception 'run not found'; end if;

  if p_stage='discovery' then
    update public.factory_product_specs
      set spec=jsonb_set(spec,'{discovery}',coalesce(p_output,'{}'::jsonb),true)
      where project_id=v_project_id and version=(select max(version) from public.factory_product_specs where project_id=v_project_id);
    update public.factory_projects set lifecycle_stage='specification',updated_at=now() where id=v_project_id;
  elsif p_stage='specification' then
    select coalesce(max(version),0)+1 into v_version from public.factory_product_specs where project_id=v_project_id;
    insert into public.factory_product_specs(project_id,version,status,spec)
      values(v_project_id,v_version,'candidate',coalesce(p_output,'{}'::jsonb));
    update public.factory_projects set lifecycle_stage='planning',updated_at=now() where id=v_project_id;
  elsif p_stage='reconciliation' then
    if btrim(coalesce(p_output->>'summary',''))='' then raise exception 'reconciliation summary is required'; end if;
    insert into public.factory_project_state_snapshots(project_id,run_id,observed_stage,summary,evidence,gaps,constraints,source_status)
    values(
      v_project_id,p_run_id,nullif(btrim(p_output->>'observed_stage'),''),
      btrim(p_output->>'summary'),coalesce(p_output->'evidence','[]'::jsonb),
      coalesce(p_output->'gaps','[]'::jsonb),coalesce(p_output->'constraints','[]'::jsonb),
      coalesce(p_output->'source_status','{}'::jsonb)
    ) returning id into v_snapshot_id;
  elsif p_stage='gap_analysis' then
    update public.factory_projects
      set lifecycle_stage='planning',manifest=manifest||jsonb_build_object('gap_analysis',coalesce(p_output,'{}'::jsonb)),updated_at=now()
      where id=v_project_id;
  else
    update public.factory_projects
      set lifecycle_stage='implementation',manifest=manifest||jsonb_build_object('engineering_plan',coalesce(p_output,'{}'::jsonb)),updated_at=now()
      where id=v_project_id;
    for v_item in select value from jsonb_array_elements(coalesce(p_output->'tasks','[]'::jsonb))
    loop
      v_external_key:='plan-'||substr(md5(coalesce(v_item->>'title',v_item::text)),1,16);
      if not exists(select 1 from public.factory_tasks where project_id=v_project_id and external_key=v_external_key) then
        insert into public.factory_tasks(project_id,parent_task_id,external_key,title,description,status,complexity,risk,acceptance_criteria,depends_on)
        values(
          v_project_id,v_task_id,v_external_key,coalesce(nullif(v_item->>'title',''),'Planned task'),v_item->>'description','queued',
          case when v_item->>'complexity' in ('low','medium','high','very_high') then v_item->>'complexity' else 'medium' end,
          coalesce(v_item->'risk','{}'::jsonb),coalesce(v_item->'acceptance_criteria','[]'::jsonb),coalesce(v_item->'depends_on','[]'::jsonb)
        );
        v_created_tasks:=v_created_tasks+1;
      end if;
    end loop;
  end if;

  insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
  values(v_project_id,v_task_id,p_run_id,'system','runtime-worker','product.stage.persisted',
    jsonb_build_object('stage',p_stage,'created_tasks',v_created_tasks,'snapshot_id',v_snapshot_id));

  return jsonb_build_object('project_id',v_project_id,'stage',p_stage,'created_tasks',v_created_tasks,'snapshot_id',v_snapshot_id);
end;
$$;
revoke all on function public.factory_persist_product_stage(uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.factory_persist_product_stage(uuid,text,jsonb) to service_role;
