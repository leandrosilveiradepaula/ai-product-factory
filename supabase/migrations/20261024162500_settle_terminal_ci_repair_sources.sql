-- Terminal CI repair source settlement (no release, no candidate rewrite).
-- Apply only through the approved Control Plane production migration gate.
begin;

create or replace function public.factory_settle_terminal_ci_repair_sources_v1(
  p_max_items integer default 3
) returns jsonb
language plpgsql security invoker set search_path = '' as $factory$
declare
  v_item record;
  v_settled integer := 0;
begin
  if p_max_items is null or p_max_items not between 1 and 4 then
    raise exception 'invalid bounded terminal CI repair settlement request'
      using errcode = 'PT400';
  end if;

  -- A passed repair receipt alone cannot close a run. The exact integrated
  -- candidate, matching source/repair lineage, current project epoch and
  -- completed parent task MUST all agree. Never revive stale epochs.
  for v_item in
    select repair.id as repair_id, repair.source_run_id, repair.release_run_id,
           repair.change_set_id, source.task_id,
           repair.original_candidate_commit, repair.repaired_commit,
           repair.project_id
    from public.factory_ci_repair_requests repair
    join public.factory_change_sets cs
      on cs.id = repair.change_set_id
     and cs.project_id = repair.project_id
     and cs.release_run_id = repair.release_run_id
     and cs.candidate_commit = repair.repaired_commit
     and cs.status = 'completed'
    join public.factory_runs source
      on source.id = repair.source_run_id
     and source.status = 'repair_pending'
     and source.candidate_commit = repair.original_candidate_commit
     and source.metadata->>'change_set_id' = repair.change_set_id::text
     and source.metadata->>'ci_repair_request_id' = repair.id::text
     and source.metadata->>'execution_generation' = repair.execution_generation::text
     and source.lease_owner is null
    join public.factory_runs release_run
      on release_run.id = repair.release_run_id
     and release_run.id <> source.id
     and release_run.task_id = source.task_id
     and release_run.candidate_commit = repair.repaired_commit
     and release_run.metadata->>'change_set_id' = repair.change_set_id::text
     and release_run.metadata->>'execution_generation' = repair.execution_generation::text
     and release_run.status = 'integrated'
     and release_run.lease_owner is null
    join public.factory_tasks task
      on task.id = source.task_id
     and task.project_id = repair.project_id
     and task.status = 'completed'
    join public.factory_projects project
      on project.id = repair.project_id
     and project.project_kind = 'existing'
     and project.is_active
    join public.factory_project_execution_controls control
      on control.project_id = repair.project_id
     and control.state = 'running'
     and control.generation = repair.execution_generation
    where repair.status = 'passed'
      and repair.repaired_commit ~ '^[0-9a-f]{40}$'
      and repair.original_candidate_commit ~ '^[0-9a-f]{40}$'
      and repair.lease_owner is null
      and cs.lease_owner is null
    order by repair.created_at, repair.id
    limit p_max_items
    for update of repair, source, release_run, cs, task, project, control skip locked
  loop
    update public.factory_runs
       set status = 'completed', finished_at = now()
     where id = v_item.source_run_id
       and status = 'repair_pending'
       and lease_owner is null;
    if not found then
      raise exception 'terminal CI repair settlement lost source lease'
        using errcode = 'PT409';
    end if;
    insert into public.factory_audit_events(
      project_id, task_id, run_id, actor_type, actor_ref, event_type, payload
    ) values (
      v_item.project_id, v_item.task_id, v_item.source_run_id,
      'system', 'ci-repair-terminal-settle',
      'ci.repair.source_terminal_settled',
      jsonb_build_object(
        'repair_request_id', v_item.repair_id,
        'change_set_id', v_item.change_set_id,
        'release_run_id', v_item.release_run_id,
        'original_candidate_commit', v_item.original_candidate_commit,
        'repaired_commit', v_item.repaired_commit,
        'source_status_before', 'repair_pending',
        'source_status_after', 'completed',
        'release_observed', false,
        'paid_model_calls', 0
      )
    );
    v_settled := v_settled + 1;
  end loop;

  return jsonb_build_object(
    'status', case when v_settled > 0 then 'settled' else 'idle' end,
    'settled', v_settled, 'max_items', p_max_items,
    'release_authorized', false, 'paid_model_calls', 0
  );
end;
$factory$;

revoke all on function public.factory_settle_terminal_ci_repair_sources_v1(integer)
  from public, anon, authenticated;
grant execute on function public.factory_settle_terminal_ci_repair_sources_v1(integer)
  to service_role;
commit;
