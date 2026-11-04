-- Repair production-observed V2 scheduler liveness mismatch, 2026-11-04.
-- Evidence: CRM #209 Change Set 3f09952e, wave 5 completed,
-- claim RPC eligible, but factory_scheduler_queue_signals() said
-- integration_work=false and stale_integration_change_sets=1 because the
-- legacy manifest pin differs from the immutable V2 journey source.
-- Do not widen legacy admission, modify tasks, call models or merge PRs.
-- Read-only scheduler wake eligibility, captured from live SQL 2026-10-20.
-- Project control commands fence Product Stage, routed manual Codex and specialist
-- lanes before the queue signal. CI/release are passive observation signals,
-- not authorization to mutate; their consumers retain separate gates.
BEGIN;
CREATE OR REPLACE FUNCTION public.factory_scheduler_queue_signals()
 RETURNS jsonb
 LANGUAGE sql
 STABLE
 SECURITY INVOKER
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
       -- Native Journey V2 is bound to its own immutable Start, not
       -- the legacy manifest's delivery_target SHA. Match the claim RPC.
       and (
         (cs.journey_id is not null and exists (
           select 1 from public.factory_journeys j
           where j.id=cs.journey_id and j.project_id=p.id
             and j.state in ('executing','preview_verified','awaiting_release')
             and j.execution_generation=c.generation
             and j.source_commit=cs.source_commit
             and j.binding->>'journey_id'=j.id::text
             and j.binding->>'project_id'=p.id::text
             and j.binding->>'request_id'=j.request_id::text
             and j.binding->>'source_commit'=cs.source_commit
             and j.binding->>'integration_branch'=cs.integration_branch
             and j.binding->>'policy_digest'=j.policy_digest
             and cs.candidate_commit is not null
         ))
         or (cs.journey_id is null and (
           p.project_kind<>'existing' or (
             p.repository is not null
             and p.manifest->'delivery_target'->>'mode'='open_pr_candidate'
             and p.manifest->'delivery_target'->>'sha'=cs.source_commit
             and p.manifest->'delivery_target'->>'repository'=p.repository
             and p.manifest->'delivery_target'->>'branch' like 'preview/%'
           )
         ))
       )
   ),
   -- This count is diagnostic only. It must not wake a paid worker or
   -- mistake a superseded Change Set for runnable integration.
   'stale_integration_change_sets', (
     select count(*) from public.factory_change_sets cs
     join public.factory_projects p on p.id=cs.project_id
     join public.factory_project_execution_controls c on c.project_id=p.id
     where cs.status in ('building','integrating')
       and p.is_active=true and p.project_kind='existing'
       and cs.journey_id is null
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
