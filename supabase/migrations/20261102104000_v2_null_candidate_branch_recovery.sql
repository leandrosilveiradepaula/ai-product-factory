-- V2 frozen-source branch fix and one bounded CRM #209 recovery.
begin;

CREATE OR REPLACE FUNCTION public.factory_bind_change_set_source(p_run_id uuid, p_source_commit text, p_integration_branch text, p_work_branch text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare v_unit public.factory_change_set_work_units%rowtype;v_set public.factory_change_sets%rowtype;
begin
 if p_source_commit is null or p_source_commit !~ '^[0-9a-f]{40}$' then raise exception 'invalid source commit SHA' using errcode='PT400'; end if;
 if nullif(btrim(p_integration_branch),'') is null then raise exception 'integration branch required'; end if;
 if nullif(btrim(p_work_branch),'') is null then raise exception 'work branch required'; end if;
 select * into v_unit from public.factory_change_set_work_units where run_id=p_run_id for update;
 if not found then raise exception 'change-set work unit not found'; end if;
 select * into v_set from public.factory_change_sets where id=v_unit.change_set_id for update;
 if v_set.source_commit is null then
   update public.factory_change_sets set source_commit=p_source_commit,candidate_commit=p_source_commit,
     integration_branch=p_integration_branch,status='building',updated_at=now()
   where id=v_set.id;
   v_set.source_commit:=p_source_commit;v_set.candidate_commit:=p_source_commit;v_set.integration_branch:=p_integration_branch;
 elsif v_set.source_commit<>p_source_commit then
   raise exception 'change-set source commit mismatch';
 elsif v_set.integration_branch<>p_integration_branch then
   raise exception 'change-set integration branch mismatch';
 end if;
 -- V2 planning materializes source_commit before a candidate exists.
 -- Before the first worker branch, atomically promote immutable source
 -- to the candidate base, without allowing a null or unknown Git SHA.
 if v_set.candidate_commit is null then
   if v_set.source_commit is null or v_set.source_commit !~ '^[0-9a-f]{40}$'
      or p_source_commit is distinct from v_set.source_commit
      or v_set.status not in ('planned','building')
      or v_set.release_run_id is not null or v_set.lease_owner is not null
      or v_set.lease_expires_at is not null
      or v_unit.base_commit is not null or v_unit.output_commit is not null
      or v_unit.status not in ('queued','running','pending') then
      raise exception 'unsafe missing Change Set candidate base' using errcode='PT409';
   end if;
   update public.factory_change_sets
     set candidate_commit=v_set.source_commit,status='building',updated_at=now()
     where id=v_set.id and candidate_commit is null;
   if not found then raise exception 'Change Set candidate base CAS lost' using errcode='PT409'; end if;
   v_set.candidate_commit:=v_set.source_commit;
 end if;
 if v_set.candidate_commit !~ '^[0-9a-f]{40}$' then
   raise exception 'invalid Change Set candidate SHA' using errcode='PT409';
 end if;
 if v_unit.wave<>v_set.current_wave then raise exception 'work unit is not in current wave'; end if;
 update public.factory_change_set_work_units
 set base_commit=v_set.candidate_commit,branch_name=p_work_branch,status='running',updated_at=now()
 where id=v_unit.id;
 return jsonb_build_object('change_set_id',v_set.id,'work_unit_id',v_unit.id,'base_commit',v_set.candidate_commit,
   'source_commit',v_set.source_commit,'integration_branch',v_set.integration_branch,'wave',v_unit.wave);
end;
$function$
;

-- Exactly once, generation-fenced recovery for the real CRM V2 branch preflight.
-- Its former blocked run stays in the durable audit; no candidate is fabricated.
create or replace function public.factory_retry_v2_null_change_set_base_once(
    p_change_set_id uuid, p_run_id uuid, p_command_id uuid,
    p_actor_id uuid, p_expected_generation bigint,
    p_expected_version bigint, p_expected_sha text
) returns jsonb language plpgsql security invoker set search_path='' as $fn$
declare
    p public.factory_projects%rowtype;
    c public.factory_project_execution_controls%rowtype;
    j public.factory_journeys%rowtype;
    s public.factory_change_sets%rowtype;
    u public.factory_change_set_work_units%rowtype;
    r public.factory_runs%rowtype;
    t public.factory_tasks%rowtype;
    older jsonb;
    receipt jsonb;
begin
    if p_change_set_id is null or p_run_id is null or p_command_id is null
       or p_actor_id is null or p_expected_generation is null
       or p_expected_version is null or p_expected_sha !~ '^[0-9a-f]{40}$'
    then raise exception 'invalid V2 branch recovery identity' using errcode='PT400'; end if;
    if not exists(select 1 from public.factory_console_operators o
        where o.user_id=p_actor_id and o.is_active=true and o.role='admin')
    then raise exception 'V2 branch recovery requires active admin' using errcode='PT403'; end if;

    select * into p from public.factory_projects
      where project_key='crm-infodive' and is_active=true
        and project_kind='existing'
        and repository='leandrosilveiradepaula/crm-infodive' for update;
    if p.id is null then raise exception 'CRM project not active' using errcode='PT409'; end if;

    select a.payload into older from public.factory_audit_events a
      where a.project_id=p.id and a.event_type='journey.v2.null_candidate_base_requeued'
        and a.payload->>'command_id'=p_command_id::text
      order by a.id desc limit 1;
    if older is not null then
      if older->>'change_set_id' is distinct from p_change_set_id::text
         or older->>'run_id' is distinct from p_run_id::text
         or older->>'actor_id' is distinct from p_actor_id::text
         or older->>'generation' is distinct from p_expected_generation::text
         or older->>'version' is distinct from p_expected_version::text
         or older->>'source_sha' is distinct from p_expected_sha
      then raise exception 'V2 branch recovery replay mismatch' using errcode='PT409'; end if;
      return older->'receipt';
    end if;

    select * into c from public.factory_project_execution_controls
      where project_id=p.id for update;
    select * into s from public.factory_change_sets
      where id=p_change_set_id and project_id=p.id for update;
    select * into j from public.factory_journeys
      where id=s.journey_id and project_id=p.id for update;
    select * into u from public.factory_change_set_work_units
      where change_set_id=s.id for update;
    select * into r from public.factory_runs where id=p_run_id for update;
    select * into t from public.factory_tasks where id=u.task_id for update;

    if c.state is distinct from 'running'
       or c.generation is distinct from p_expected_generation
       or c.version is distinct from p_expected_version
       or s.id is null or s.status is distinct from 'blocked'
       or s.current_wave is distinct from 1
       or s.source_commit is distinct from p_expected_sha
       or s.candidate_commit is not null
       or s.integration_branch is distinct from j.binding->>'integration_branch'
       or s.metadata#>>'{blocker,type}' is distinct from 'implementation_preflight_error'
       or s.metadata#>>'{blocker,reason}' is distinct from
            'GitHubRequestError: GitHub request failed with HTTP 404'
       or s.metadata#>>'{blocker,run_id}' is distinct from p_run_id::text
       or s.lease_owner is not null or s.lease_expires_at is not null
       or s.release_run_id is not null
       or j.id is null or j.state is distinct from 'executing'
       or j.execution_generation is distinct from p_expected_generation
       or j.source_commit is distinct from p_expected_sha
       or j.binding->>'source_commit' is distinct from p_expected_sha
       or j.binding->>'execution_generation' is distinct from c.generation::text
       or j.project_policy_version is distinct from 4
       or j.policy_digest is distinct from p.manifest#>>'{journey_delivery_binding_v2,digest}'
       or j.request_snapshot->>'text' not like '%issue #209%'
       or j.request_snapshot->>'text' not like '%leandrosilveiradepaula/crm-infodive%'
       or j.candidate_commit is not null
       or j.work_unit_output_commit is not null
       or j.preview_merge_sha is not null or j.production_release_sha is not null
       or u.id is null or u.status is distinct from 'blocked'
       or u.run_id is distinct from r.id
       or u.base_commit is not null or u.output_commit is not null
       or u.changed_files is distinct from '[]'::jsonb
       or u.branch_name is distinct from
          'factory/cs-'||substr(p_change_set_id::text,1,8)||'/issue209-contracts-isolated-read'
       or s.metadata#>>'{blocker,work_unit_id}' is distinct from u.id::text
       or r.id is null or r.status is distinct from 'blocked'
       or r.task_id is distinct from t.id
       or r.execution_route is distinct from 'direct'
       or r.source_commit is distinct from p_expected_sha
       or r.candidate_commit is not null
       or r.metadata->>'blocker_type' is distinct from 'implementation_preflight_error'
       or r.metadata->>'blocker_reason' is distinct from
            'GitHubRequestError: GitHub request failed with HTTP 404'
       or r.metadata->'journey_binding_v2' is distinct from j.binding
       or r.metadata->>'execution_generation' is distinct from c.generation::text
       or r.lease_owner is not null or r.lease_expires_at is not null
       or t.id is null or t.status is distinct from 'blocked'
       or t.journey_id is distinct from j.id or t.project_id is distinct from p.id
       or t.parent_task_id is null
       or not public.factory_control_quiescent(p.id)
    then raise exception 'V2 branch recovery state/binding unsafe' using errcode='PT409'; end if;

    if (select count(*) from public.factory_change_set_work_units w where w.change_set_id=s.id)<>1
       or exists(select 1 from public.factory_runs x join public.factory_tasks xt on xt.id=x.task_id
           where xt.project_id=p.id and x.status in ('created','queued','running'))
       or exists(select 1 from public.factory_deployments d where d.run_id=r.id)
       or exists(select 1 from public.factory_human_gates g where g.run_id=r.id)
       or exists(select 1 from public.factory_release_reports rr where rr.run_id=r.id)
       or exists(select 1 from public.factory_evaluations ev where ev.run_id=r.id)
       or exists(select 1 from public.factory_audit_events a
           where a.project_id=p.id
             and a.event_type='journey.v2.null_candidate_base_requeued'
             and a.payload->>'change_set_id'=s.id::text)
       or exists(select 1 from public.factory_audit_events a
           where a.run_id=r.id and a.event_type='change_set.work_unit.completed')
    then raise exception 'V2 branch recovery already advanced' using errcode='PT409'; end if;

    -- No new run or new journey. Resume the original work identity once,
    -- with a strictly frozen source as the first (and only) candidate base.
    update public.factory_change_sets
       set candidate_commit=source_commit,status='building',updated_at=now(),
           metadata=(metadata-'blocker') ||
              jsonb_build_object('null_candidate_base_recovery',
                  jsonb_build_object('run_id',r.id,'command_id',p_command_id,
                     'source_sha',p_expected_sha,'previous_error',
                     'GitHubRequestError: GitHub request failed with HTTP 404'))
       where id=s.id and status='blocked' and candidate_commit is null;
    if not found then raise exception 'V2 branch recovery Change Set CAS lost' using errcode='PT409'; end if;
    update public.factory_change_set_work_units
       set status='queued',base_commit=null,updated_at=now()
       where id=u.id and status='blocked' and output_commit is null;
    if not found then raise exception 'V2 branch recovery unit CAS lost' using errcode='PT409'; end if;
    update public.factory_runs
       set status='queued',last_error=null,
           metadata=metadata-'blocker_type'-'blocker_reason'-'implementation_blocked' ||
              jsonb_build_object('branch_base_recovery_once',p_command_id::text)
       where id=r.id and status='blocked';
    if not found then raise exception 'V2 branch recovery run CAS lost' using errcode='PT409'; end if;
    update public.factory_tasks set status='queued_execution',updated_at=now()
       where id=t.id and status='blocked';
    if not found then raise exception 'V2 branch recovery task CAS lost' using errcode='PT409'; end if;

    receipt:=jsonb_build_object('status','requeued','created',true,
        'project_id',p.id,'journey_id',j.id,'change_set_id',s.id,
        'work_unit_id',u.id,'run_id',r.id,'source_commit',p_expected_sha,
        'generation',c.generation,'release_authorized',false,'paid_calls',0);
    insert into public.factory_audit_events(
        project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
    values(p.id,t.id,r.id,'human',p_actor_id::text,
        'journey.v2.null_candidate_base_requeued',
        jsonb_build_object('command_id',p_command_id,
            'change_set_id',s.id,'run_id',r.id,'actor_id',p_actor_id,
            'generation',p_expected_generation,'version',p_expected_version,
            'source_sha',p_expected_sha,'receipt',receipt));
    return receipt;
end $fn$;

revoke all on function public.factory_retry_v2_null_change_set_base_once(
 uuid,uuid,uuid,uuid,bigint,bigint,text) from public,anon,authenticated;
grant execute on function public.factory_retry_v2_null_change_set_base_once(
 uuid,uuid,uuid,uuid,bigint,bigint,text) to service_role;


commit;
