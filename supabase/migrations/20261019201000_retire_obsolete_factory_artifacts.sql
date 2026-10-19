-- Factory maintenance: retire proven obsolete work without deleting evidence.
-- No data rewrite is performed by this migration. Execution requires a separate
-- exact project/pin/request/UUID allowlist via service_role-only RPC.
-- Superseding changes terminal status; runs, Work Units, commits, audits, cost
-- and production branches remain intact.
create or replace function public.factory_retire_obsolete_artifacts_v1(
  p_project_key text,
  p_expected_pin text,
  p_change_set_ids uuid[],
  p_task_ids uuid[],
  p_request_id uuid,
  p_reason text
) returns jsonb
language plpgsql
security invoker
set search_path to ''
as $function$
declare
 v_project public.factory_projects%rowtype;
 v_control public.factory_project_execution_controls%rowtype;
 v_set public.factory_change_sets%rowtype;
 v_task public.factory_tasks%rowtype;
 v_id uuid;
 v_now timestamptz:=now();
 v_sets uuid[]:=coalesce(p_change_set_ids,'{}'::uuid[]);
 v_tasks uuid[]:=coalesce(p_task_ids,'{}'::uuid[]);
 v_pin text;
 v_target_status text;
 v_old_status text;
 v_cs_done integer:=0;
 v_task_completed integer:=0;
 v_task_cancelled integer:=0;
 v_receipt jsonb;
 v_prior jsonb;
begin
 if p_project_key is null or btrim(p_project_key)='' or length(p_project_key)>150
    or p_request_id is null or p_reason is null or length(btrim(p_reason))<12
    or length(p_reason)>500 or p_expected_pin is null then
   raise exception 'invalid archival request' using errcode='PT400';
 end if;
 if cardinality(v_sets)>15 or cardinality(v_tasks)>25
    or cardinality(v_sets)+cardinality(v_tasks)=0
    or array_position(v_sets,null) is not null or array_position(v_tasks,null) is not null
    or (select count(distinct x.item_id) from unnest(v_sets) as x(item_id))<>cardinality(v_sets)
    or (select count(distinct x.item_id) from unnest(v_tasks) as x(item_id))<>cardinality(v_tasks) then
   raise exception 'invalid or duplicate archival IDs' using errcode='PT400';
 end if;
 select * into v_project from public.factory_projects
 where project_key=p_project_key and is_active=true for update;
 if not found then raise exception 'unknown or inactive project' using errcode='PT404'; end if;
 select * into v_control from public.factory_project_execution_controls
 where project_id=v_project.id for update;
 if not found or v_control.state<>'running' or v_control.generation<1 then
   raise exception 'project not running' using errcode='PT409';
 end if;
 v_pin:=v_project.manifest->'delivery_target'->>'sha';
 if v_project.project_kind='existing' then
   if p_expected_pin !~ '^[0-9a-f]{40}$'
      or v_pin is distinct from p_expected_pin
      or v_project.manifest->'delivery_target'->>'mode' is distinct from 'open_pr_candidate'
      or coalesce(v_project.manifest->'delivery_target'->>'branch','') not like 'preview/%'
      or v_project.manifest->'delivery_target'->>'repository' is distinct from v_project.repository then
     raise exception 'pinned candidate changed' using errcode='PT409';
   end if;
 elsif v_project.project_kind='platform' then
   if p_expected_pin<>'platform:no-pinned-candidate' or v_pin is not null
      or cardinality(v_sets)>0 then
     raise exception 'platform archival requires task-only explicit scope' using errcode='PT409';
   end if;
 else raise exception 'unsupported project kind for archival' using errcode='PT409'; end if;
 if public.factory_control_quiescent(v_project.id) is distinct from true then
   raise exception 'project has active worker leases' using errcode='PT409';
 end if;

 -- A duplicate request is safe only when the input is byte-for-byte the same.
 select payload into v_prior from public.factory_audit_events
 where project_id=v_project.id and event_type='project.obsolete_artifacts.retired'
   and payload->>'request_id'=p_request_id::text
 order by created_at desc limit 1;
 if found then
   if v_prior->>'project_key' is distinct from p_project_key
      or v_prior->>'expected_pin' is distinct from p_expected_pin
      or v_prior->>'reason' is distinct from p_reason
      or v_prior->'change_set_ids' is distinct from to_jsonb(v_sets)
      or v_prior->'task_ids' is distinct from to_jsonb(v_tasks) then
     raise exception 'retirement request ID reused' using errcode='PT409';
   end if;
   return v_prior->'receipt';
 end if;

 -- Verify BEFORE mutation; any failure rolls the entire function back.
 for v_id in select id from unnest(v_sets) id order by id loop
   select * into v_set from public.factory_change_sets
   where id=v_id and project_id=v_project.id for update;
   if not found or v_set.lease_owner is not null
      or v_set.lease_expires_at is not null
      or v_set.release_run_id is not null
      or v_set.status not in ('building','review_ready') then
     raise exception 'Change Set not safely retireable: %',v_id using errcode='PT409';
   end if;
   if not exists(select 1 from public.factory_tasks t
      where t.id=v_set.root_task_id and t.project_id=v_project.id
        and t.status='completed') then
     raise exception 'Change Set root unfinished: %',v_id using errcode='PT409';
   end if;
   if v_set.status='building' then
     if v_project.project_kind<>'existing' or v_set.source_commit is null
        or v_set.source_commit=p_expected_pin
        or not exists(select 1 from public.factory_change_set_work_units u
                      where u.change_set_id=v_id and u.wave=v_set.current_wave)
        or exists(select 1 from public.factory_change_set_work_units u
                  where u.change_set_id=v_id and u.status<>'completed') then
       raise exception 'Change Set still current or unfinished: %',v_id using errcode='PT409';
     end if;
   else
     if v_set.source_commit is not null or v_set.candidate_commit is not null
        or exists(select 1 from public.factory_change_set_work_units u
                  where u.change_set_id=v_id)
        or not exists(select 1 from public.factory_change_sets newer
                      join public.factory_change_set_work_units wu on wu.change_set_id=newer.id
                      where newer.project_id=v_project.id
                        and newer.created_at>v_set.created_at
                        and wu.status in ('completed','integrated')) then
       raise exception 'review-ready Change Set may still contain work: %',v_id
          using errcode='PT409';
     end if;
   end if;
   if exists(select 1 from public.factory_runs r
      join public.factory_tasks t on t.id=r.task_id
      join public.factory_change_set_work_units u on u.task_id=t.id
      where u.change_set_id=v_id and r.status not in
      ('completed','failed','cancelled','blocked','integrated','merged','preview_ready')) then
     raise exception 'Change Set has active descendant run: %',v_id using errcode='PT409';
   end if;
 end loop;

 for v_id in select id from unnest(v_tasks) id order by id loop
   select * into v_task from public.factory_tasks
   where id=v_id and project_id=v_project.id for update;
   if not found or v_task.status<>'queued'
      or v_task.created_at>v_now-interval '7 days'
      or v_task.parent_task_id is null
      or not exists(select 1 from public.factory_tasks parent
                    where parent.id=v_task.parent_task_id and parent.status='completed')
      or not exists(select 1 from public.factory_tasks newer
                    where newer.project_id=v_project.id
                      and newer.created_at>v_task.created_at
                      and newer.status in ('completed','integrated')) then
     raise exception 'legacy task not safely obsolete: %',v_id using errcode='PT409';
   end if;
   if exists(select 1 from public.factory_runs r where r.task_id=v_id
     and r.status not in ('completed','failed','cancelled','blocked','integrated','merged','preview_ready'))
      or exists(select 1 from public.factory_human_gates g
                join public.factory_runs r on r.id=g.run_id
                where r.task_id=v_id and g.status='pending')
      or exists(select 1 from public.factory_tasks child where child.parent_task_id=v_id
                and child.status not in ('completed','cancelled','integrated'))
      or exists(select 1 from public.factory_change_set_work_units wu
                join public.factory_change_sets cs on cs.id=wu.change_set_id
                where wu.task_id=v_id and cs.status not in
                  ('completed','superseded','blocked')) then
     raise exception 'legacy task has active work: %',v_id using errcode='PT409';
   end if;
 end loop;

 -- Every update is CAS-guarded and independently auditable; no DELETE.
 for v_id in select id from unnest(v_sets) id order by id loop
   select * into v_set from public.factory_change_sets
    where id=v_id and project_id=v_project.id for update;
   update public.factory_change_sets set status='superseded',
      lease_owner=null,lease_expires_at=null,updated_at=v_now,
      metadata=coalesce(metadata,'{}'::jsonb)||jsonb_build_object(
        'retirement',jsonb_build_object(
          'reason',p_reason,'request_id',p_request_id,'retired_at',v_now,
          'previous_status',v_set.status,'previous_source_commit',v_set.source_commit,
          'current_pinned_commit',v_pin))
    where id=v_id and status=v_set.status;
   if not found then raise exception 'Change Set retirement race' using errcode='PT409'; end if;
   insert into public.factory_audit_events
      (project_id,task_id,actor_type,actor_ref,event_type,payload)
   values(v_project.id,v_set.root_task_id,'system','audited-obsolete-artifact-retirement',
          'change_set.retired_obsolete',
          jsonb_build_object('request_id',p_request_id,'change_set_id',v_id,
            'previous_status',v_set.status,'status','superseded','reason',p_reason,
            'source_commit',v_set.source_commit,'current_pinned_commit',v_pin));
   v_cs_done:=v_cs_done+1;
 end loop;

 for v_id in select id from unnest(v_tasks) id order by id loop
   select * into v_task from public.factory_tasks
   where id=v_id and project_id=v_project.id for update;
   v_target_status:=case when exists(
      select 1 from public.factory_runs r where r.task_id=v_id and r.status='completed'
   ) then 'completed' else 'cancelled' end;
   v_old_status:=v_task.status;
   update public.factory_tasks
   set status=v_target_status,updated_at=v_now
   where id=v_id and status='queued';
   if not found then raise exception 'task retirement race' using errcode='PT409'; end if;
   insert into public.factory_audit_events
      (project_id,task_id,actor_type,actor_ref,event_type,payload)
   values(v_project.id,v_id,'system','audited-obsolete-artifact-retirement',
          'task.retired_obsolete',
          jsonb_build_object('request_id',p_request_id,
            'previous_status',v_old_status,'status',v_target_status,'reason',p_reason));
   if v_target_status='completed' then v_task_completed:=v_task_completed+1;
   else v_task_cancelled:=v_task_cancelled+1; end if;
 end loop;
 v_receipt:=jsonb_build_object(
   'project_key',p_project_key,'change_sets_superseded',v_cs_done,
   'tasks_completed',v_task_completed,'tasks_cancelled',v_task_cancelled,
   'request_id',p_request_id,'expected_pin',p_expected_pin,'reason',p_reason);
 insert into public.factory_audit_events(
    project_id,actor_type,actor_ref,event_type,payload)
 values(v_project.id,'system','audited-obsolete-artifact-retirement',
   'project.obsolete_artifacts.retired',
   jsonb_build_object('request_id',p_request_id,'project_key',p_project_key,
     'expected_pin',p_expected_pin,'reason',p_reason,
     'change_set_ids',to_jsonb(v_sets),'task_ids',to_jsonb(v_tasks),
     'receipt',v_receipt));
 return v_receipt;
end;
$function$;

revoke all on function public.factory_retire_obsolete_artifacts_v1(
 text,text,uuid[],uuid[],uuid,text) from public,anon,authenticated;
grant execute on function public.factory_retire_obsolete_artifacts_v1(
 text,text,uuid[],uuid[],uuid,text) to service_role;
