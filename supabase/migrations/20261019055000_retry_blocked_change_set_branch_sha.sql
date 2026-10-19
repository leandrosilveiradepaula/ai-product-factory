-- Privileged, narrowly scoped recovery after the CRM work branch was fast-forwarded.
create or replace function public.factory_retry_blocked_change_set_branch_sha(
 p_change_set_id uuid, p_expected_sha text, p_branch text, p_reason text
) returns jsonb language plpgsql security invoker set search_path='' as $$
declare s public.factory_change_sets%rowtype; u public.factory_change_set_work_units%rowtype;
r public.factory_runs%rowtype; t public.factory_tasks%rowtype;
begin
 if p_expected_sha !~ '^[0-9a-f]{40}$' or nullif(btrim(p_branch),'') is null
 or nullif(btrim(p_reason),'') is null or length(p_reason)>1000 then
 raise exception 'invalid recovery arguments'; end if;
 select * into s from public.factory_change_sets where id=p_change_set_id for update;
 if not found or s.status<>'blocked' or s.source_commit is distinct from p_expected_sha
 or s.candidate_commit is distinct from p_expected_sha
 or s.metadata->'blocker'->>'type' is distinct from 'implementation_preflight_error'
 or s.metadata->'blocker'->>'reason' is distinct from
 ('RuntimeError: branch '||p_branch||' does not match expected candidate SHA')
 or s.lease_owner is not null or s.lease_expires_at is not null
 or s.release_run_id is not null then raise exception 'change set not eligible'; end if;
 if (select count(*) from public.factory_change_set_work_units where change_set_id=s.id)<>1
 then raise exception 'requires exactly one unit'; end if;
 select * into u from public.factory_change_set_work_units where change_set_id=s.id for update;
 if u.status<>'blocked' or u.base_commit is distinct from p_expected_sha
 or u.branch_name is distinct from p_branch or u.output_commit is not null
 or s.metadata->'blocker'->>'work_unit_id' is distinct from u.id::text
 or s.metadata->'blocker'->>'run_id' is distinct from u.run_id::text
 then raise exception 'unit not eligible'; end if;
 select * into r from public.factory_runs where id=u.run_id for update;
 select * into t from public.factory_tasks where id=u.task_id for update;
 if r.status<>'blocked' or t.status<>'blocked' or r.task_id is distinct from t.id
 or r.attempt_count>3 or r.lease_owner is not null or r.lease_expires_at is not null
 or r.candidate_commit is not null then raise exception 'run/task not eligible'; end if;
 if not exists(select 1 from public.factory_project_execution_controls
 where project_id=s.project_id and state='running') then raise exception 'project not running'; end if;
 update public.factory_runs set status='queued',last_error=null where id=r.id;
 update public.factory_tasks set status='queued_execution',updated_at=now() where id=t.id;
 update public.factory_change_set_work_units set status='queued',updated_at=now() where id=u.id;
 update public.factory_change_sets set status='building',updated_at=now(),
 metadata=(metadata-'blocker')||jsonb_build_object('branch_sha_recovery',
 jsonb_build_object('branch',p_branch,'sha',p_expected_sha,'reason',p_reason,'at',now()))
 where id=s.id;
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(s.project_id,t.id,r.id,'system','branch-sha-recovery','change_set.branch_sha_requeued',
 jsonb_build_object('change_set_id',s.id,'work_unit_id',u.id,'branch',p_branch,'sha',p_expected_sha,'reason',p_reason));
 return jsonb_build_object('status','building','run_id',r.id,'change_set_id',s.id);
end $$;
revoke all on function public.factory_retry_blocked_change_set_branch_sha(uuid,text,text,text) from public,anon,authenticated;
grant execute on function public.factory_retry_blocked_change_set_branch_sha(uuid,text,text,text) to service_role;