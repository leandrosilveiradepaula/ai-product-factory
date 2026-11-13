-- One-time, exact-identity, fail-closed recovery for a legitimate greenfield
-- first-wave context-discovery preflight blocked on a README-only repository.
-- Migration installation DOES NOT execute recovery. Production application is
-- a separate human gate. No release, model call, cross-repo write or merge.
begin;

create or replace function public.factory_resume_greenfield_foundation_context_once(
    p_run_id uuid,
    p_change_set_id uuid,
    p_work_unit_id uuid,
    p_expected_source_sha text,
    p_expected_generation bigint,
    p_reason text
) returns jsonb
language plpgsql
security invoker
set search_path = ''
as $function$
declare
    v_project public.factory_projects%rowtype;
    v_control public.factory_project_execution_controls%rowtype;
    v_set public.factory_change_sets%rowtype;
    v_unit public.factory_change_set_work_units%rowtype;
    v_run public.factory_runs%rowtype;
    v_task public.factory_tasks%rowtype;
    v_recovery_key constant text := 'greenfield_first_wave_context_once_v1';
    v_blocker constant text :=
        'RuntimeError: repository context discovery found no relevant files; replan with explicit context_paths';
begin
    if p_run_id is null or p_change_set_id is null or p_work_unit_id is null
       or p_expected_source_sha is null
       or p_expected_source_sha !~ '^[0-9a-f]{40}$'
       or p_expected_generation is null or p_expected_generation < 1
       or nullif(btrim(p_reason), '') is null or length(p_reason) > 500
    then
        raise exception 'invalid greenfield recovery identity' using errcode='PT400';
    end if;

    -- Project lock serializes this recovery against Stop/Pause and other
    -- project commands; no privilege is inferred from the supplied IDs.
    select p.* into v_project
    from public.factory_projects p
    join public.factory_change_sets s on s.project_id=p.id
    where s.id=p_change_set_id and p.is_active=true
      and p.project_kind='greenfield'
      and p.manifest->>'source'='factory-console'
    for update of p;
    if v_project.id is null then
        raise exception 'greenfield project unavailable' using errcode='PT409';
    end if;
    select * into v_control
    from public.factory_project_execution_controls
    where project_id=v_project.id for share;
    select * into v_set
    from public.factory_change_sets
    where id=p_change_set_id and project_id=v_project.id for update;
    select * into v_unit
    from public.factory_change_set_work_units
    where id=p_work_unit_id and change_set_id=p_change_set_id for update;
    select * into v_run
    from public.factory_runs
    where id=p_run_id and task_id=v_unit.task_id for update;
    select * into v_task
    from public.factory_tasks
    where id=v_unit.task_id and project_id=v_project.id for update;

    -- A second invocation may report its recorded result but never requeue.
    if v_run.metadata->>'greenfield_context_recovery' = v_recovery_key then
        return jsonb_build_object(
            'requeued',false,'status',v_run.status,'run_id',v_run.id,
            'change_set_id',v_set.id,'release_authorized',false
        );
    end if;
    if v_control.project_id is null or v_set.id is null or v_unit.id is null
       or v_run.id is null or v_task.id is null
       or v_control.state is distinct from 'running'
       or v_control.generation is distinct from p_expected_generation
       or v_set.status is distinct from 'blocked'
       or v_set.current_wave is distinct from 1
       or v_set.source_commit is distinct from p_expected_source_sha
       or v_set.candidate_commit is distinct from p_expected_source_sha
       or v_set.release_run_id is not null
       or v_set.journey_id is not null
       or v_set.lease_owner is not null or v_set.lease_expires_at is not null
       or v_set.metadata->'blocker'->>'type' is distinct from 'implementation_preflight_error'
       or v_set.metadata->'blocker'->>'reason' is distinct from v_blocker
       or v_set.metadata->'blocker'->>'run_id' is distinct from p_run_id::text
       or v_set.metadata->'blocker'->>'work_unit_id' is distinct from p_work_unit_id::text
       or v_unit.status is distinct from 'blocked'
       or v_unit.wave is distinct from 1
       or v_unit.plan_task_key is distinct from 'app-foundation'
       or v_unit.run_id is distinct from p_run_id
       or v_unit.base_commit is distinct from p_expected_source_sha
       or v_unit.output_commit is not null
       or v_run.status is distinct from 'blocked'
       or v_run.execution_route is distinct from 'direct'
       or v_run.source_commit is distinct from p_expected_source_sha
       or v_run.candidate_commit is not null
       or v_run.attempt_count is distinct from 1
       or v_run.lease_owner is not null or v_run.lease_expires_at is not null
       or v_run.metadata->>'execution_generation' is distinct from p_expected_generation::text
       or v_run.last_error is distinct from v_blocker
       or v_task.status is distinct from 'blocked'
       or v_task.scope_keys is distinct from
          '["application-foundation","domain-contracts","test-harness"]'::jsonb
       or (select count(*) from public.factory_change_set_work_units
           where change_set_id=p_change_set_id) <> 1
       or (select count(*) from public.factory_runs
           where task_id=v_task.id and status in
           ('queued','queued_execution','running','implementing')) <> 0
    then
        raise exception 'greenfield context recovery preflight mismatch' using errcode='PT409';
    end if;

    update public.factory_runs set
        status='queued',last_error=null,
        metadata=metadata || jsonb_build_object(
            'greenfield_context_recovery',v_recovery_key,
            'greenfield_context_recovery_reason',p_reason,
            'greenfield_context_recovery_at',now()
        )
    where id=p_run_id;
    update public.factory_tasks
    set status='queued_execution',updated_at=now() where id=v_task.id;
    update public.factory_change_set_work_units
    set status='queued',updated_at=now() where id=v_unit.id;
    update public.factory_change_sets
    set status='building',updated_at=now(),
        metadata=(metadata-'blocker') || jsonb_build_object(
            'greenfield_context_recovery',
            jsonb_build_object('run_id',p_run_id,'source_sha',
              p_expected_source_sha,'generation',p_expected_generation,'at',now())
        )
    where id=v_set.id;
    insert into public.factory_audit_events(
        project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
    ) values(
        v_project.id,v_task.id,p_run_id,'system','greenfield-context-recovery',
        'change_set.greenfield_foundation_requeued',
        jsonb_build_object('change_set_id',v_set.id,'work_unit_id',v_unit.id,
            'source_sha',p_expected_source_sha,'generation',p_expected_generation,
            'reason',p_reason)
    );
    return jsonb_build_object(
        'requeued',true,'status','building','run_id',p_run_id,
        'change_set_id',v_set.id,'work_unit_id',v_unit.id,
        'release_authorized',false
    );
end;
$function$;

revoke all on function public.factory_resume_greenfield_foundation_context_once(
    uuid,uuid,uuid,text,bigint,text
) from public,anon,authenticated;
grant execute on function public.factory_resume_greenfield_foundation_context_once(
    uuid,uuid,uuid,text,bigint,text
) to service_role;
commit;
