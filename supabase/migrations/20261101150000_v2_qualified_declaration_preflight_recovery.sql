-- A single auditable retry of an already failed Journey V2 source preflight.
-- Does not run models, rewrite source binding, or fabricate delivery evidence.
begin;

create or replace function public.factory_requeue_v2_declaration_preflight_once(
  p_journey_id uuid, p_run_id uuid, p_command_id uuid, p_actor_id uuid,
  p_expected_generation bigint, p_expected_version bigint,
  p_expected_source_commit text
) returns jsonb language plpgsql security invoker set search_path='' as $fn$
declare
 p public.factory_projects%rowtype;
 c public.factory_project_execution_controls%rowtype;
 j public.factory_journeys%rowtype;
 r public.factory_runs%rowtype;
 t public.factory_tasks%rowtype;
 prior jsonb;
 receipt jsonb;
begin
 if p_journey_id is null or p_run_id is null or p_command_id is null or p_actor_id is null
   or p_expected_generation is null or p_expected_version is null
   or p_expected_source_commit !~ '^[0-9a-f]{40}$'
 then raise exception 'invalid V2 preflight requeue arguments' using errcode='PT400'; end if;
 if not exists(select 1 from public.factory_console_operators o
    where o.user_id=p_actor_id and o.is_active=true and o.role='admin')
 then raise exception 'V2 preflight requeue requires active admin' using errcode='PT403'; end if;

 select * into p from public.factory_projects
   where project_key='crm-infodive' and is_active=true
     and repository='leandrosilveiradepaula/crm-infodive'
     and project_kind='existing' for update;
 if p.id is null then raise exception 'CRM existing project unavailable' using errcode='PT409'; end if;

 select a.payload into prior from public.factory_audit_events a
  where a.project_id=p.id
    and a.event_type='journey.source_declaration_preflight_requeued'
    and a.payload->>'command_id'=p_command_id::text
  order by a.id desc limit 1;
 if prior is not null then
   if prior->>'journey_id' is distinct from p_journey_id::text
      or prior->>'run_id' is distinct from p_run_id::text
      or prior->>'actor_id' is distinct from p_actor_id::text
      or prior->>'expected_generation' is distinct from p_expected_generation::text
      or prior->>'expected_version' is distinct from p_expected_version::text
      or prior->>'source_commit' is distinct from p_expected_source_commit
   then raise exception 'V2 declaration recovery replay mismatch' using errcode='PT409'; end if;
   return prior->'receipt';
 end if;

 select * into c from public.factory_project_execution_controls
   where project_id=p.id for update;
 select * into j from public.factory_journeys
   where id=p_journey_id and project_id=p.id for update;
 select * into r from public.factory_runs
   where id=p_run_id and journey_id=p_journey_id for update;
 select * into t from public.factory_tasks
   where id=r.task_id and project_id=p.id for update;

 if c.state is distinct from 'running'
    or c.generation is distinct from p_expected_generation
    or c.version is distinct from p_expected_version
    or j.id is null or j.state is distinct from 'executing'
    or j.execution_generation is distinct from c.generation
    or j.source_commit is distinct from p_expected_source_commit
    or j.binding->>'source_commit' is distinct from p_expected_source_commit
    or j.binding->>'execution_generation' is distinct from c.generation::text
    or j.binding->>'integration_branch' is distinct from r.branch_name
    or j.request_snapshot->>'text' not like '%issue #209%'
    or j.request_snapshot->>'text' not like '%leandrosilveiradepaula/crm-infodive%'
    or j.project_policy_version is distinct from 3
    or j.policy_digest is distinct from p.manifest->'journey_delivery_binding_v2'->>'digest'
    or r.id is null or t.id is null or t.journey_id is distinct from j.id
    or r.status is distinct from 'failed' or t.status is distinct from 'failed'
    or r.execution_route is distinct from 'direct'
    or r.source_commit is distinct from j.source_commit
    or r.metadata->>'execution_generation' is distinct from c.generation::text
    or r.metadata->'journey_binding_v2' is distinct from j.binding
    or r.metadata->>'error' is distinct from 'journey_reported_existing_code_not_at_source'
    or r.metadata->'stages' is distinct from '["reconciliation","gap_analysis","planning"]'::jsonb
    or r.metadata ? 'stage_evidence' or r.metadata ? 'preflight_recovery_once'
    or r.metadata ? 'resume_checkpoint'
    or r.lease_owner is not null or r.lease_expires_at is not null
    or r.candidate_commit is not null or j.candidate_commit is not null
    or j.work_unit_output_commit is not null
    or j.production_release_sha is not null
    or not public.factory_control_quiescent(p.id)
 then raise exception 'V2 declaration preflight recovery context is unsafe' using errcode='PT409'; end if;

 if exists(select 1 from public.factory_runs other
      join public.factory_tasks ot on ot.id=other.task_id
      where ot.project_id=p.id and other.status in ('running','created','queued'))
   or exists(select 1 from public.factory_tasks child where child.parent_task_id=t.id)
   or exists(select 1 from public.factory_change_sets cs where cs.journey_id=j.id)
   or exists(select 1 from public.factory_human_gates g where g.run_id=r.id)
   or exists(select 1 from public.factory_deployments d where d.run_id=r.id)
   or exists(select 1 from public.factory_release_reports report where report.run_id=r.id)
   or exists(select 1 from public.factory_evaluations ev where ev.run_id=r.id)
   or exists(select 1 from public.factory_tool_usage u where u.run_id=r.id)
   or exists(select 1 from public.factory_audit_events a
      where a.run_id=r.id
        and a.event_type not in ('journey.source_bound','journey.executing','run.claimed','run.failed'))
   or (select count(*) from public.factory_audit_events a
      where a.run_id=r.id and a.event_type='run.failed') is distinct from 1
   or (select count(*) from public.factory_audit_events a
      where a.run_id=r.id and a.event_type='run.claimed') is distinct from 1
   or exists(select 1 from public.factory_audit_events a
      where a.project_id=p.id
        and a.event_type='journey.source_declaration_preflight_requeued'
        and a.payload->>'run_id'=r.id::text)
 then raise exception 'V2 preflight recovery already advanced or previously used' using errcode='PT409'; end if;

 -- Original failed evidence survives in run.failed audit. Clear worker claim
 -- and derived status only after every guard above has passed.
 update public.factory_runs set
   status='queued',started_at=null,finished_at=null,last_error=null,
   metadata=(metadata-'error'-'worker_id'-'claimed_at')||
     jsonb_build_object('preflight_recovery_once',jsonb_build_object(
       'reason','qualified_method_declaration_false_positive',
       'previous_error','journey_reported_existing_code_not_at_source',
       'command_id',p_command_id::text,'requeued_at',now()))
 where id=r.id and status='failed';
 if not found then raise exception 'V2 preflight run CAS lost' using errcode='PT409'; end if;
 update public.factory_tasks set status='queued',updated_at=now()
 where id=t.id and status='failed';
 if not found then raise exception 'V2 preflight task CAS lost' using errcode='PT409'; end if;

 receipt:=jsonb_build_object(
   'status','requeued','journey_id',j.id,'run_id',r.id,'task_id',t.id,
   'generation',c.generation,'source_commit',j.source_commit,
   'paid_calls',0,'release_authorized',false,'created',true);
 insert into public.factory_audit_events(
   project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
 ) values(p.id,t.id,r.id,'human',p_actor_id::text,
   'journey.source_declaration_preflight_requeued',
   jsonb_build_object(
     'command_id',p_command_id,'journey_id',j.id,'run_id',r.id,'actor_id',p_actor_id,
     'expected_generation',p_expected_generation,'expected_version',p_expected_version,
     'source_commit',p_expected_source_commit,'receipt',receipt));
 return receipt;
end $fn$;

revoke all on function public.factory_requeue_v2_declaration_preflight_once(
 uuid,uuid,uuid,uuid,bigint,bigint,text
) from public,anon,authenticated;
grant execute on function public.factory_requeue_v2_declaration_preflight_once(
 uuid,uuid,uuid,uuid,bigint,bigint,text
) to service_role;

commit;
