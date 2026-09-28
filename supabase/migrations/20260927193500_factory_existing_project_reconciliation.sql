create or replace function public.factory_enqueue_project_bootstrap(p_project_key text)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_project_id uuid;
  v_project_kind text;
  v_manifest jsonb;
  v_task_id uuid;
  v_run_id uuid;
  v_external_key text;
  v_title text;
  v_description text;
  v_stages jsonb;
begin
 select id,project_kind,manifest into v_project_id,v_project_kind,v_manifest
 from public.factory_projects where project_key=btrim(p_project_key) and is_active=true;
 if v_project_id is null then raise exception 'active project not found'; end if;

 if v_project_kind='existing' or coalesce(v_manifest->>'reconcile_first','false')='true' then
   v_external_key := 'project-reconciliation-v1';
   v_title := 'Reconciliar projeto existente antes da continuidade';
   v_description := 'Inspecionar as fontes de verdade disponíveis, registrar o estado atual, comparar com o briefing de continuidade e planejar somente as lacunas restantes.';
   v_stages := jsonb_build_array('reconciliation','gap_analysis','planning');
 else
   v_external_key := 'product-bootstrap-v1';
   v_title := 'Preparar descoberta e planejamento do produto';
   v_description := 'Executar descoberta, especificação do produto e planejamento da implementação a partir da entrada aprovada.';
   v_stages := jsonb_build_array('discovery','specification','planning');
 end if;

 select t.id,r.id into v_task_id,v_run_id
 from public.factory_tasks t join public.factory_runs r on r.task_id=t.id
 where t.project_id=v_project_id and t.external_key=v_external_key
   and t.status in ('queued','running') and r.status in ('created','queued','running')
 order by t.created_at desc limit 1;
 if v_task_id is not null then return jsonb_build_object('project_id',v_project_id,'task_id',v_task_id,'run_id',v_run_id,'created',false); end if;

 insert into public.factory_tasks(project_id,external_key,title,description,status,complexity,risk,acceptance_criteria,depends_on)
 values(v_project_id,v_external_key,v_title,v_description,'queued','medium','{}'::jsonb,
   case when v_external_key='project-reconciliation-v1'
     then '["evidencias das fontes de verdade reconciliadas","estado atual persistido","lacunas restantes explicitas","trabalho existente preservado"]'::jsonb
     else '["contexto de descoberta estruturado","especificacao do produto versionada","plano de implementacao acionavel"]'::jsonb end,
   '[]'::jsonb) returning id into v_task_id;

 insert into public.factory_runs(task_id,status,execution_route,metadata)
 values(v_task_id,'created','direct',jsonb_build_object('stages',v_stages,'source','factory-console','reconcile_first',v_external_key='project-reconciliation-v1'))
 returning id into v_run_id;

 insert into public.factory_tool_usage(run_id,tool_family,operation,usage_units,estimated_cost,metadata)
 values(v_run_id,'orchestrator',case when v_external_key='project-reconciliation-v1' then 'enqueue_project_reconciliation' else 'enqueue_product_bootstrap' end,0,0,jsonb_build_object('project_key',p_project_key));

 insert into public.factory_audit_events(project_id,run_id,actor_type,actor_ref,event_type,payload)
 values(v_project_id,v_run_id,'system','factory-console',
   case when v_external_key='project-reconciliation-v1' then 'project.reconciliation.enqueued' else 'project.bootstrap.enqueued' end,
   jsonb_build_object('task_id',v_task_id,'reported_stage',v_manifest->>'reported_stage'));

 return jsonb_build_object('project_id',v_project_id,'task_id',v_task_id,'run_id',v_run_id,'created',true,'mode',case when v_external_key='project-reconciliation-v1' then 'reconciliation' else 'discovery' end);
end;
$$;

revoke all on function public.factory_enqueue_project_bootstrap(text) from public, anon, authenticated;
grant execute on function public.factory_enqueue_project_bootstrap(text) to service_role;
