create or replace function public.factory_finalize_console_human_release(
  p_run_id uuid,
  p_candidate_commit text,
  p_merge_sha text
)
returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
  v_run public.factory_runs%rowtype;
  v_task public.factory_tasks%rowtype;
  v_report public.factory_release_reports%rowtype;
  v_report_merge_sha text;
  v_idempotent boolean := false;
begin
  if nullif(btrim(p_candidate_commit),'') is null then raise exception 'candidate commit required'; end if;
  if nullif(btrim(p_merge_sha),'') is null then raise exception 'merge sha required'; end if;

  select * into v_run
  from public.factory_runs
  where id=p_run_id
  for update;
  if v_run.id is null then raise exception 'run not found'; end if;

  select * into v_task
  from public.factory_tasks
  where id=v_run.task_id
  for update;
  if v_task.id is null then raise exception 'task not found'; end if;

  select * into v_report
  from public.factory_release_reports
  where run_id=p_run_id
  order by created_at desc
  limit 1
  for update;
  if v_report.id is null then raise exception 'release report not found'; end if;
  if v_report.status<>'released' then raise exception 'release report is not released'; end if;
  if v_report.candidate_commit<>p_candidate_commit then raise exception 'release report candidate mismatch'; end if;

  v_report_merge_sha:=nullif(btrim(v_report.report->>'merge_sha'),'');
  if v_report_merge_sha is null or v_report_merge_sha<>p_merge_sha then
    raise exception 'release report merge sha mismatch';
  end if;

  if v_run.status='merged' then
    if v_run.candidate_commit<>p_merge_sha then raise exception 'merged run sha mismatch'; end if;
    if v_task.status<>'completed' then raise exception 'merged run task is not completed'; end if;
    v_idempotent:=true;
  else
    if v_run.status<>'awaiting_release' then raise exception 'run is not awaiting release'; end if;
    if v_run.candidate_commit<>p_candidate_commit then raise exception 'run candidate mismatch'; end if;
    if v_task.status not in ('ci_pending','awaiting_human','awaiting_release') then
      raise exception 'release task has incompatible status';
    end if;

    update public.factory_runs
    set status='merged',
        candidate_commit=p_merge_sha,
        finished_at=now(),
        metadata=metadata||jsonb_build_object(
          'release_observed',true,
          'release_source','console_human_merge',
          'release_candidate_commit',p_candidate_commit,
          'merge_sha',p_merge_sha
        )
    where id=p_run_id;

    update public.factory_tasks
    set status='completed',updated_at=now()
    where id=v_task.id;

    insert into public.factory_audit_events(
      project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
    )
    values(
      v_task.project_id,v_task.id,p_run_id,'system','release-followup',
      'release.human_merge_observed',
      jsonb_build_object(
        'source','console_human_merge',
        'candidate_commit',p_candidate_commit,
        'merge_sha',p_merge_sha
      )
    );
  end if;

  return jsonb_build_object(
    'run_id',p_run_id,
    'task_id',v_task.id,
    'status','merged',
    'merge_sha',p_merge_sha,
    'idempotent',v_idempotent
  );
end;
$$;

revoke all on function public.factory_finalize_console_human_release(uuid,text,text) from public,anon,authenticated;
grant execute on function public.factory_finalize_console_human_release(uuid,text,text) to service_role;
