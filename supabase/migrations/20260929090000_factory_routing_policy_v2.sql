create or replace function public.factory_record_dispatch_decision_v2(
 p_run_id uuid,p_route text,p_codex_level integer,p_codex_used boolean,
 p_codex_reasons jsonb,p_routing_policy_version text,p_human_gate boolean,p_gate_reasons jsonb
) returns void
language plpgsql security invoker set search_path=''
as $$
declare v_task_id uuid;v_project_id uuid;
begin
 if p_route not in ('direct','codex') then raise exception 'invalid route';end if;
 if p_codex_level<0 or p_codex_level>4 then raise exception 'invalid codex level';end if;
 if jsonb_typeof(coalesce(p_codex_reasons,'[]'::jsonb))<>'array' then raise exception 'codex reasons must be array';end if;
 if jsonb_typeof(coalesce(p_gate_reasons,'[]'::jsonb))<>'array' then raise exception 'gate reasons must be array';end if;
 if nullif(btrim(p_routing_policy_version),'') is null then raise exception 'routing policy version required';end if;

 select r.task_id,t.project_id into v_task_id,v_project_id
 from public.factory_runs r join public.factory_tasks t on t.id=r.task_id
 where r.id=p_run_id for update of r;
 if v_task_id is null then raise exception 'run not found';end if;

 update public.factory_runs
 set execution_route=p_route,
     status=case when p_human_gate then 'awaiting_human' else 'queued' end,
     metadata=metadata||jsonb_build_object(
       'dispatch_pending',false,'codex_level',p_codex_level,'codex_used',p_codex_used,
       'codex_reasons',coalesce(p_codex_reasons,'[]'::jsonb),
       'routing_policy_version',p_routing_policy_version,
       'human_gate_required',p_human_gate,'gate_reasons',coalesce(p_gate_reasons,'[]'::jsonb)
     )
 where id=p_run_id;

 update public.factory_tasks
 set status=case when p_human_gate then 'awaiting_human' else 'queued_execution' end,updated_at=now()
 where id=v_task_id;

 insert into public.factory_decisions(project_id,task_id,decision_type,question,decision,decided_by)
 values(v_project_id,v_task_id,'execution_route',null,
   jsonb_build_object(
    'route',p_route,'codex_level',p_codex_level,'codex_used',p_codex_used,
    'codex_reasons',coalesce(p_codex_reasons,'[]'::jsonb),
    'routing_policy_version',p_routing_policy_version,
    'human_gate_required',p_human_gate,'gate_reasons',coalesce(p_gate_reasons,'[]'::jsonb)
   ),'ai-product-factory');

 insert into public.factory_codex_usage(run_id,policy_level,invocation_count,reason,reported_usage)
 values(p_run_id,p_codex_level,0,coalesce(p_codex_reasons,'[]'::jsonb),
   jsonb_build_object('routing_policy_version',p_routing_policy_version));
end;
$$;

revoke all on function public.factory_record_dispatch_decision_v2(uuid,text,integer,boolean,jsonb,text,boolean,jsonb)
 from public,anon,authenticated;
grant execute on function public.factory_record_dispatch_decision_v2(uuid,text,integer,boolean,jsonb,text,boolean,jsonb)
 to service_role;
