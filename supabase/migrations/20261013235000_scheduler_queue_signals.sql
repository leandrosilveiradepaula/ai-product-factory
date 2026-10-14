-- Read-only authoritative queue existence signals. No global window cap.
-- Helps scheduler detect legitimate work when legacy audits exceed 400 rows.
create or replace function public.factory_scheduler_queue_signals()
returns jsonb
language sql stable security invoker set search_path=''
as $$
 select jsonb_build_object(
   'product_work', exists(
     select 1 from public.factory_runs r
     join public.factory_tasks t on t.id=r.task_id
     join public.factory_projects p on p.id=t.project_id
     where r.status in ('created','queued') and t.status='queued'
       and p.is_active=true
   ),
   'routed_execution_work', exists(
     select 1 from public.factory_runs r
     join public.factory_tasks t on t.id=r.task_id
     join public.factory_projects p on p.id=t.project_id
     where r.status='queued' and r.execution_route in ('direct','codex')
       and t.status='queued_execution' and p.is_active=true
   ),
   'codex_manual_work', exists(
     select 1 from public.factory_runs r
     join public.factory_tasks t on t.id=r.task_id
     join public.factory_projects p on p.id=t.project_id
     where p.is_active=true and (
       r.status='awaiting_codex_manual'
       or (r.status='queued' and r.execution_route='codex'
           and t.status='queued_execution')
     )
   )
 );
$$;
revoke all on function public.factory_scheduler_queue_signals()
 from public,anon,authenticated;
grant execute on function public.factory_scheduler_queue_signals() to service_role;
