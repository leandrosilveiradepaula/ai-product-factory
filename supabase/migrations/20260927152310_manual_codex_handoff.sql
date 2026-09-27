-- Durable manual Codex handoff while managed Codex automation is unavailable.
-- No model/provider credential is stored in the Control Plane.

create or replace function public.factory_claim_next_manual_codex_handoff(p_worker_id text)
returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
  v_run public.factory_runs%rowtype;
  v_task public.factory_tasks%rowtype;
  v_project public.factory_projects%rowtype;
  v_issue_number integer;
begin
  if nullif(btrim(p_worker_id),'') is null then
    raise exception 'worker_id is required';
  end if;

  select r.*
  into v_run
  from public.factory_runs r
  join public.factory_tasks t on t.id=r.task_id
  where r.status='queued'
    and r.execution_route='codex'
    and t.status='queued_execution'
  order by r.created_at
  for update of r skip locked
  limit 1;

  if v_run.id is null then
    return null;
  end if;

  select * into v_task
  from public.factory_tasks
  where id=v_run.task_id
  for update;

  select * into v_project
  from public.factory_projects
  where id=v_task.project_id;

  v_issue_number:=case
    when nullif(v_run.metadata->'github_issue'->>'number','') is null then null
    else (v_run.metadata->'github_issue'->>'number')::integer
  end;

  update public.factory_runs
  set status='preparing_codex_manual',
      started_at=coalesce(started_at,now()),
      lease_owner=p_worker_id,
      lease_expires_at=now()+interval '10 minutes',
      attempt_count=attempt_count+1,
      last_error=null,
      metadata=metadata||jsonb_build_object(
        'manual_codex',true,
        'manual_codex_handoff_worker',p_worker_id,
        'manual_codex_handoff_claimed_at',now()
      )
  where id=v_run.id
    and status='queued'
    and execution_route='codex';

  if not found then
    return null;
  end if;

  update public.factory_tasks
  set status='preparing_codex_manual',
      updated_at=now()
  where id=v_task.id;

  insert into public.factory_audit_events(
    project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
  )
  values(
    v_project.id,v_task.id,v_run.id,'system',p_worker_id,
    'execution.codex.manual.claimed',
    jsonb_build_object(
      'codex_level',greatest(1,coalesce((v_run.metadata->>'codex_level')::integer,1)),
      'lease_minutes',10
    )
  );

  return jsonb_build_object(
    'run_id',v_run.id,
    'task_id',v_task.id,
    'project_key',v_project.project_key,
    'repository',v_project.repository,
    'issue_number',v_issue_number,
    'title',v_task.title,
    'description',v_task.description,
    'codex_level',greatest(1,coalesce((v_run.metadata->>'codex_level')::integer,1))
  );
end;
$$;

revoke all on function public.factory_claim_next_manual_codex_handoff(text)
from public,anon,authenticated;
grant execute on function public.factory_claim_next_manual_codex_handoff(text)
to service_role;


create or replace function public.factory_mark_manual_codex_waiting(p_run_id uuid)
returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
  v_task_id uuid;
  v_project_id uuid;
  v_issue_number integer;
begin
  select r.task_id,t.project_id,
         case
           when nullif(r.metadata->'github_issue'->>'number','') is null then null
           else (r.metadata->'github_issue'->>'number')::integer
         end
  into v_task_id,v_project_id,v_issue_number
  from public.factory_runs r
  join public.factory_tasks t on t.id=r.task_id
  where r.id=p_run_id
    and r.execution_route='codex'
    and r.status='preparing_codex_manual'
  for update of r;

  if v_task_id is null then
    raise exception 'manual Codex handoff run not found';
  end if;
  if v_issue_number is null or v_issue_number < 1 then
    raise exception 'manual Codex handoff requires a bound GitHub issue';
  end if;

  update public.factory_runs
  set status='awaiting_codex_manual',
      lease_owner=null,
      lease_expires_at=null,
      metadata=metadata||jsonb_build_object(
        'manual_codex_handoff_ready_at',now()
      )
  where id=p_run_id;

  update public.factory_tasks
  set status='awaiting_codex_manual',
      updated_at=now()
  where id=v_task_id;

  insert into public.factory_audit_events(
    project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
  )
  values(
    v_project_id,v_task_id,p_run_id,'system','manual-codex-handoff',
    'execution.codex.manual.awaiting',
    jsonb_build_object('issue_number',v_issue_number)
  );

  return jsonb_build_object(
    'run_id',p_run_id,
    'status','awaiting_codex_manual',
    'issue_number',v_issue_number
  );
end;
$$;

revoke all on function public.factory_mark_manual_codex_waiting(uuid)
from public,anon,authenticated;
grant execute on function public.factory_mark_manual_codex_waiting(uuid)
to service_role;


create or replace function public.factory_adopt_manual_codex_pr(
  p_run_id uuid,
  p_pr_number integer,
  p_pr_url text,
  p_head_sha text,
  p_head_ref text
)
returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
  v_task_id uuid;
  v_project_id uuid;
begin
  if p_pr_number is null or p_pr_number < 1 then
    raise exception 'invalid PR number';
  end if;
  if nullif(btrim(p_head_sha),'') is null then
    raise exception 'head SHA is required';
  end if;
  if nullif(btrim(p_head_ref),'') is null then
    raise exception 'head ref is required';
  end if;

  select r.task_id,t.project_id
  into v_task_id,v_project_id
  from public.factory_runs r
  join public.factory_tasks t on t.id=r.task_id
  where r.id=p_run_id
    and r.execution_route='codex'
    and r.status='awaiting_codex_manual'
  for update of r;

  if v_task_id is null then
    raise exception 'awaiting manual Codex run not found';
  end if;

  update public.factory_runs
  set status='ci_pending',
      candidate_commit=p_head_sha,
      branch_name=p_head_ref,
      lease_owner=null,
      lease_expires_at=null,
      metadata=metadata||jsonb_build_object(
        'manual_codex_pr',
        jsonb_build_object(
          'number',p_pr_number,
          'url',p_pr_url,
          'head_sha',p_head_sha,
          'head_ref',p_head_ref
        ),
        'manual_codex_pr_adopted_at',now()
      )
  where id=p_run_id;

  update public.factory_tasks
  set status='ci_pending',
      updated_at=now()
  where id=v_task_id;

  insert into public.factory_tool_usage(
    run_id,tool_family,operation,usage_units,estimated_cost,metadata
  )
  values(
    p_run_id,'github','create_pr',1,0,
    jsonb_build_object(
      'pr',p_pr_number,
      'head_sha',p_head_sha,
      'url',p_pr_url,
      'source','manual_codex'
    )
  );

  insert into public.factory_audit_events(
    project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
  )
  values(
    v_project_id,v_task_id,p_run_id,'system','manual-codex-followup',
    'execution.codex.manual.pr_adopted',
    jsonb_build_object(
      'pr_number',p_pr_number,
      'head_sha',p_head_sha,
      'head_ref',p_head_ref
    )
  );

  return jsonb_build_object(
    'run_id',p_run_id,
    'status','ci_pending',
    'pr_number',p_pr_number,
    'candidate_commit',p_head_sha,
    'branch',p_head_ref
  );
end;
$$;

revoke all on function public.factory_adopt_manual_codex_pr(uuid,integer,text,text,text)
from public,anon,authenticated;
grant execute on function public.factory_adopt_manual_codex_pr(uuid,integer,text,text,text)
to service_role;


create or replace function public.factory_recover_expired_runs(p_max_attempts integer default 3)
returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
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
    where r.status in ('running','implementing','preparing_codex_manual')
      and r.lease_expires_at is not null
      and r.lease_expires_at<now()
    for update of r skip locked
  loop
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
$$;

revoke all on function public.factory_recover_expired_runs(integer)
from public,anon,authenticated;
grant execute on function public.factory_recover_expired_runs(integer)
to service_role;
