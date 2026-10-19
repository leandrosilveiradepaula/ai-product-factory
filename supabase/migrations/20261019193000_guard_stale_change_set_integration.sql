-- Prevent stale externally advanced Preview SHAs from consuming integration
-- attempts or keeping idle GitHub Actions runners awake. The incident:
-- CRM Change Set 552fd082 completed its one Work Unit but the Direct job failed
-- in terminal cleanup. The branch was advanced outside its integration path
-- and the existing queue signal still advertised the stale Change Set as work.
--
-- These replacements are read/claim guards; the migration does not update
-- existing Change Sets, runs, PRs, project pins, or production application data.
-- Applying it to the production Control Plane requires separate human approval.
-- PostgreSQL function grants remain service_role-only; RLS is untouched.
--
-- This guard does not prove a stale Change Set was integrated. It keeps the
-- original row and Work Unit as historical evidence and reports the count.
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
     where j.status='queued' and j.role='security'
   ),
   'specialist_qa_work', exists(
     select 1 from public.factory_specialist_lane_jobs j
     where j.status='queued' and j.role='qa'
   ),
   'specialist_operations_work', exists(
     select 1 from public.factory_specialist_lane_jobs j
     where j.status='queued' and j.role='operations'
   )
 );
$$;
revoke all on function public.factory_scheduler_queue_signals()
 from public,anon,authenticated;
grant execute on function public.factory_scheduler_queue_signals() to service_role;

CREATE OR REPLACE FUNCTION public.factory_claim_change_set_integration(p_worker_id text, p_lease_seconds integer DEFAULT 600)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY INVOKER
 SET search_path TO ''
AS $function$
declare v_set public.factory_change_sets%rowtype;v_project public.factory_projects%rowtype;
 v_units jsonb;v_generation bigint;
begin
 if nullif(btrim(p_worker_id),'') is null or p_lease_seconds<1 or p_lease_seconds>600 then
  raise exception 'invalid integration lease request' using errcode='PT400';
 end if;
 select s.* into v_set from public.factory_change_sets s
 join public.factory_project_execution_controls c on c.project_id=s.project_id
 join public.factory_projects p on p.id=s.project_id
 where s.status in ('building','integrating') and p.is_active=true
   and (p.project_kind<>'existing' or (
     p.repository is not null
     and p.manifest->'delivery_target'->>'mode'='open_pr_candidate'
     and p.manifest->'delivery_target'->>'sha'=s.source_commit
     and p.manifest->'delivery_target'->>'repository'=p.repository
     and p.manifest->'delivery_target'->>'branch' like 'preview/%'
   )) and c.state='running'
   and c.generation>0 and s.attempt_count<3
   and (s.lease_expires_at is null or s.lease_expires_at<=now())
   and exists(select 1 from public.factory_change_set_work_units u
       where u.change_set_id=s.id and u.wave=s.current_wave)
   and not exists(select 1 from public.factory_change_set_work_units u
       where u.change_set_id=s.id and u.wave=s.current_wave and u.status<>'completed')
 order by s.created_at for update of s skip locked limit 1;
 if not found then return null; end if;
 select * into v_project from public.factory_projects where id=v_set.project_id;
 select generation into v_generation from public.factory_project_execution_controls
  where project_id=v_set.project_id for share;
 if v_generation is null then raise exception 'missing integration generation' using errcode='PT409'; end if;
 select jsonb_agg(jsonb_build_object(
  'work_unit_id',u.id,'task_id',u.task_id,'plan_task_key',u.plan_task_key,'agent_key',u.agent_key,
  'base_commit',u.base_commit,'branch_name',u.branch_name,'output_commit',u.output_commit,
  'changed_files',u.changed_files) order by u.plan_task_key) into v_units
 from public.factory_change_set_work_units u
 where u.change_set_id=v_set.id and u.wave=v_set.current_wave and u.status='completed';
 update public.factory_change_sets set status='integrating',lease_owner=p_worker_id,
   lease_expires_at=now()+make_interval(secs=>p_lease_seconds),
   attempt_count=attempt_count+1,updated_at=now() where id=v_set.id;
 return jsonb_build_object(
  'change_set_id',v_set.id,'project_id',v_set.project_id,'execution_generation',v_generation,
  'lease_owner',p_worker_id,'project_key',v_project.project_key,'repository',v_project.repository,
  'source_commit',v_set.source_commit,'candidate_commit',v_set.candidate_commit,
  'integration_branch',v_set.integration_branch,'current_wave',v_set.current_wave,
  'work_units',coalesce(v_units,'[]'::jsonb));
end;
$function$;
revoke all on function public.factory_claim_change_set_integration(text,integer)
    from public,anon,authenticated;
grant execute on function public.factory_claim_change_set_integration(text,integer)
    to service_role;
