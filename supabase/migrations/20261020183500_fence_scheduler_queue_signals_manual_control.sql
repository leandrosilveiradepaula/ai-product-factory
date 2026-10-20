-- Read-only scheduler wake eligibility, captured from live SQL 2026-10-20.
-- Project control commands fence Product Stage, routed manual Codex and specialist
-- lanes before the queue signal. CI/release are passive observation signals,
-- not authorization to mutate; their consumers retain separate gates.
BEGIN;
CREATE OR REPLACE FUNCTION public.factory_scheduler_queue_signals()
 RETURNS jsonb
 LANGUAGE sql
 STABLE
 SET search_path TO ''
AS $function$
 select jsonb_build_object(
   'product_work', exists(
     select 1 from public.factory_runs r
     join public.factory_tasks t on t.id=r.task_id
     join public.factory_projects p on p.id=t.project_id
     join public.factory_project_execution_controls c on c.project_id=p.id and c.state='running' and c.generation>0
     where r.status in ('created','queued') and t.status='queued'
       and p.is_active=true
   ),
   'routed_execution_work', exists(
     select 1 from public.factory_runs r
     join public.factory_tasks t on t.id=r.task_id
     join public.factory_projects p on p.id=t.project_id
     join public.factory_project_execution_controls c on c.project_id=p.id and c.state='running' and c.generation>0
     where r.status='queued' and r.execution_route in ('direct','codex')
       and t.status='queued_execution' and p.is_active=true
   ),
   'codex_manual_work', exists(
     select 1 from public.factory_runs r
     join public.factory_tasks t on t.id=r.task_id
     join public.factory_projects p on p.id=t.project_id
     join public.factory_project_execution_controls c on c.project_id=p.id and c.state='running' and c.generation>0
     where p.is_active=true and (
       r.status='awaiting_codex_manual'
       or (r.status='queued' and r.execution_route='codex'
           and r.metadata->>'codex_execution_mode'='manual'
           and t.status='queued_execution')
     )
   ),
   'integration_work', exists(
     select 1 from public.factory_change_sets cs
     join public.factory_projects p on p.id=cs.project_id
     join public.factory_project_execution_controls c on c.project_id=p.id
     where p.is_active=true and c.state='running' and c.generation>0
       and cs.status in ('building','integrating') and cs.attempt_count<3
       and (cs.lease_expires_at is null or cs.lease_expires_at<=now())
       and exists (
         select 1 from public.factory_change_set_work_units u
         where u.change_set_id=cs.id and u.wave=cs.current_wave
       )
       and not exists (
         select 1 from public.factory_change_set_work_units u
         where u.change_set_id=cs.id and u.wave=cs.current_wave
           and u.status<>'completed'
       )
       and (p.project_kind<>'existing' or (
         p.repository is not null
         and p.manifest->'delivery_target'->>'mode'='open_pr_candidate'
         and p.manifest->'delivery_target'->>'sha'=cs.source_commit
         and p.manifest->'delivery_target'->>'repository'=p.repository
         and p.manifest->'delivery_target'->>'branch' like 'preview/%'
       ))
   ),
   -- This count is diagnostic only. It must not wake a paid worker or
   -- mistake a superseded Change Set for runnable integration.
   'stale_integration_change_sets', (
     select count(*) from public.factory_change_sets cs
     join public.factory_projects p on p.id=cs.project_id
     join public.factory_project_execution_controls c on c.project_id=p.id
     where cs.status in ('building','integrating')
       and p.is_active=true and p.project_kind='existing'
       and c.state='running'
       and cs.source_commit is distinct from p.manifest->'delivery_target'->>'sha'
       and exists (
         select 1 from public.factory_change_set_work_units u
         where u.change_set_id=cs.id and u.wave=cs.current_wave
       )
       and not exists (
         select 1 from public.factory_change_set_work_units u
         where u.change_set_id=cs.id and u.wave=cs.current_wave
           and u.status<>'completed'
       )
   ),
   'ci_work', exists(
     select 1 from public.factory_runs r where r.status='ci_pending'
   ),
   'release_work', exists(
     select 1 from public.factory_runs r where r.status='awaiting_release'
   ),
   'specialist_security_work', exists(
     select 1 from public.factory_specialist_lane_jobs j
     join public.factory_projects p on p.id=j.project_id
     join public.factory_project_execution_controls c on c.project_id=p.id
     where p.is_active=true and c.state='running' and c.generation>0
       and j.status='queued' and j.role='security'
   ),
   'specialist_qa_work', exists(
     select 1 from public.factory_specialist_lane_jobs j
     join public.factory_projects p on p.id=j.project_id
     join public.factory_project_execution_controls c on c.project_id=p.id
     where p.is_active=true and c.state='running' and c.generation>0
       and j.status='queued' and j.role='qa'
   ),
   'specialist_operations_work', exists(
     select 1 from public.factory_specialist_lane_jobs j
     join public.factory_projects p on p.id=j.project_id
     join public.factory_project_execution_controls c on c.project_id=p.id
     where p.is_active=true and c.state='running' and c.generation>0
       and j.status='queued' and j.role='operations'
   )
 );
$function$
;
REVOKE ALL ON FUNCTION public.factory_scheduler_queue_signals() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.factory_scheduler_queue_signals() TO service_role;
COMMIT;
