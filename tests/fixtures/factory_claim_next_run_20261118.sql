-- Read-only snapshot from Factory Control Plane on 2026-11-18.
-- Isolated regression for the installed Product Stage claim RPC.
-- In particular: running with NULL lease_expires_at is not a confirmed
-- expiring lease. Do not infer live worker activity from that claim alone.
CREATE OR REPLACE FUNCTION public.factory_claim_next_run(p_worker_id text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare v_run public.factory_runs%rowtype;v_task public.factory_tasks%rowtype;
 v_project public.factory_projects%rowtype;v_generation bigint;
begin
 if nullif(btrim(p_worker_id),'') is null then
  raise exception 'worker_id is required' using errcode='PT400';
 end if;
 select r.* into v_run from public.factory_runs r
 join public.factory_tasks t on t.id=r.task_id
 join public.factory_project_execution_controls c on c.project_id=t.project_id
 join public.factory_projects p on p.id=t.project_id and p.is_active=true
 where r.status in ('created','queued') and t.status='queued'
   and c.state='running' and c.generation>0
   and (not (r.metadata ? 'execution_generation')
      or r.metadata->>'execution_generation'=c.generation::text
      or r.metadata ? 'retry_of')
 order by r.created_at for update of c skip locked limit 1;
 if v_run.id is null then return null;end if;
 -- Acquire control first, then the task and run rows, matching operator lock order.
 select * into v_task from public.factory_tasks where id=v_run.task_id for update;
 -- Another claimant may have won while we waited for the task lock.
 if v_task.status is distinct from 'queued' then return null;end if;
 select * into v_run from public.factory_runs where id=v_run.id for update;
 if v_run.status not in ('created','queued') then return null;end if;
 select * into v_project from public.factory_projects where id=v_task.project_id;
 select generation into v_generation from public.factory_project_execution_controls
 where project_id=v_project.id for share;
 perform public.factory_assert_project_execution_epoch(v_project.id,v_generation);
 if (v_run.metadata ? 'execution_generation')
    and v_run.metadata->>'execution_generation' is distinct from v_generation::text
    and not (v_run.metadata ? 'retry_of') then return null; end if;
 update public.factory_runs set status='running',lease_owner=p_worker_id,lease_expires_at=null,started_at=coalesce(started_at,now()),
  metadata=coalesce(metadata,'{}'::jsonb)||jsonb_build_object(
   'worker_id',p_worker_id,'claimed_at',now(),'execution_generation',v_generation)
 where id=v_run.id;
 update public.factory_tasks set status='running',updated_at=now() where id=v_task.id;
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_project.id,v_task.id,v_run.id,'system',p_worker_id,'run.claimed',
 jsonb_build_object('execution_generation',v_generation));
 return jsonb_build_object('run_id',v_run.id,'task_id',v_task.id,
  'project_id',v_project.id,'project_key',v_project.project_key,
  'execution_generation',v_generation,
  'stages',coalesce(v_run.metadata->'stages','[]'::jsonb),
  'context',jsonb_build_object('task',v_task.description,'manifest',v_project.manifest));
end;
$function$
