create or replace function public.factory_enqueue_project_bootstrap(p_project_key text)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare v_project_id uuid; v_task_id uuid; v_run_id uuid;
begin
 select id into v_project_id from public.factory_projects where project_key=btrim(p_project_key) and is_active=true;
 if v_project_id is null then raise exception 'active project not found'; end if;
 select t.id,r.id into v_task_id,v_run_id from public.factory_tasks t join public.factory_runs r on r.task_id=t.id where t.project_id=v_project_id and t.external_key='product-bootstrap-v1' and t.status in ('queued','running') and r.status in ('created','queued','running') order by t.created_at desc limit 1;
 if v_task_id is not null then return jsonb_build_object('project_id',v_project_id,'task_id',v_task_id,'run_id',v_run_id,'created',false); end if;
 insert into public.factory_tasks(project_id,external_key,title,description,status,complexity,risk,acceptance_criteria,depends_on) values(v_project_id,'product-bootstrap-v1','Bootstrap product discovery and planning','Execute discovery, product specification and implementation planning from the approved intake.','queued','medium','{}'::jsonb,'["discovery context is structured","product specification is versioned","implementation plan is actionable"]'::jsonb,'[]'::jsonb) returning id into v_task_id;
 insert into public.factory_runs(task_id,status,execution_route,metadata) values(v_task_id,'created','direct',jsonb_build_object('stages',jsonb_build_array('discovery','specification','planning'),'source','factory-console')) returning id into v_run_id;
 insert into public.factory_tool_usage(run_id,tool_family,operation,usage_units,estimated_cost,metadata) values(v_run_id,'orchestrator','enqueue_product_bootstrap',0,0,jsonb_build_object('project_key',p_project_key));
 insert into public.factory_audit_events(project_id,run_id,actor_type,actor_ref,event_type,payload) values(v_project_id,v_run_id,'system','factory-console','project.bootstrap.enqueued',jsonb_build_object('task_id',v_task_id));
 return jsonb_build_object('project_id',v_project_id,'task_id',v_task_id,'run_id',v_run_id,'created',true);
end;$$;
revoke all on function public.factory_enqueue_project_bootstrap(text) from public, anon, authenticated;
grant execute on function public.factory_enqueue_project_bootstrap(text) to service_role;
