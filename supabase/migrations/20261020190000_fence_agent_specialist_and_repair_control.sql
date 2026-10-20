-- Security-invoker operator control boundaries: six new-work entry points.
-- Source definitions read from production catalog at 2026-10-20; isolated
-- validation precedes any separately approved production migration.
-- No broadening of grants; preserve all previous function signatures.
BEGIN;
CREATE OR REPLACE FUNCTION public.factory_claim_agent_slot(p_run_id uuid, p_agent_key text, p_scope_keys jsonb DEFAULT '[]'::jsonb, p_lease_seconds integer DEFAULT 900)
 RETURNS uuid
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare
 v_agent public.factory_agents%rowtype;
 v_task public.factory_tasks%rowtype;
 v_project_id uuid;
 v_assignment_id uuid;
 v_active_count integer;
 v_scope text;
 v_conflict record;
begin
 if p_lease_seconds < 60 or p_lease_seconds > 7200 then raise exception 'invalid agent lease'; end if;
 if jsonb_typeof(coalesce(p_scope_keys,'[]'::jsonb)) <> 'array' then raise exception 'scope keys must be an array'; end if;

 select * into v_agent from public.factory_agents where agent_key=p_agent_key and is_active for update;
 if not found then raise exception 'active agent not found'; end if;

 select t.* into v_task from public.factory_runs r join public.factory_tasks t on t.id=r.task_id where r.id=p_run_id;
 if not found then raise exception 'run not found'; end if;
 v_project_id:=v_task.project_id;
 perform public.factory_assert_project_running(v_project_id);

 -- Serialize scope conflict checks across agents of the same project.
 -- Row locks on individual agents do not protect overlapping hierarchical scopes.
 -- Advisory transaction lock is automatically released at commit/rollback.
 if jsonb_array_length(coalesce(p_scope_keys,'[]'::jsonb)) > 0 then
  perform pg_catalog.pg_advisory_xact_lock(
   pg_catalog.hashtextextended('factory:agent-scopes:' || v_project_id::text,0)
  );
 end if;

 select count(*) into v_active_count
 from public.factory_run_agent_assignments a
 where a.agent_id=v_agent.id and a.status in ('assigned','claimed');
 if v_active_count >= v_agent.max_concurrency then raise exception 'agent concurrency exhausted'; end if;

 if exists(select 1 from public.factory_run_agent_assignments where run_id=p_run_id and status in ('assigned','claimed')) then
  raise exception 'run already assigned';
 end if;

 for v_scope in select value from jsonb_array_elements_text(coalesce(p_scope_keys,'[]'::jsonb))
 loop
  if btrim(v_scope)='' or v_scope like '%..%' then raise exception 'invalid scope key'; end if;
  select l.scope_key,l.run_id into v_conflict
  from public.factory_agent_scope_locks l
  where l.project_id=v_project_id
    and l.released_at is null
    and l.lease_expires_at > now()
    and l.run_id <> p_run_id
    and (
      l.scope_key=v_scope
      or starts_with(l.scope_key,v_scope || '/')
      or starts_with(v_scope,l.scope_key || '/')
    )
  limit 1;
  if found then raise exception 'scope conflict with run % on %',v_conflict.run_id,v_conflict.scope_key; end if;
 end loop;

 insert into public.factory_run_agent_assignments(run_id,agent_id,status,claimed_at)
 values(p_run_id,v_agent.id,'assigned',null) returning id into v_assignment_id;

 for v_scope in select value from jsonb_array_elements_text(coalesce(p_scope_keys,'[]'::jsonb))
 loop
  insert into public.factory_agent_scope_locks(project_id,run_id,agent_id,scope_key,lease_expires_at)
  values(v_project_id,p_run_id,v_agent.id,v_scope,now()+make_interval(secs=>p_lease_seconds));
 end loop;

 update public.factory_agents set health_status='working',updated_at=now() where id=v_agent.id;
 return v_assignment_id;
end;$function$;

CREATE OR REPLACE FUNCTION public.factory_schedule_run_agent(p_run_id uuid, p_preferred_role text DEFAULT NULL::text, p_required_capabilities jsonb DEFAULT '[]'::jsonb, p_scope_keys jsonb DEFAULT '[]'::jsonb, p_lease_seconds integer DEFAULT 900)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare
 v_agent public.factory_agents%rowtype;
 v_cap text;
 v_assignment_id uuid;
begin
 if jsonb_typeof(coalesce(p_required_capabilities,'[]'::jsonb)) <> 'array' then raise exception 'required capabilities must be an array'; end if;
 perform public.factory_assert_project_running(
   (select t.project_id from public.factory_runs r
    join public.factory_tasks t on t.id=r.task_id where r.id=p_run_id)
 );

 select a.* into v_agent
 from public.factory_agents a
 where a.is_active=true
   and (p_preferred_role is null or a.role=p_preferred_role or a.agent_key=p_preferred_role)
   and not exists (
     select 1 from jsonb_array_elements_text(coalesce(p_required_capabilities,'[]'::jsonb)) r(value)
     where not (a.capabilities ? r.value)
   )
   and not exists (
     select 1
     from jsonb_array_elements_text(coalesce(p_scope_keys,'[]'::jsonb)) s(value)
     join public.factory_runs rr on rr.id=p_run_id
     join public.factory_tasks tt on tt.id=rr.task_id
     join public.factory_agent_scope_locks l on l.project_id=tt.project_id
     where l.released_at is null
       and l.lease_expires_at > now()
       and l.run_id <> p_run_id
       and (
         l.scope_key=s.value
         or starts_with(l.scope_key,s.value || '/')
         or starts_with(s.value,l.scope_key || '/')
       )
   )
   and (
     select count(*) from public.factory_run_agent_assignments x
     where x.agent_id=a.id and x.status in ('assigned','claimed')
   ) < a.max_concurrency
 order by
   case when a.agent_key=p_preferred_role then 0 when a.role=p_preferred_role then 1 else 2 end,
   a.agent_key
 for update skip locked
 limit 1;

 if v_agent.id is null then return null; end if;

 v_assignment_id:=public.factory_claim_agent_slot(
   p_run_id,v_agent.agent_key,coalesce(p_scope_keys,'[]'::jsonb),p_lease_seconds
 );

 return jsonb_build_object(
   'assignment_id',v_assignment_id,
   'agent_id',v_agent.id,
   'agent_key',v_agent.agent_key,
   'role',v_agent.role,
   'max_concurrency',v_agent.max_concurrency,
   'model_policy',v_agent.model_policy,
   'allowed_tools',v_agent.allowed_tools
 );
end;$function$;

CREATE OR REPLACE FUNCTION public.factory_schedule_next_unassigned_run()
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare v_run public.factory_runs%rowtype;v_task public.factory_tasks%rowtype;v_result jsonb;
begin
 select r.* into v_run
 from public.factory_runs r
 join public.factory_tasks t on t.id=r.task_id
 join public.factory_projects p on p.id=t.project_id and p.is_active=true
 join public.factory_project_execution_controls c on c.project_id=p.id and c.state='running' and c.generation>0
 where r.status='queued'
   and r.execution_route in ('direct','codex')
   and t.status='queued_execution'
   and not exists(
     select 1 from public.factory_run_agent_assignments a
     where a.run_id=r.id and a.status in ('assigned','claimed')
   )
 order by r.created_at
 for update of r skip locked
 limit 1;
 if v_run.id is null then return null; end if;

 select * into v_task from public.factory_tasks where id=v_run.task_id;
 v_result:=public.factory_schedule_run_agent(
   v_run.id,
   case
     when nullif(v_task.agent_role,'') is not null then v_task.agent_role
     when coalesce(v_task.required_capabilities,'[]'::jsonb)='[]'::jsonb then 'development'
     else null
   end,
   coalesce(v_task.required_capabilities,'[]'::jsonb),
   coalesce(v_task.scope_keys,'[]'::jsonb),
   900
 );
 if v_result is null then return null; end if;
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_task.project_id,v_task.id,v_run.id,'system','agent-scheduler','agent.assigned',v_result);
 return v_result || jsonb_build_object('run_id',v_run.id,'task_id',v_task.id);
end;$function$;

CREATE OR REPLACE FUNCTION public.factory_claim_specialist_lane(p_role text, p_worker_id text, p_lease_seconds integer DEFAULT 600)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare v_job public.factory_specialist_lane_jobs%rowtype;v_project public.factory_projects%rowtype;v_run public.factory_runs%rowtype;
begin
 if p_role not in ('security','qa','operations') then raise exception 'invalid specialist role'; end if;
 if nullif(btrim(p_worker_id),'') is null then raise exception 'worker id required'; end if;
 if p_lease_seconds<60 or p_lease_seconds>1800 then raise exception 'invalid lease'; end if;

 select * into v_job
 from public.factory_specialist_lane_jobs j
 where j.role=p_role
   and exists(select 1 from public.factory_projects p
       join public.factory_project_execution_controls c on c.project_id=p.id
       where p.id=j.project_id and p.is_active=true and c.state='running' and c.generation>0)
   and attempt_count < 3
   and (
     status='queued'
     or (status='claimed' and lease_expires_at<=now())
   )
 order by created_at
 for update skip locked
 limit 1;
 if v_job.id is null then return null; end if;

 select * into v_run from public.factory_runs where id=v_job.run_id;
 if v_run.candidate_commit is distinct from v_job.candidate_commit then
   update public.factory_specialist_lane_jobs set status='blocked',completed_at=now(),updated_at=now(),
     findings=jsonb_build_array(jsonb_build_object('code','candidate_commit_mismatch','severity','critical'))
   where id=v_job.id;
   return null;
 end if;
 select * into v_project from public.factory_projects where id=v_job.project_id;

 update public.factory_specialist_lane_jobs
 set status='claimed',lease_owner=p_worker_id,lease_expires_at=now()+make_interval(secs=>p_lease_seconds),
     attempt_count=attempt_count+1,updated_at=now()
 where id=v_job.id;

 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 select v_job.project_id,r.task_id,v_job.run_id,'agent',p_role,'specialist.lane.claimed',
        jsonb_build_object('job_id',v_job.id,'candidate_commit',v_job.candidate_commit,'worker_id',p_worker_id)
 from public.factory_runs r where r.id=v_job.run_id;

 return jsonb_build_object(
   'job_id',v_job.id,'run_id',v_job.run_id,'project_key',v_project.project_key,'repository',v_project.repository,
   'role',v_job.role,'candidate_commit',v_job.candidate_commit,'manifest',v_project.manifest
 );
end;
$function$;

CREATE OR REPLACE FUNCTION public.factory_enqueue_specialist_lanes(p_run_id uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare
 v_run public.factory_runs%rowtype;
 v_project_id uuid;
 v_plan jsonb;
 v_role text;
 v_roles text[]:=array[]::text[];
 v_count integer:=0;
begin
 select r.* into v_run from public.factory_runs r where r.id=p_run_id for update;
 if not found then raise exception 'run not found'; end if;
 if nullif(v_run.candidate_commit,'') is null then raise exception 'candidate commit required'; end if;
 select t.project_id into v_project_id from public.factory_tasks t where t.id=v_run.task_id;
 perform public.factory_assert_project_running(v_project_id);
 select plan into v_plan
 from public.factory_execution_team_plans
 where project_id=v_project_id and status='ready'
 order by version desc limit 1;
 if v_plan is null then raise exception 'ready execution team plan required'; end if;

 for v_role in
   select distinct role from (
     select x->>'role' role
     from jsonb_array_elements(coalesce(v_plan->'selected_agents','[]'::jsonb)) x
     where x->>'role' in ('security','qa','operations')
     union all
     select x->>'role' role
     from jsonb_array_elements(coalesce(v_plan->'advisory_specialist_lanes','[]'::jsonb)) x
     where x->>'role' in ('security','qa','operations')
   ) q
 loop
   v_roles:=array_append(v_roles,v_role);
   insert into public.factory_specialist_lane_jobs(run_id,project_id,role,candidate_commit,status,required)
   values(p_run_id,v_project_id,v_role,v_run.candidate_commit,'queued',true)
   on conflict(run_id,role,candidate_commit) do nothing;
   if found then v_count:=v_count+1; end if;
 end loop;

 if coalesce(array_length(v_roles,1),0)=0 then
   update public.factory_runs set status='preview_ready',
     metadata=metadata||jsonb_build_object('specialist_lanes',jsonb_build_object('required',false,'roles','[]'::jsonb))
   where id=p_run_id;
 else
   update public.factory_runs set status='specialist_review_pending',
     metadata=metadata||jsonb_build_object('specialist_lanes',jsonb_build_object('required',true,'roles',to_jsonb(v_roles),'candidate_commit',v_run.candidate_commit))
   where id=p_run_id;
 end if;

 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 select v_project_id,r.task_id,p_run_id,'system','specialist-lane-router','specialist.lanes.enqueued',
        jsonb_build_object('roles',to_jsonb(v_roles),'created_jobs',v_count,'candidate_commit',v_run.candidate_commit)
 from public.factory_runs r where r.id=p_run_id;

 return jsonb_build_object('run_id',p_run_id,'roles',to_jsonb(v_roles),'created_jobs',v_count,
   'status',case when coalesce(array_length(v_roles,1),0)=0 then 'preview_ready' else 'specialist_review_pending' end);
end;
$function$;

CREATE OR REPLACE FUNCTION public.factory_enqueue_repair_from_specialist(p_job_id uuid, p_findings jsonb, p_max_cycles integer DEFAULT 3)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare
 v_job public.factory_specialist_lane_jobs%rowtype;
 v_run public.factory_runs%rowtype;
 v_set public.factory_change_sets%rowtype;
 v_find jsonb;
 v_cycle integer;
 v_task_id uuid;
 v_unit_id uuid;
 v_repair_id uuid;
 v_wave integer;
 v_scopes jsonb;
begin
 if p_max_cycles<1 or p_max_cycles>3 then raise exception 'repair max cycles must be between 1 and 3'; end if;
 if jsonb_typeof(coalesce(p_findings,'[]'::jsonb))<>'array' then raise exception 'findings must be array'; end if;
 select * into v_job from public.factory_specialist_lane_jobs where id=p_job_id for update;
 if not found then raise exception 'specialist job not found'; end if;
 perform public.factory_assert_project_running(v_job.project_id);
 if v_job.role not in ('security','qa') then
  return jsonb_build_object('created',false,'reason','role_not_auto_repairable');
 end if;
 select * into v_run from public.factory_runs where id=v_job.run_id;
 if coalesce(v_run.metadata->>'change_set_id','')='' then
  return jsonb_build_object('created',false,'reason','no_change_set');
 end if;
 select * into v_set from public.factory_change_sets where id=(v_run.metadata->>'change_set_id')::uuid for update;
 if not found then return jsonb_build_object('created',false,'reason','change_set_not_found'); end if;
 select count(*)+1 into v_cycle from public.factory_repair_jobs
 where change_set_id=v_set.id and source_role=v_job.role;
 if v_cycle>p_max_cycles then
  update public.factory_change_sets
  set status='blocked',metadata=metadata||jsonb_build_object('blocker','repair_cycles_exhausted','repair_source_role',v_job.role),updated_at=now()
  where id=v_set.id;
  insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
  values(v_job.project_id,v_run.task_id,v_job.run_id,'system','repair-controller','repair.exhausted',
    jsonb_build_object('change_set_id',v_set.id,'source_role',v_job.role,'max_cycles',p_max_cycles));
  return jsonb_build_object('created',false,'reason','repair_cycles_exhausted','cycle',v_cycle);
 end if;
 select value into v_find from jsonb_array_elements(coalesce(p_findings,'[]'::jsonb)) limit 1;
 if v_find is null then return jsonb_build_object('created',false,'reason','no_findings'); end if;
 v_scopes=case when jsonb_typeof(v_find->'scope_keys')='array' then v_find->'scope_keys'
               when nullif(v_find->>'path','') is not null then jsonb_build_array(v_find->>'path')
               else coalesce(v_set.metadata->'integrated_files','[]'::jsonb) end;
 if jsonb_array_length(coalesce(v_scopes,'[]'::jsonb))=0 then
   update public.factory_change_sets
   set status='blocked',metadata=metadata||jsonb_build_object('blocker','repair_scope_unknown','repair_source_role',v_job.role),updated_at=now()
   where id=v_set.id;
   return jsonb_build_object('created',false,'reason','repair_scope_unknown');
 end if;
 v_wave=v_set.current_wave+1;
 insert into public.factory_tasks(project_id,parent_task_id,external_key,title,description,status,complexity,risk,acceptance_criteria,depends_on)
 values(v_job.project_id,v_set.root_task_id,'repair-'||replace(p_job_id::text,'-','')||'-'||v_cycle,
   'Repair '||v_job.role||' findings - cycle '||v_cycle,
   'Bounded repair generated from independent '||v_job.role||' findings. Fix only the recorded finding and assigned scopes.',
   'queued','medium','{}'::jsonb,jsonb_build_array(jsonb_build_object('finding',v_find,'source_role',v_job.role)),
   '[]'::jsonb)
 returning id into v_task_id;
 insert into public.factory_change_set_work_units(change_set_id,task_id,plan_task_key,agent_key,wave,status)
 values(v_set.id,v_task_id,'repair-'||v_job.role||'-'||v_cycle,'development',v_wave,'pending')
 returning id into v_unit_id;
 insert into public.factory_repair_jobs(project_id,change_set_id,source_run_id,specialist_job_id,source_role,cycle,max_cycles,
   owner_agent_key,candidate_commit,finding,write_scopes,status,task_id,work_unit_id)
 values(v_job.project_id,v_set.id,v_job.run_id,p_job_id,v_job.role,v_cycle,p_max_cycles,'development',
   v_job.candidate_commit,v_find,v_scopes,'queued',v_task_id,v_unit_id) returning id into v_repair_id;
 update public.factory_change_sets
 set status='building',current_wave=v_wave,release_run_id=null,attempt_count=0,lease_owner=null,lease_expires_at=null,
     metadata=metadata||jsonb_build_object('repair_cycle',v_cycle,'repair_source_role',v_job.role),updated_at=now()
 where id=v_set.id;
 update public.factory_runs set status='repair_pending',
   metadata=metadata||jsonb_build_object('repair_job_id',v_repair_id,'repair_cycle',v_cycle)
 where id=v_job.run_id;
 insert into public.factory_audit_events(project_id,task_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_job.project_id,v_task_id,v_job.run_id,'system','repair-controller','repair.queued',
   jsonb_build_object('repair_job_id',v_repair_id,'change_set_id',v_set.id,'cycle',v_cycle,'owner_agent_key','development',
     'write_scopes',v_scopes,'candidate_commit',v_job.candidate_commit));
 return jsonb_build_object('created',true,'repair_job_id',v_repair_id,'task_id',v_task_id,'work_unit_id',v_unit_id,
   'cycle',v_cycle,'max_cycles',p_max_cycles,'status','repair_pending');
end;
$function$;
COMMIT;
