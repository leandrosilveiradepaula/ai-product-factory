-- Restore a single Direct attempt blocked only because the producer lacked proof
-- of an already audited exact-native-CI candidate repin.
-- Versioned but NEVER applied by GitHub Actions or migration discovery.
begin;

create or replace function public.factory_resume_blocked_repin_context_v1(
  p_max_items integer default 2
) returns jsonb
language plpgsql security invoker set search_path = '' as $factory$
declare
  v_row record;
  v_count integer := 0;
begin
  if p_max_items is null or p_max_items not between 1 and 2 then
    raise exception 'invalid bounded repin context recovery'
      using errcode='PT400';
  end if;

  for v_row in
    select
      cs.id as change_set_id, cs.project_id, cs.root_task_id,
      u.id as work_unit_id, r.id as run_id, r.task_id,
      cs.source_commit as source_sha,
      control.generation as execution_generation,
      cp.packet_hash as context_hash,
      proof.id as repin_audit_event_id,
      (proof.payload->>'ci_run_id')::bigint as native_ci_run_id
    from public.factory_change_sets cs
    join public.factory_projects project
      on project.id=cs.project_id
     and project.is_active=true and project.project_kind='existing'
     and project.repository=project.manifest#>>'{delivery_target,repository}'
     and project.manifest#>>'{delivery_target,sha}'=cs.source_commit
     and project.manifest#>>'{delivery_target,branch}' like 'preview/%'
     and project.manifest#>>'{delivery_target,mode}'='open_pr_candidate'
     and project.manifest#>>'{delivery_target,repin_policy,enabled}'='true'
    join public.factory_project_execution_controls control
      on control.project_id=project.id
     and control.state='running' and control.generation>0
    join public.factory_tasks root_task
      on root_task.id=cs.root_task_id
     and root_task.project_id=project.id
     and root_task.status='completed'
    join public.factory_change_set_work_units u
      on u.change_set_id=cs.id
     and u.status='blocked'
     and u.base_commit=cs.source_commit
     and u.output_commit is null
     and (u.changed_files is null or u.changed_files='[]'::jsonb)
     and u.wave=cs.current_wave
    join public.factory_runs r
      on r.id=u.run_id and r.task_id=u.task_id
     and r.status='blocked' and r.execution_route='direct'
     and r.candidate_commit is null
     and r.lease_owner is null and r.lease_expires_at is null
     and r.attempt_count=2
     and r.metadata->>'source'='change-set'
     and r.metadata->>'change_set_id'=cs.id::text
     and r.metadata->>'execution_generation'=control.generation::text
    join public.factory_tasks task
      on task.id=r.task_id
     and task.project_id=cs.project_id
     and task.status='blocked'
    join public.factory_work_unit_context_packets cp
      on cp.run_id=r.id
     and cp.work_unit_id=u.id
     and cp.change_set_id=cs.id and cp.project_id=cs.project_id
     and cp.version=1
     and cp.packet->>'sha256'=cp.packet_hash
     and cp.packet#>>'{repository,exact_base_commit}'=cs.source_commit
     and cp.packet#>>'{repository,repository}'=project.repository
     and cp.packet#>>'{repository,project_key}'=project.project_key
     and cp.packet#>>'{repository,work_branch}'=u.branch_name
     and cp.packet#>'{repository,write_scopes}'=task.scope_keys
     and cp.packet#>'{repository,delivery_repin_evidence}' is null
    join public.factory_audit_events proof
      on proof.project_id=project.id
     and proof.event_type='project.delivery_target.reconciled'
     and proof.actor_type='system'
     and proof.actor_ref='factory-candidate-reconciler'
     and proof.payload->>'source'='github_actions_exact_sha'
     and proof.payload->>'status'='updated'
     and proof.payload->>'repository'=project.repository
     and proof.payload->>'project_key'=project.project_key
     and proof.payload->>'branch'=project.manifest#>>'{delivery_target,branch}'
     and proof.payload->>'new_sha'=cs.source_commit
     and proof.payload->>'ci_sha'=cs.source_commit
     and proof.payload->>'pr_number'=project.manifest#>>'{delivery_target,candidate_pr_number}'
     and proof.payload->>'generation'=control.generation::text
     and proof.payload->>'version'=control.version::text
     and proof.payload->>'compare_status'='ahead'
     and proof.payload->>'ahead_by' ~ '^[1-9][0-9]*$'
     and proof.payload->>'behind_by'='0'
     and proof.payload->>'ci_run_id' ~ '^[1-9][0-9]*$'
     and proof.payload->>'old_sha' ~ '^[a-f0-9]{40}    where cs.status='blocked'
      and cs.candidate_commit=cs.source_commit
      and cs.source_commit ~ '^[a-f0-9]{40}$'
      and cs.release_run_id is null
      and cs.lease_owner is null and cs.lease_expires_at is null
      and cs.metadata#>>'{blocker,type}'='repository_governance'
      and cs.metadata#>>'{blocker,run_id}'=r.id::text
      and cs.metadata#>>'{blocker,work_unit_id}'=u.id::text
      and cs.metadata#>>'{blocker,reason}'=r.last_error
      and r.last_error like 'The active docs/codex/CURRENT_TASK.md authorizes implementation only from %'
      and r.last_error like '%or a successor explicitly repinned after exact % validation%'
      and r.last_error like '%with no explicit repin%'
      and r.last_error like '%so no files were changed.'
      and position(cs.source_commit in r.last_error)>0
      and position(proof.payload->>'old_sha' in r.last_error)>0
      and cs.metadata#>>'{last_literal_scope_recovery,run_id}'=r.id::text
      and cs.metadata#>>'{last_literal_scope_recovery,previous_packet_hash}'
            =r.metadata#>>'{literal_scope_recovery,previous_packet_hash}'
      and r.metadata#>>'{literal_scope_recovery,execution_generation}'
            =control.generation::text
      and exists (
        select 1 from public.factory_audit_events old_recovery
        where old_recovery.run_id=r.id
          and old_recovery.project_id=cs.project_id
          and old_recovery.event_type='change_set.literal_scope_requeued'
          and old_recovery.payload->>'change_set_id'=cs.id::text
          and old_recovery.payload->>'work_unit_id'=u.id::text
          and old_recovery.payload->>'previous_packet_hash'
                =r.metadata#>>'{literal_scope_recovery,previous_packet_hash}'
      )
      and (select count(*) from public.factory_change_set_work_units other
           where other.change_set_id=cs.id)=1
      and not exists (
        select 1 from public.factory_audit_events replay
        where replay.run_id=r.id
          and replay.event_type='change_set.repin_context_requeued'
      )
      and exists (
        select 1 from public.factory_runs root_run
        where root_run.task_id=cs.root_task_id
          and root_run.status='completed'
      )
    order by cs.created_at, cs.id, proof.id desc
    limit p_max_items
    for update of cs, project, control, root_task, u, r, task, cp skip locked
  loop
    update public.factory_runs set
      status='queued',last_error=null,
      metadata=(metadata-'blocker_type'-'blocker_reason'-'implementation_blocked')
       ||jsonb_build_object('repin_context_recovery',jsonb_build_object(
            'previous_context_hash',v_row.context_hash,
            'repin_audit_event_id',v_row.repin_audit_event_id,
            'native_ci_run_id',v_row.native_ci_run_id,
            'execution_generation',v_row.execution_generation,
            'requeued_at',now()))
    where id=v_row.run_id and status='blocked' and lease_owner is null;
    if not found then
      raise exception 'repin recovery run changed' using errcode='PT409';
    end if;
    update public.factory_tasks set status='queued_execution',updated_at=now()
    where id=v_row.task_id and status='blocked';
    if not found then
      raise exception 'repin recovery task changed' using errcode='PT409';
    end if;
    update public.factory_change_set_work_units set status='queued',updated_at=now()
    where id=v_row.work_unit_id and status='blocked' and output_commit is null;
    if not found then
      raise exception 'repin recovery unit changed' using errcode='PT409';
    end if;
    update public.factory_change_sets set
      status='building',updated_at=now(),
      metadata=(metadata-'blocker')||jsonb_build_object(
        'last_repin_context_recovery',jsonb_build_object(
          'run_id',v_row.run_id,'work_unit_id',v_row.work_unit_id,
          'previous_context_hash',v_row.context_hash,
          'repin_audit_event_id',v_row.repin_audit_event_id,
          'at',now()))
    where id=v_row.change_set_id and status='blocked';
    if not found then
      raise exception 'repin recovery change set changed' using errcode='PT409';
    end if;

    insert into public.factory_audit_events(
      project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
    ) values (
      v_row.project_id,v_row.task_id,v_row.run_id,
      'system','repin-context-recovery','change_set.repin_context_requeued',
      jsonb_build_object(
        'change_set_id',v_row.change_set_id,
        'work_unit_id',v_row.work_unit_id,
        'root_task_id',v_row.root_task_id,
        'source_sha',v_row.source_sha,
        'previous_context_hash',v_row.context_hash,
        'repin_audit_event_id',v_row.repin_audit_event_id,
        'native_ci_run_id',v_row.native_ci_run_id,
        'execution_generation',v_row.execution_generation,
        'product_stage_replayed',false,
        'release_authorized',false,
        'paid_model_calls',0)
    );
    v_count:=v_count+1;
  end loop;

  return jsonb_build_object(
    'status',case when v_count>0 then 'requeued' else 'idle' end,
    'requeued',v_count,'max_items',p_max_items,
    'product_stage_replayed',false,
    'release_authorized',false,
    'paid_model_calls',0);
end;
$factory$;

revoke all on function public.factory_resume_blocked_repin_context_v1(integer)
  from public,anon,authenticated;
grant execute on function public.factory_resume_blocked_repin_context_v1(integer)
  to service_role;
commit;

     and proof.id = (
       select max(latest.id) from public.factory_audit_events latest
       where latest.project_id=project.id
         and latest.event_type='project.delivery_target.reconciled'
         and latest.payload->>'new_sha'=cs.source_commit
         and latest.payload->>'generation'=control.generation::text
         and latest.payload->>'version'=control.version::text
     )
    where cs.status='blocked'
      and cs.candidate_commit=cs.source_commit
      and cs.source_commit ~ '^[a-f0-9]{40}$'
      and cs.release_run_id is null
      and cs.lease_owner is null and cs.lease_expires_at is null
      and cs.metadata#>>'{blocker,type}'='repository_governance'
      and cs.metadata#>>'{blocker,run_id}'=r.id::text
      and cs.metadata#>>'{blocker,work_unit_id}'=u.id::text
      and cs.metadata#>>'{blocker,reason}'=r.last_error
      and r.last_error like 'The active docs/codex/CURRENT_TASK.md authorizes implementation only from %'
      and r.last_error like '%or a successor explicitly repinned after exact % validation%'
      and r.last_error like '%with no explicit repin%'
      and r.last_error like '%so no files were changed.'
      and position(cs.source_commit in r.last_error)>0
      and position(proof.payload->>'old_sha' in r.last_error)>0
      and cs.metadata#>>'{last_literal_scope_recovery,run_id}'=r.id::text
      and cs.metadata#>>'{last_literal_scope_recovery,previous_packet_hash}'
            =r.metadata#>>'{literal_scope_recovery,previous_packet_hash}'
      and r.metadata#>>'{literal_scope_recovery,execution_generation}'
            =control.generation::text
      and exists (
        select 1 from public.factory_audit_events old_recovery
        where old_recovery.run_id=r.id
          and old_recovery.project_id=cs.project_id
          and old_recovery.event_type='change_set.literal_scope_requeued'
          and old_recovery.payload->>'change_set_id'=cs.id::text
          and old_recovery.payload->>'work_unit_id'=u.id::text
          and old_recovery.payload->>'previous_packet_hash'
                =r.metadata#>>'{literal_scope_recovery,previous_packet_hash}'
      )
      and (select count(*) from public.factory_change_set_work_units other
           where other.change_set_id=cs.id)=1
      and not exists (
        select 1 from public.factory_audit_events replay
        where replay.run_id=r.id
          and replay.event_type='change_set.repin_context_requeued'
      )
      and exists (
        select 1 from public.factory_runs root_run
        where root_run.task_id=cs.root_task_id
          and root_run.status='completed'
      )
    order by cs.created_at, cs.id, proof.id desc
    limit p_max_items
    for update of cs, project, control, root_task, u, r, task, cp skip locked
  loop
    update public.factory_runs set
      status='queued',last_error=null,
      metadata=(metadata-'blocker_type'-'blocker_reason'-'implementation_blocked')
       ||jsonb_build_object('repin_context_recovery',jsonb_build_object(
            'previous_context_hash',v_row.context_hash,
            'repin_audit_event_id',v_row.repin_audit_event_id,
            'native_ci_run_id',v_row.native_ci_run_id,
            'execution_generation',v_row.execution_generation,
            'requeued_at',now()))
    where id=v_row.run_id and status='blocked' and lease_owner is null;
    if not found then
      raise exception 'repin recovery run changed' using errcode='PT409';
    end if;
    update public.factory_tasks set status='queued_execution',updated_at=now()
    where id=v_row.task_id and status='blocked';
    if not found then
      raise exception 'repin recovery task changed' using errcode='PT409';
    end if;
    update public.factory_change_set_work_units set status='queued',updated_at=now()
    where id=v_row.work_unit_id and status='blocked' and output_commit is null;
    if not found then
      raise exception 'repin recovery unit changed' using errcode='PT409';
    end if;
    update public.factory_change_sets set
      status='building',updated_at=now(),
      metadata=(metadata-'blocker')||jsonb_build_object(
        'last_repin_context_recovery',jsonb_build_object(
          'run_id',v_row.run_id,'work_unit_id',v_row.work_unit_id,
          'previous_context_hash',v_row.context_hash,
          'repin_audit_event_id',v_row.repin_audit_event_id,
          'at',now()))
    where id=v_row.change_set_id and status='blocked';
    if not found then
      raise exception 'repin recovery change set changed' using errcode='PT409';
    end if;

    insert into public.factory_audit_events(
      project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
    ) values (
      v_row.project_id,v_row.task_id,v_row.run_id,
      'system','repin-context-recovery','change_set.repin_context_requeued',
      jsonb_build_object(
        'change_set_id',v_row.change_set_id,
        'work_unit_id',v_row.work_unit_id,
        'root_task_id',v_row.root_task_id,
        'source_sha',v_row.source_sha,
        'previous_context_hash',v_row.context_hash,
        'repin_audit_event_id',v_row.repin_audit_event_id,
        'native_ci_run_id',v_row.native_ci_run_id,
        'execution_generation',v_row.execution_generation,
        'product_stage_replayed',false,
        'release_authorized',false,
        'paid_model_calls',0)
    );
    v_count:=v_count+1;
  end loop;

  return jsonb_build_object(
    'status',case when v_count>0 then 'requeued' else 'idle' end,
    'requeued',v_count,'max_items',p_max_items,
    'product_stage_replayed',false,
    'release_authorized',false,
    'paid_model_calls',0);
end;
$factory$;

revoke all on function public.factory_resume_blocked_repin_context_v1(integer)
  from public,anon,authenticated;
grant execute on function public.factory_resume_blocked_repin_context_v1(integer)
  to service_role;
commit;
