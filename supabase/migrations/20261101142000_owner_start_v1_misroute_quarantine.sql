-- Audited, single-run quarantine for an incorrectly admitted legacy OWNER Start.
-- Safe only while the CRM remains paused. Does not create a Journey or release.
begin;

create or replace function public.factory_quarantine_owner_v1_misroute(
 p_run_id uuid, p_task_id uuid, p_command_id uuid, p_actor_id uuid,
 p_expected_generation bigint, p_expected_version bigint,
 p_comment_id bigint, p_request_id uuid
) returns jsonb language plpgsql security invoker set search_path='' as $fn$
declare
 v_project public.factory_projects%rowtype;
 v_control public.factory_project_execution_controls%rowtype;
 v_run public.factory_runs%rowtype;
 v_task public.factory_tasks%rowtype;
 v_old jsonb;
 v_receipt jsonb;
begin
 if p_run_id is null or p_task_id is null or p_command_id is null
    or p_actor_id is null or p_expected_generation is null
    or p_expected_version is null or p_comment_id is null or p_comment_id<1
    or p_request_id is null then
   raise exception 'invalid owner misroute recovery arguments' using errcode='PT400';
 end if;
 if not exists(select 1 from public.factory_console_operators o
   where o.user_id=p_actor_id and o.role='admin' and o.is_active=true) then
   raise exception 'owner misroute recovery requires active admin' using errcode='PT403';
 end if;

 select * into v_project from public.factory_projects p
   where p.project_key='crm-infodive'
     and p.repository='leandrosilveiradepaula/crm-infodive'
     and p.project_kind='existing' and p.is_active=true for update;
 if not found then raise exception 'CRM existing project not found' using errcode='PT409'; end if;

 -- Serialized replay is safe only for the exact same command/parameters.
 select a.payload into v_old from public.factory_audit_events a
   where a.project_id=v_project.id
     and a.event_type='owner_start.v1_misroute_quarantined'
     and a.payload->>'command_id'=p_command_id::text
   order by a.id desc limit 1;
 if v_old is not null then
   if v_old->>'run_id' is distinct from p_run_id::text
      or v_old->>'task_id' is distinct from p_task_id::text
      or v_old->>'actor_id' is distinct from p_actor_id::text
      or v_old->>'comment_id' is distinct from p_comment_id::text
      or v_old->>'request_id' is distinct from p_request_id::text
      or v_old->>'generation' is distinct from p_expected_generation::text
      or v_old->>'control_version' is distinct from p_expected_version::text
   then raise exception 'owner misroute command replay mismatch' using errcode='PT409'; end if;
   return v_old->'receipt';
 end if;

 select * into v_control from public.factory_project_execution_controls c
   where c.project_id=v_project.id for update;
 select * into v_run from public.factory_runs r where r.id=p_run_id for update;
 select * into v_task from public.factory_tasks t where t.id=p_task_id for update;

 if v_control.state is distinct from 'paused'
    or v_control.generation is distinct from p_expected_generation
    or v_control.version is distinct from p_expected_version
    or not public.factory_control_quiescent(v_project.id)
    or v_project.manifest->'journey_delivery_binding_v2'->>'enabled' is distinct from 'true'
    or v_run.id is null or v_task.id is null or v_run.task_id is distinct from v_task.id
    or v_task.project_id is distinct from v_project.id
    or v_run.status is distinct from 'created' or v_task.status is distinct from 'queued'
    or v_run.journey_id is not null or v_task.journey_id is not null
    or v_task.parent_task_id is not null
    or v_run.lease_owner is not null or v_run.lease_expires_at is not null
    or v_run.source_commit is not null or v_run.candidate_commit is not null
    or v_run.branch_name is not null
    or v_run.metadata->>'source' is distinct from 'github-owner'
    or v_run.metadata->>'execution_generation' is distinct from v_control.generation::text
    or v_run.metadata->>'continuation_request_id' is distinct from p_request_id::text
    or v_run.metadata->'continuation_request'->'github'->>'comment_id' is distinct from p_comment_id::text
    or v_run.metadata->'continuation_request'->'github'->>'issue_number' is distinct from '1055'
    or v_run.metadata->'continuation_request'->'github'->>'actor_id' is distinct from '256917842'
    or v_run.metadata->'stages' is distinct from '["reconciliation","gap_analysis","planning"]'::jsonb
 then raise exception 'owner misroute is not unstarted or epoch mismatch' using errcode='PT409'; end if;

 if exists(select 1 from public.factory_tasks t where t.parent_task_id=v_task.id)
    or exists(select 1 from public.factory_change_sets s where s.root_task_id=v_task.id)
    or exists(select 1 from public.factory_human_gates g where g.run_id=v_run.id)
    or exists(select 1 from public.factory_evaluations e where e.run_id=v_run.id)
    or exists(select 1 from public.factory_deployments d where d.run_id=v_run.id)
    or exists(select 1 from public.factory_release_reports d where d.run_id=v_run.id)
    or (select count(*) from public.factory_tool_usage u where u.run_id=v_run.id) <> 1
    or exists(select 1 from public.factory_tool_usage u where u.run_id=v_run.id
       and (u.operation is distinct from 'enqueue_project_reconciliation'
         or u.metadata->>'request_id' is distinct from p_request_id::text
         or u.metadata->>'comment_id' is distinct from p_comment_id::text))
    or (select count(*) from public.factory_audit_events a where a.run_id=v_run.id) <> 2
    or exists(select 1 from public.factory_audit_events a where a.run_id=v_run.id
        and a.event_type not in ('project.continuation.requested','project.reconciliation.enqueued'))
 then raise exception 'owner misroute has execution evidence or unsafe descendants' using errcode='PT409'; end if;

 update public.factory_runs set status='cancelled',finished_at=now(),
   last_error='legacy OWNER Start was misrouted without Journey V2 binding'
   where id=v_run.id and status='created';
 if not found then raise exception 'owner misroute run CAS lost' using errcode='PT409'; end if;
 update public.factory_tasks set status='cancelled',updated_at=now()
   where id=v_task.id and status='queued';
 if not found then raise exception 'owner misroute task CAS lost' using errcode='PT409'; end if;

 v_receipt:=jsonb_build_object('status','quarantined','run_id',v_run.id,
    'task_id',v_task.id,'project_id',v_project.id,'generation',v_control.generation,
    'control_version',v_control.version,'created',true,
    'journey_created',false,'ready_for_production',false);
 insert into public.factory_audit_events(
  project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
 ) values(v_project.id,v_task.id,v_run.id,'human',p_actor_id::text,
   'owner_start.v1_misroute_quarantined',jsonb_build_object(
     'command_id',p_command_id,'run_id',v_run.id,'task_id',v_task.id,
     'actor_id',p_actor_id,'comment_id',p_comment_id,'request_id',p_request_id,
     'generation',p_expected_generation,'control_version',p_expected_version,
     'receipt',v_receipt));
 return v_receipt;
end $fn$;

revoke all on function public.factory_quarantine_owner_v1_misroute(
 uuid,uuid,uuid,uuid,bigint,bigint,bigint,uuid) from public,anon,authenticated;
grant execute on function public.factory_quarantine_owner_v1_misroute(
 uuid,uuid,uuid,uuid,bigint,bigint,bigint,uuid) to service_role;

commit;
