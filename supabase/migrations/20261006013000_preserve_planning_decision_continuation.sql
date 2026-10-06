create or replace function public.factory_reconcile_terminal_task_descendants()
returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
  v_completed integer := 0;
  v_cancelled integer := 0;
  v_superseded integer := 0;
  v_row record;
begin
  for v_row in
    select
      child.id as task_id,
      child.project_id,
      child.status as old_status,
      parent.id as parent_task_id,
      parent.status as parent_status
    from public.factory_tasks child
    join public.factory_tasks parent on parent.id=child.parent_task_id
    where parent.status in ('completed','cancelled')
      and child.status not in ('completed','cancelled')
      and not exists (
        select 1
        from public.factory_runs gate_run
        join public.factory_human_gates gate on gate.run_id=gate_run.id
        where gate_run.task_id=child.id
          and gate.status='pending'
      )
      and not exists (
        select 1
        from public.factory_runs continuation_run
        where continuation_run.task_id=child.id
          and continuation_run.status in ('created','queued','running')
          and continuation_run.metadata->>'source'='planning-decision'
      )
    order by child.created_at,child.id
    for update of child
  loop
    if v_row.old_status='integrated' then
      update public.factory_tasks
      set status='completed',updated_at=now()
      where id=v_row.task_id;

      insert into public.factory_audit_events(
        project_id,task_id,actor_type,actor_ref,event_type,payload
      )
      values(
        v_row.project_id,v_row.task_id,'system','terminal-descendant-recovery',
        'task.descendant.reconciled',
        jsonb_build_object(
          'from_status',v_row.old_status,
          'to_status','completed',
          'parent_task_id',v_row.parent_task_id,
          'parent_status',v_row.parent_status,
          'reason','parent_terminal_child_already_integrated'
        )
      );
      v_completed:=v_completed+1;
    else
      update public.factory_tasks
      set status='cancelled',updated_at=now()
      where id=v_row.task_id;

      insert into public.factory_audit_events(
        project_id,task_id,actor_type,actor_ref,event_type,payload
      )
      values(
        v_row.project_id,v_row.task_id,'system','terminal-descendant-recovery',
        'task.descendant.reconciled',
        jsonb_build_object(
          'from_status',v_row.old_status,
          'to_status','cancelled',
          'parent_task_id',v_row.parent_task_id,
          'parent_status',v_row.parent_status,
          'reason','parent_terminal_child_no_longer_actionable'
        )
      );
      v_cancelled:=v_cancelled+1;
    end if;
  end loop;

  for v_row in
    select
      s.id as change_set_id,
      s.project_id,
      s.root_task_id,
      s.status as old_status
    from public.factory_change_sets s
    join public.factory_tasks root on root.id=s.root_task_id
    where root.status in ('completed','cancelled')
      and s.status not in ('completed','superseded')
    order by s.created_at,s.id
    for update of s
  loop
    update public.factory_change_sets
    set status='superseded',
        lease_owner=null,
        lease_expires_at=null,
        updated_at=now(),
        metadata=metadata||jsonb_build_object(
          'reconciliation',jsonb_build_object(
            'reason','root_task_terminal',
            'previous_status',v_row.old_status,
            'reconciled_at',now()
          )
        )
    where id=v_row.change_set_id;

    insert into public.factory_audit_events(
      project_id,task_id,actor_type,actor_ref,event_type,payload
    )
    values(
      v_row.project_id,v_row.root_task_id,'system','terminal-descendant-recovery',
      'change_set.superseded_after_terminal_root',
      jsonb_build_object(
        'change_set_id',v_row.change_set_id,
        'from_status',v_row.old_status,
        'to_status','superseded'
      )
    );
    v_superseded:=v_superseded+1;
  end loop;

  return jsonb_build_object(
    'completed_children',v_completed,
    'cancelled_children',v_cancelled,
    'superseded_change_sets',v_superseded
  );
end;
$$;

revoke all on function public.factory_reconcile_terminal_task_descendants() from public,anon,authenticated;
grant execute on function public.factory_reconcile_terminal_task_descendants() to service_role;


do $$
declare
  v_row record;
begin
  for v_row in
    select
      t.id as task_id,
      t.project_id,
      r.id as run_id,
      r.metadata->>'decision_gate_id' as decision_gate_id
    from public.factory_tasks t
    join public.factory_runs r on r.task_id=t.id
    join public.factory_human_gates g on g.id::text=r.metadata->>'decision_gate_id'
    where t.status='cancelled'
      and r.status='created'
      and r.metadata->>'source'='planning-decision'
      and g.status='approved'
      and exists (
        select 1
        from public.factory_audit_events e
        where e.task_id=t.id
          and e.event_type='task.descendant.reconciled'
          and e.payload->>'reason'='parent_terminal_child_no_longer_actionable'
      )
    order by t.created_at,t.id
    for update of t
  loop
    update public.factory_tasks
    set status='queued',updated_at=now()
    where id=v_row.task_id
      and status='cancelled';

    insert into public.factory_audit_events(
      project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
    )
    values(
      v_row.project_id,v_row.task_id,v_row.run_id,
      'system','planning-decision-continuation-recovery',
      'planning_decision.continuation.recovered',
      jsonb_build_object(
        'decision_gate_id',v_row.decision_gate_id,
        'from_status','cancelled',
        'to_status','queued',
        'reason','terminal_descendant_reconciliation_cancelled_valid_continuation'
      )
    );
  end loop;
end;
$$;
