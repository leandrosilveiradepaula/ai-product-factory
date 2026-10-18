-- Candidate only. Requires explicit human authorization before production application.
begin;

create or replace function public.factory_assert_change_set_integration_epoch(
 p_change_set_id uuid,p_project_id uuid,p_generation bigint,p_worker_id text,p_wave integer
) returns void language plpgsql security invoker set search_path='' as $f$
declare v_state text;v_generation bigint;v_set record;
begin
 if p_change_set_id is null or p_project_id is null or p_generation is null or p_generation<1
    or nullif(btrim(p_worker_id),'') is null or p_wave is null or p_wave<1 then
   raise exception 'invalid integration capability' using errcode='PT400';
 end if;
 select state,generation into v_state,v_generation
 from public.factory_project_execution_controls where project_id=p_project_id for share;
 if v_state is distinct from 'running' or v_generation is distinct from p_generation then
   raise exception 'integration epoch revoked' using errcode='PT409';
 end if;
 select project_id,status,current_wave,lease_owner,lease_expires_at into v_set
 from public.factory_change_sets where id=p_change_set_id;
 if not found or v_set.project_id is distinct from p_project_id
    or v_set.status is distinct from 'integrating'
    or v_set.current_wave is distinct from p_wave
    or v_set.lease_owner is distinct from p_worker_id
    or v_set.lease_expires_at is null or v_set.lease_expires_at<=now() then
   raise exception 'integration lease revoked' using errcode='PT409';
 end if;
end;
$f$;
revoke all on function public.factory_assert_change_set_integration_epoch(uuid,uuid,bigint,text,integer) from public,anon,authenticated;
grant execute on function public.factory_assert_change_set_integration_epoch(uuid,uuid,bigint,text,integer) to service_role;

create or replace function public.factory_claim_change_set_integration(
 p_worker_id text,p_lease_seconds integer default 600
) returns jsonb language plpgsql security invoker set search_path='' as $f$
declare v_set public.factory_change_sets%rowtype;v_project public.factory_projects%rowtype;
 v_units jsonb;v_generation bigint;
begin
 if nullif(btrim(p_worker_id),'') is null or p_lease_seconds<1 or p_lease_seconds>600 then
  raise exception 'invalid integration lease request' using errcode='PT400';
 end if;
 select s.* into v_set from public.factory_change_sets s
 join public.factory_project_execution_controls c on c.project_id=s.project_id
 where s.status in ('building','integrating') and c.state='running'
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
$f$;
revoke all on function public.factory_claim_change_set_integration(text,integer) from public,anon,authenticated;
grant execute on function public.factory_claim_change_set_integration(text,integer) to service_role;
commit;
