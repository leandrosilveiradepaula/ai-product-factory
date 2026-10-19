-- Explicitly authorized execution only. The function itself makes no data changes until called.
create or replace function public.factory_rebase_blocked_change_set_source(
 p_change_set_id uuid,p_old_sha text,p_new_sha text,p_evidence jsonb,p_reason text
) returns jsonb language plpgsql security invoker set search_path='' as $$
declare s public.factory_change_sets%rowtype; u public.factory_change_set_work_units%rowtype;
 r public.factory_runs%rowtype; t public.factory_tasks%rowtype; p public.factory_projects%rowtype;
begin
 if p_old_sha !~ '^[0-9a-f]{40}$' or p_new_sha !~ '^[0-9a-f]{40}$'
 or p_old_sha=p_new_sha or nullif(btrim(p_reason),'') is null or length(p_reason)>1000
 or jsonb_typeof(p_evidence) is distinct from 'object'
 or p_evidence->>'old_sha' is distinct from p_old_sha
 or p_evidence->>'new_sha' is distinct from p_new_sha
 or p_evidence->>'compare_status' is distinct from 'ahead'
 or coalesce((p_evidence->>'ahead_by') ~ '^[1-9][0-9]*$',false) is false
 then raise exception 'invalid source reconciliation evidence'; end if;
 select * into s from public.factory_change_sets where id=p_change_set_id for update;
 if not found or s.status<>'blocked' or s.source_commit is distinct from p_old_sha
 or s.candidate_commit is distinct from p_old_sha
 or s.metadata->'blocker'->>'type' is distinct from 'implementation_preflight_error'
 or s.metadata->'blocker'->>'reason' is distinct from 'PermissionError: frozen Change Set source differs from pinned candidate'
 or s.lease_owner is not null or s.lease_expires_at is not null or s.release_run_id is not null
 then raise exception 'change set not eligible'; end if;
 select * into p from public.factory_projects where id=s.project_id for share;
 if not found or p.project_kind is distinct from 'existing'
 or p.manifest->'delivery_target'->>'sha' is distinct from p_new_sha
 or p.manifest->'delivery_target'->>'repository' is distinct from p_evidence->>'repository'
 or p.manifest->'delivery_target'->>'branch' is distinct from p_evidence->>'branch'
 or p.manifest->'delivery_target'->>'candidate_pr_number' is distinct from p_evidence->>'pr_number'
 or p.manifest->'delivery_target'->>'mode' is distinct from 'open_pr_candidate'
 then raise exception 'pinned target differs from evidence'; end if;
 if not exists(select 1 from public.factory_project_execution_controls
 where project_id=s.project_id and state='running')
 then raise exception 'project is not running'; end if;
 if (select count(*) from public.factory_change_set_work_units where change_set_id=p_change_set_id)<>1
 then raise exception 'requires one unimplemented work unit'; end if;
 select * into u from public.factory_change_set_work_units
 where change_set_id=p_change_set_id and status='blocked' for update;
 if not found or u.base_commit is distinct from p_old_sha or u.output_commit is not null
 or s.metadata->'blocker'->>'work_unit_id' is distinct from u.id::text
 or s.metadata->'blocker'->>'run_id' is distinct from u.run_id::text
 then raise exception 'blocked unit mismatch'; end if;
 select * into r from public.factory_runs where id=u.run_id for update;
 select * into t from public.factory_tasks where id=u.task_id for update;
 if r.status<>'blocked' or t.status<>'blocked' or r.task_id is distinct from t.id
 or r.attempt_count>3 or r.lease_owner is not null or r.lease_expires_at is not null
 or r.candidate_commit is not null
 then raise exception 'run/task not eligible'; end if;
 update public.factory_change_sets set source_commit=p_new_sha,candidate_commit=p_new_sha,
 status='building',lease_owner=null,lease_expires_at=null,updated_at=now(),
 metadata=(metadata-'blocker')||jsonb_build_object('source_reconciliation',
 p_evidence||jsonb_build_object('reason',p_reason,'at',now()))
 where id=s.id;
 update public.factory_change_set_work_units set base_commit=p_new_sha,status='queued',updated_at=now() where id=u.id;
 update public.factory_runs set status='queued',last_error=null where id=r.id;
 update public.factory_tasks set status='queued_execution',updated_at=now() where id=t.id;
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(s.project_id,t.id,r.id,'system','source-reconciliation','change_set.source.reconciled',
 p_evidence||jsonb_build_object('change_set_id',s.id,'work_unit_id',u.id,'reason',p_reason));
 return jsonb_build_object('status','building','change_set_id',s.id,'run_id',r.id,'source_commit',p_new_sha);
end;
$$;
revoke all on function public.factory_rebase_blocked_change_set_source(uuid,text,text,jsonb,text) from public,anon,authenticated;
grant execute on function public.factory_rebase_blocked_change_set_source(uuid,text,text,jsonb,text) to service_role;
