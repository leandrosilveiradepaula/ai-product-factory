BEGIN;
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
   and (
     (s.journey_id is not null and exists (
       select 1 from public.factory_journeys j
       where j.id=s.journey_id and j.project_id=p.id
         and j.state in ('executing','preview_verified','awaiting_release')
         and j.execution_generation=c.generation
         and j.source_commit=s.source_commit
         and j.binding->>'journey_id'=j.id::text
         and j.binding->>'project_id'=p.id::text
         and j.binding->>'request_id'=j.request_id::text
         and j.binding->>'source_commit'=s.source_commit
         and j.binding->>'integration_branch'=s.integration_branch
         and j.binding->>'policy_digest'=j.policy_digest
         and s.candidate_commit is not null
     ))
     or (s.journey_id is null and (
       p.project_kind<>'existing' or (
         p.repository is not null
         and p.manifest->'delivery_target'->>'mode'='open_pr_candidate'
         and p.manifest->'delivery_target'->>'sha'=s.source_commit
         and p.manifest->'delivery_target'->>'repository'=p.repository
         and p.manifest->'delivery_target'->>'branch' like 'preview/%'
       )
     ))
   ) and c.state='running'
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
$function$
;
REVOKE ALL ON FUNCTION public.factory_claim_change_set_integration(text,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.factory_claim_change_set_integration(text,integer) TO service_role;
COMMIT;