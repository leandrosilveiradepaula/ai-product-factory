-- Owner-requested recovery for a technically blocked repair.  This deliberately
-- creates a new, linked continuation; it never mutates a terminal Change Set.
begin;
create table if not exists public.factory_blocked_work_recovery_requests (
 id uuid primary key default gen_random_uuid(), project_id uuid not null references public.factory_projects(id) on delete restrict,
 command_id uuid not null, source_task_id uuid not null references public.factory_tasks(id) on delete restrict,
 source_run_id uuid not null references public.factory_runs(id) on delete restrict,
 repair_job_id uuid not null references public.factory_repair_jobs(id) on delete restrict,
 continuation_task_id uuid, continuation_run_id uuid, status text not null check(status in ('accepted','queued','claimed','recovering','completed','blocked')),
 execution_generation bigint not null check(execution_generation>0), reason_code text, created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 unique(project_id,command_id), unique(repair_job_id)
);
alter table public.factory_blocked_work_recovery_requests enable row level security;
revoke all on public.factory_blocked_work_recovery_requests from public,anon,authenticated;
grant select,insert,update on public.factory_blocked_work_recovery_requests to service_role;

-- Product workers already own the run state machine.  This projection makes
-- the operator receipt durable without granting the Console any worker role.
create or replace function public.factory_sync_blocked_work_recovery_request()
returns trigger language plpgsql security invoker set search_path='' as $sync$
begin
 if new.status is distinct from old.status then
   update public.factory_blocked_work_recovery_requests
   set status=case new.status
     when 'running' then 'recovering'
     when 'implementing' then 'recovering'
     when 'completed' then 'completed'
     when 'failed' then 'blocked'
     when 'cancelled' then 'blocked'
     when 'blocked' then 'blocked'
     else status
   end,updated_at=now()
   where continuation_run_id=new.id
     and status in ('queued','claimed','recovering');
 end if;
 return new;
end;
$sync$;
drop trigger if exists factory_sync_blocked_work_recovery_request on public.factory_runs;
create trigger factory_sync_blocked_work_recovery_request
after update of status on public.factory_runs
for each row execute function public.factory_sync_blocked_work_recovery_request();

create or replace function public.factory_restart_blocked_work_v1(p_project_key text,p_command_id uuid,p_expected_version bigint,p_actor_id uuid)
returns jsonb language plpgsql security invoker set search_path to '' as $f$
declare p public.factory_projects%rowtype; c public.factory_project_execution_controls%rowtype; r public.factory_runs%rowtype; t public.factory_tasks%rowtype; j public.factory_repair_jobs%rowtype; e record; nt uuid; nr uuid; out jsonb;
begin
 if nullif(btrim(p_project_key),'') is null or p_command_id is null or p_actor_id is null or p_expected_version<0 then raise exception 'invalid blocked recovery command' using errcode='PT400'; end if;
 select * into p from public.factory_projects where project_key=btrim(p_project_key) and is_active for update; if not found then raise exception 'project not found' using errcode='PT404'; end if;
 select * into e from public.factory_blocked_work_recovery_requests where project_id=p.id and command_id=p_command_id;
 if found then
   if not exists(select 1 from public.factory_project_execution_commands k
     where k.project_id=p.id and k.command_id=p_command_id and k.command='restart'
       and k.expected_version=p_expected_version and k.actor_id=p_actor_id)
   then raise exception 'reused recovery command with different actor or version' using errcode='PT409'; end if;
   return jsonb_build_object('status',e.status,'request_id',e.id,'run_id',e.continuation_run_id,'task_id',e.continuation_task_id,'idempotent',true);
 end if;
 select * into c from public.factory_project_execution_controls where project_id=p.id for update;
 if c.version<>p_expected_version or c.state<>'running' then raise exception 'project control is not running at expected version' using errcode='PT409'; end if;
 if exists(select 1 from public.factory_runs a join public.factory_tasks at on at.id=a.task_id
   where at.project_id=p.id and a.status in ('running','implementing')
     and (a.lease_owner is not null or a.lease_expires_at>now()))
 then raise exception 'another execution is active in this project' using errcode='PT409'; end if;
 select * into j from public.factory_repair_jobs where project_id=p.id and status='blocked' and cycle<max_cycles order by updated_at desc limit 1 for update; if not found then raise exception 'no resumable blocked repair' using errcode='PT409'; end if;
 select * into t from public.factory_tasks where id=j.task_id and project_id=p.id and status='blocked' for update; if not found then raise exception 'blocked repair task mismatch' using errcode='PT409'; end if;
 select * into r from public.factory_runs where task_id=t.id and status='blocked' and lease_owner is null and lease_expires_at is null order by created_at desc limit 1 for update; if not found then raise exception 'blocked repair lineage mismatch' using errcode='PT409'; end if;
 if not exists(
   select 1 from public.factory_change_sets cs
     join public.factory_runs sr on sr.id=j.source_run_id
     join public.factory_tasks st on st.id=sr.task_id
   where cs.id=j.change_set_id and cs.project_id=p.id and cs.status='completed'
     and cs.root_task_id=st.id and st.project_id=p.id
     and sr.status in ('merged','integrated','completed')
     and cs.lease_owner is null and cs.lease_expires_at is null
 ) then raise exception 'terminal source is not verified in project' using errcode='PT409'; end if;
 if jsonb_typeof(r.metadata) is distinct from 'object'
    or r.metadata->>'change_set_id' is null
    or j.change_set_id::text is distinct from r.metadata->>'change_set_id'
 then raise exception 'blocked repair has no immutable lineage' using errcode='PT409'; end if;
 insert into public.factory_tasks(project_id,parent_task_id,external_key,title,description,status,complexity,risk,acceptance_criteria,depends_on)
 values(p.id,t.id,'operator-recovery-'||replace(p_command_id::text,'-',''),'Retomar reparo bloqueado','Reavaliar o reparo bloqueado a partir de sua evidência imutável; não reabrir o Change Set terminal.','queued',t.complexity,t.risk,t.acceptance_criteria,'[]'::jsonb) returning id into nt;
 insert into public.factory_runs(task_id,status,execution_route,source_commit,candidate_commit,branch_name,metadata)
 values(nt,'queued',null,r.source_commit,null,null,jsonb_build_object(
   'source','operator-blocked-work-recovery',
   'recovery_request_id',p_command_id,
   'recovery_source_run_id',r.id,
   'repair_job_id',j.id,
   'terminal_change_set_id',r.metadata->>'change_set_id',
   'execution_generation',c.generation,
   'stages',jsonb_build_array('reconciliation','gap_analysis','planning'),
   'checkpoint',coalesce(r.metadata->'checkpoint',r.metadata->'stage_evidence','{}'::jsonb)
 )) returning id into nr;
 insert into public.factory_blocked_work_recovery_requests(project_id,command_id,source_task_id,source_run_id,repair_job_id,continuation_task_id,continuation_run_id,status,execution_generation)
 values(p.id,p_command_id,t.id,r.id,j.id,nt,nr,'queued',c.generation) returning jsonb_build_object('status','queued','request_id',id,'run_id',continuation_run_id,'task_id',continuation_task_id,'idempotent',false) into out;
 -- Reuse the bounded wake outbox, not a best-effort browser-only signal.
 -- This is a wake receipt only: it neither changes lifecycle state nor starts
 -- a model, and the continuation still has to pass normal Product-stage gates.
 insert into public.factory_project_execution_commands(
   project_id,command_id,command,expected_version,actor_id,result
 ) values (
   p.id,p_command_id,'restart',p_expected_version,p_actor_id,
   jsonb_build_object('project_id',p.id,'state','running','version',c.version,
     'generation',c.generation,'command','restart','created',true,
     'run_id',nr,'task_id',nt,'recovery_request_id',out->>'request_id')
 );
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload) values(p.id,nt,nr,'human',p_actor_id::text,'blocked_work.recovery.queued',jsonb_build_object('command_id',p_command_id,'source_task_id',t.id,'source_run_id',r.id,'repair_job_id',j.id,'generation',c.generation));
 return out;
end;$f$;
revoke all on function public.factory_restart_blocked_work_v1(text,uuid,bigint,uuid) from public,anon,authenticated;
grant execute on function public.factory_restart_blocked_work_v1(text,uuid,bigint,uuid) to service_role;
commit;
