-- Resume only a previously verified CI repair work unit blocked by applying
-- imported-project repin proof to the already-integrated PR candidate SHA.
-- This migration is versioned only; it requires a separate human gate.
begin;
create or replace function public.factory_resume_blocked_ci_repair_candidate_v1(
  p_max_items integer default 2
) returns jsonb
language plpgsql security invoker set search_path='' as $factory$
declare
  v record;
  n integer:=0;
begin
  if p_max_items is null or p_max_items not between 1 and 2 then
    raise exception 'invalid bounded CI repair candidate recovery' using errcode='PT400';
  end if;
  for v in
    select rr.id as request_id,rr.project_id,rr.change_set_id,
      rr.source_run_id,rr.work_unit_id,rr.original_candidate_commit,
      rr.pr_number,rr.execution_generation,u.task_id,u.run_id,
      cs.source_commit as pinned_source_sha
    from public.factory_ci_repair_requests rr
    join public.factory_projects p
      on p.id=rr.project_id and p.is_active=true
      and p.project_kind='existing'
      and p.repository=rr.repository
      and p.manifest#>>'{delivery_target,repository}'=p.repository
      and p.manifest#>>'{delivery_target,sha}' ~ '^[a-f0-9]{40}$'
      and p.manifest#>>'{delivery_target,branch}' like 'preview/%'
      and p.manifest#>>'{delivery_target,mode}'='open_pr_candidate'
    join public.factory_project_execution_controls c
      on c.project_id=p.id and c.state='running'
      and c.generation=rr.execution_generation and c.generation>0
    join public.factory_change_sets cs
      on cs.id=rr.change_set_id and cs.project_id=p.id
      and cs.status='blocked' and cs.source_commit=p.manifest#>>'{delivery_target,sha}'
      and cs.candidate_commit=rr.original_candidate_commit
      and cs.integration_branch=rr.branch
      and cs.release_run_id is null
      and cs.lease_owner is null and cs.lease_expires_at is null
      and cs.current_wave=2
    join public.factory_change_set_work_units u
      on u.id=rr.work_unit_id and u.change_set_id=cs.id
      and u.status='blocked' and u.wave=cs.current_wave
      and u.base_commit=rr.original_candidate_commit
      and u.output_commit is null
      and (u.changed_files is null or u.changed_files='[]'::jsonb)
      and u.plan_task_key='ci-repair-1'
    join public.factory_tasks t
      on t.id=u.task_id and t.project_id=p.id and t.status='blocked'
      and t.scope_keys=rr.write_scopes
      and t.parent_task_id=cs.root_task_id
    join public.factory_runs r
      on r.id=u.run_id and r.task_id=t.id and r.status='blocked'
      and r.execution_route='direct' and r.attempt_count=1
      and r.candidate_commit is null and r.lease_owner is null
      and r.lease_expires_at is null
      and r.metadata->>'change_set_id'=cs.id::text
      and r.metadata->>'execution_generation'=c.generation::text
      and r.metadata->>'blocker_type'='implementation_preflight_error'
      and r.last_error='PermissionError: repin evidence does not match exact pinned source'
    join public.factory_runs src
      on src.id=rr.source_run_id and src.status='repair_pending'
      and src.candidate_commit=rr.original_candidate_commit
      and src.branch_name=rr.branch
      and src.metadata->>'change_set_id'=cs.id::text
      and src.metadata->>'ci_repair_request_id'=rr.id::text
    where rr.status='failed_gate'
      and rr.failure_class='code'
      and rr.attempt=1 and rr.max_attempts between 1 and 3
      and rr.original_candidate_commit ~ '^[a-f0-9]{40}$'
      and rr.lease_owner is null and rr.lease_expires_at is null
      and jsonb_typeof(rr.write_scopes)='array'
      and jsonb_array_length(rr.write_scopes) between 1 and 20
      and jsonb_typeof(rr.failures)='array'
      and jsonb_array_length(rr.failures) between 1 and 20
      and not exists (
        select 1 from jsonb_array_elements(rr.failures) f(value)
        where f.value->>'name' is distinct from 'native-ci/typescript'
          or f.value->>'failure_class' is distinct from 'code'
      )
      and rr.blocker_reason like '%repin evidence does not match exact pinned source%'
      and cs.metadata#>>'{blocker,type}'='implementation_preflight_error'
      and cs.metadata#>>'{blocker,run_id}'=r.id::text
      and cs.metadata#>>'{blocker,work_unit_id}'=u.id::text
      and cs.metadata#>>'{blocker,reason}'=r.last_error
      and cs.metadata#>>'{integration_release_request,pr_number}'=rr.pr_number::text
      and cs.metadata#>>'{integration_release_request,candidate_commit}'=rr.original_candidate_commit
      and (select count(*) from public.factory_change_set_work_units wu
           where wu.change_set_id=cs.id)=2
      and exists (
        select 1 from public.factory_change_set_work_units original
        where original.change_set_id=cs.id and original.id<>u.id
          and original.status='integrated' and original.wave=1
          and original.output_commit is not null
      )
      and not exists (
        select 1 from public.factory_audit_events ae
        where ae.run_id=r.id
          and ae.event_type='change_set.ci_repair_candidate_requeued'
      )
    order by rr.created_at,rr.id
    limit p_max_items
    for update of rr,p,c,cs,u,t,r,src skip locked
  loop
    update public.factory_ci_repair_requests
      set status='queued',blocker_reason=null,updated_at=now(),
        lease_owner=null,lease_expires_at=null
      where id=v.request_id and status='failed_gate';
    if not found then raise exception 'CI repair request moved' using errcode='PT409'; end if;
    update public.factory_runs set
      status='queued',last_error=null,
      metadata=(metadata-'blocker_type'-'blocker_reason'-'implementation_blocked')
        ||jsonb_build_object('ci_candidate_context_recovery',jsonb_build_object(
          'repair_request_id',v.request_id,
          'candidate_sha',v.original_candidate_commit,
          'execution_generation',v.execution_generation,
          'at',now()))
      where id=v.run_id and status='blocked' and lease_owner is null;
    if not found then raise exception 'CI repair run moved' using errcode='PT409'; end if;
    update public.factory_tasks set status='queued_execution',updated_at=now()
      where id=v.task_id and status='blocked';
    if not found then raise exception 'CI repair task moved' using errcode='PT409'; end if;
    update public.factory_change_set_work_units set status='queued',updated_at=now()
      where id=v.work_unit_id and status='blocked' and output_commit is null;
    if not found then raise exception 'CI repair Work Unit moved' using errcode='PT409'; end if;
    update public.factory_change_sets set
      status='building',updated_at=now(),
      metadata=(metadata-'blocker')||jsonb_build_object(
        'last_ci_repair_candidate_recovery',jsonb_build_object(
          'repair_request_id',v.request_id,'work_unit_id',v.work_unit_id,
          'candidate_sha',v.original_candidate_commit,'at',now()))
      where id=v.change_set_id and status='blocked';
    if not found then raise exception 'CI repair Change Set moved' using errcode='PT409'; end if;
    insert into public.factory_audit_events(
      project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
    ) values (
      v.project_id,v.task_id,v.run_id,'system','ci-repair-candidate-recovery',
      'change_set.ci_repair_candidate_requeued',
      jsonb_build_object(
        'repair_request_id',v.request_id,'change_set_id',v.change_set_id,
        'work_unit_id',v.work_unit_id,'source_run_id',v.source_run_id,
        'pinned_source_sha',v.pinned_source_sha,
        'candidate_commit',v.original_candidate_commit,
        'pr_number',v.pr_number,'execution_generation',v.execution_generation,
        'ci_repair_attempt',1,'product_stage_replayed',false,
        'release_authorized',false,'paid_model_calls',0)
    );
    n:=n+1;
  end loop;
  return jsonb_build_object(
    'status',case when n>0 then 'requeued' else 'idle' end,
    'requeued',n,'max_items',p_max_items,
    'product_stage_replayed',false,'release_authorized',false,
    'paid_model_calls',0
  );
end;
$factory$;
revoke all on function public.factory_resume_blocked_ci_repair_candidate_v1(integer)
  from public,anon,authenticated;
grant execute on function public.factory_resume_blocked_ci_repair_candidate_v1(integer)
  to service_role;
commit;
