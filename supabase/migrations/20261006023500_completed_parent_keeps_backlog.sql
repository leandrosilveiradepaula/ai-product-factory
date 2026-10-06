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
    where parent.status='cancelled'
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
          'reason','parent_cancelled_child_already_integrated'
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
          'reason','parent_cancelled_child_no_longer_actionable'
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
    where root.status='cancelled'
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
            'reason','root_task_cancelled',
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
      'change_set.superseded_after_cancelled_root',
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
  v_target_status text;
begin
  for v_row in
    select
      t.id as task_id,
      t.project_id,
      (
        select r.status
        from public.factory_runs r
        where r.task_id=t.id
        order by r.created_at desc,r.id desc
        limit 1
      ) as latest_run_status
    from public.factory_tasks t
    join public.factory_tasks parent on parent.id=t.parent_task_id
    where t.status='cancelled'
      and parent.status='completed'
      and exists (
        select 1
        from public.factory_audit_events e
        where e.task_id=t.id
          and e.event_type='task.descendant.reconciled'
          and e.payload->>'reason'='parent_terminal_child_no_longer_actionable'
          and e.payload->>'parent_status'='completed'
      )
    order by t.created_at,t.id
    for update of t
  loop
    v_target_status:=case
      when v_row.latest_run_status in ('created','queued','implementing','running') then 'queued_execution'
      else 'queued'
    end;

    update public.factory_tasks
    set status=v_target_status,updated_at=now()
    where id=v_row.task_id
      and status='cancelled';

    insert into public.factory_audit_events(
      project_id,task_id,actor_type,actor_ref,event_type,payload
    )
    values(
      v_row.project_id,v_row.task_id,
      'system','completed-parent-backlog-recovery',
      'task.descendant.recovered_after_completed_parent',
      jsonb_build_object(
        'from_status','cancelled',
        'to_status',v_target_status,
        'reason','completed_parent_satisfies_dependency'
      )
    );
  end loop;
end;
$$;


do $$
declare
  v_row record;
  v_target_status text;
begin
  for v_row in
    select
      s.id as change_set_id,
      s.project_id,
      s.root_task_id,
      coalesce(s.metadata#>>'{reconciliation,previous_status}','building') as previous_status
    from public.factory_change_sets s
    join public.factory_tasks root on root.id=s.root_task_id
    where s.status='superseded'
      and root.status='completed'
      and s.metadata#>>'{reconciliation,reason}'='root_task_terminal'
      and exists (
        select 1
        from public.factory_audit_events e
        where e.task_id=s.root_task_id
          and e.event_type='change_set.superseded_after_terminal_root'
          and e.payload->>'change_set_id'=s.id::text
      )
    order by s.created_at,s.id
    for update of s
  loop
    v_target_status:=case
      when v_row.previous_status in ('planned','building','integrating') then v_row.previous_status
      else 'building'
    end;

    update public.factory_change_sets
    set status=v_target_status,
        metadata=(metadata-'reconciliation')||jsonb_build_object(
          'recovery',jsonb_build_object(
            'reason','completed_root_keeps_change_set_actionable',
            'recovered_at',now()
          )
        ),
        updated_at=now()
    where id=v_row.change_set_id
      and status='superseded';

    insert into public.factory_audit_events(
      project_id,task_id,actor_type,actor_ref,event_type,payload
    )
    values(
      v_row.project_id,v_row.root_task_id,
      'system','completed-parent-backlog-recovery',
      'change_set.recovered_after_completed_root',
      jsonb_build_object(
        'change_set_id',v_row.change_set_id,
        'to_status',v_target_status,
        'reason','completed_root_keeps_change_set_actionable'
      )
    );
  end loop;
end;
$$;
