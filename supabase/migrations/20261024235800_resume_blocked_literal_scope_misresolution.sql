-- Resume only a terminal, model-refused exact-file scope misresolution.
-- No direct Product Stage replay and no merge/release capability.
-- Apply to Control Plane only via a SEPARATE authorized production migration gate.
begin;
create or replace function public.factory_resume_blocked_literal_scope_misresolution_v1(
 p_max_items integer default 2
) returns jsonb
language plpgsql security invoker set search_path = '' as $factory$
declare
  v_row record;
  v_count integer := 0;
begin
  if p_max_items is null or p_max_items not between 1 and 3 then
    raise exception 'invalid bounded scope recovery request' using errcode='PT400';
  end if;
  for v_row in
    select cs.id as change_set_id, cs.project_id, u.id as unit_id,
      r.id as run_id, r.task_id, cs.source_commit as source_sha,
      c.generation as execution_generation, cp.packet_hash as old_packet_hash
    from public.factory_change_sets cs
    join public.factory_projects p
      on p.id=cs.project_id and p.is_active=true
      and p.project_kind='existing'
      and p.manifest#>>'{delivery_target,sha}'=cs.source_commit
      and p.manifest#>>'{delivery_target,repository}'=p.repository
      and p.manifest#>>'{delivery_target,branch}' like 'preview/%'
    join public.factory_project_execution_controls c
      on c.project_id=p.id and c.state='running' and c.generation>0
    join public.factory_change_set_work_units u
      on u.change_set_id=cs.id and u.status='blocked'
      and u.base_commit=cs.source_commit
      and u.output_commit is null
      and (u.changed_files is null or u.changed_files='[]'::jsonb)
      and u.wave=cs.current_wave
    join public.factory_runs r
      on r.id=u.run_id and r.task_id=u.task_id
      and r.status='blocked' and r.candidate_commit is null
      and r.lease_owner is null and r.lease_expires_at is null
      and r.attempt_count between 1 and 2
      and r.metadata->>'change_set_id'=cs.id::text
      and r.metadata->>'execution_generation'=c.generation::text
    join public.factory_tasks t
      on t.id=r.task_id and t.project_id=cs.project_id and t.status='blocked'
    join public.factory_work_unit_context_packets cp
      on cp.run_id=r.id and cp.work_unit_id=u.id
      and cp.change_set_id=cs.id and cp.project_id=cs.project_id
      and cp.version=1 and cp.packet->>'sha256'=cp.packet_hash
      and cp.packet#>>'{repository,exact_base_commit}'=cs.source_commit
      and cp.packet#>>'{repository,work_branch}'=u.branch_name
      and cp.packet#>>'{repository,repository}'=p.repository
      and cp.packet#>>'{repository,project_key}'=p.project_key
    where cs.status='blocked'
      and cs.source_commit~'^[a-f0-9]{40}$'
      and cs.candidate_commit=cs.source_commit
      and cs.release_run_id is null
      and cs.lease_owner is null and cs.lease_expires_at is null
      and cs.metadata#>>'{blocker,type}'='repository_governance'
      and cs.metadata#>>'{blocker,run_id}'=r.id::text
      and cs.metadata#>>'{blocker,work_unit_id}'=u.id::text
      and r.last_error=cs.metadata#>>'{blocker,reason}'
      and r.last_error like 'Blocked: the enforced repository.write_scopes permits only %'
      and r.last_error like '%it does not permit required files %'
      and jsonb_typeof(t.scope_keys)='array'
      and jsonb_array_length(t.scope_keys) between 1 and 10
      and jsonb_typeof(cp.packet#>'{repository,write_scopes}')='array'
      and jsonb_array_length(cp.packet#>'{repository,write_scopes}') between 1 and 20
      and exists (
        select 1 from jsonb_array_elements_text(t.scope_keys) requested(value)
        where not ((cp.packet#>'{repository,write_scopes}') ? requested.value)
      )
      and not exists (
        select 1 from jsonb_array_elements_text(t.scope_keys) requested(value)
        where requested.value !~ '^(src|app|apps|packages|tests|test|docs)/[A-Za-z0-9_./()\-]+\.(py|ts|tsx|js|jsx|md)$'
          or requested.value like '%..%' or requested.value like '%//%'
          or requested.value like '%/.%' or requested.value like '.%'
      )
      and (select count(*) from public.factory_change_set_work_units other
        where other.change_set_id=cs.id)=1
      and not exists (
        select 1 from public.factory_audit_events ae
        where ae.run_id=r.id
          and ae.event_type='change_set.literal_scope_requeued'
      )
    order by cs.created_at, cs.id
    limit p_max_items
    for update of cs, p, c, u, r, t, cp skip locked
  loop
    -- The prior malformed context and provenance remain visible through the
    -- audit. New code will re-check actual repository paths before a model.
    update public.factory_runs
      set status='queued',last_error=null,
        metadata=(metadata-'blocker_type'-'blocker_reason'-'implementation_blocked')
          ||jsonb_build_object('literal_scope_recovery',
             jsonb_build_object('previous_packet_hash',v_row.old_packet_hash,
               'execution_generation',v_row.execution_generation,'requeued_at',now()))
      where id=v_row.run_id and status='blocked' and lease_owner is null;
    if not found then raise exception 'scope recovery source moved' using errcode='PT409'; end if;
    update public.factory_tasks set status='queued_execution',updated_at=now()
      where id=v_row.task_id and status='blocked';
    if not found then raise exception 'scope recovery task moved' using errcode='PT409'; end if;
    update public.factory_change_set_work_units set status='queued',updated_at=now()
      where id=v_row.unit_id and status='blocked' and output_commit is null;
    if not found then raise exception 'scope recovery unit moved' using errcode='PT409'; end if;
    update public.factory_change_sets
      set status='building',lease_owner=null,lease_expires_at=null,updated_at=now(),
        metadata=(metadata-'blocker')||jsonb_build_object(
          'last_literal_scope_recovery',jsonb_build_object(
             'run_id',v_row.run_id,'work_unit_id',v_row.unit_id,
             'previous_packet_hash',v_row.old_packet_hash,'at',now()))
      where id=v_row.change_set_id and status='blocked';
    if not found then raise exception 'scope recovery change set moved' using errcode='PT409'; end if;
    insert into public.factory_audit_events(
      project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
    ) values (
      v_row.project_id,v_row.task_id,v_row.run_id,
      'system','literal-scope-recovery','change_set.literal_scope_requeued',
      jsonb_build_object(
       'change_set_id',v_row.change_set_id,'work_unit_id',v_row.unit_id,
       'source_sha',v_row.source_sha,'previous_packet_hash',v_row.old_packet_hash,
       'execution_generation',v_row.execution_generation,
       'product_stage_replayed',false,'release_authorized',false,
       'model_calls_in_recovery',0)
    );
    v_count:=v_count+1;
  end loop;
  return jsonb_build_object(
    'status',case when v_count>0 then 'requeued' else 'idle' end,
    'requeued',v_count,'max_items',p_max_items,
    'product_stage_replayed',false,
    'release_authorized',false,'paid_model_calls',0
  );
end;
$factory$;
revoke all on function public.factory_resume_blocked_literal_scope_misresolution_v1(integer)
 from public,anon,authenticated;
grant execute on function public.factory_resume_blocked_literal_scope_misresolution_v1(integer)
 to service_role;
commit;
