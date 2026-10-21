-- Terminal cleanup must not cancel preserved work during operator Pause/Stop.
-- Captured from live public.factory_reconcile_terminal_task_descendants() on 2026-10-21.
-- One existing invoker-rights, service-role-only RPC is replaced; no GRANT,
-- default privileges, public RLS policies or destructive DDL are changed.
-- Row locks on the project AND execution control are taken with SKIP LOCKED
-- in the same candidate query before task/Change Set mutations. An operator
-- Pause/Stop holding the control row causes only that candidate to be skipped.
-- An authorized recovery holding its share lock makes Pause/Stop wait until
-- the short transaction has committed. No cross-project parent/root binding.
BEGIN;
CREATE OR REPLACE FUNCTION public.factory_reconcile_terminal_task_descendants()
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
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
    join public.factory_tasks parent on parent.id=child.parent_task_id and parent.project_id=child.project_id
    join public.factory_projects p on p.id=child.project_id and p.is_active=true
    join public.factory_project_execution_controls c on c.project_id=p.id and c.state='running' and c.generation>0
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
    for update of child skip locked
    for share of c,p skip locked
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
    join public.factory_tasks root on root.id=s.root_task_id and root.project_id=s.project_id
    join public.factory_projects p on p.id=s.project_id and p.is_active=true
    join public.factory_project_execution_controls c on c.project_id=p.id and c.state='running' and c.generation>0
    where root.status='cancelled'
      and s.status not in ('completed','superseded')
    order by s.created_at,s.id
    for update of s skip locked
    for share of c,p skip locked
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
$function$;
COMMIT;
