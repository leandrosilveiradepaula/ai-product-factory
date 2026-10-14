-- Atomic project continuation and lock-sharing with initial bootstrap.
-- Privileged server-only; installing in production requires explicit human migration gate.
CREATE OR REPLACE FUNCTION public.factory_enqueue_project_bootstrap(p_project_key text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY INVOKER
 SET search_path TO ''
AS $function$
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
 from public.factory_projects where project_key=btrim(p_project_key) and is_active=true FOR UPDATE;
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

 if exists(
   select 1 from public.factory_tasks t
   where t.project_id=v_project_id and t.parent_task_id is null
     and t.status not in ('completed','cancelled','failed','merged','integrated')
 ) then raise exception 'another active project cycle exists' using errcode='PT409'; end if;

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
$function$;
REVOKE ALL ON FUNCTION public.factory_enqueue_project_bootstrap(text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.factory_enqueue_project_bootstrap(text) TO service_role;

CREATE OR REPLACE FUNCTION public.factory_enqueue_project_continuation(
 p_project_key text, p_request text, p_request_id uuid, p_attachment_count integer DEFAULT 0
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path TO ''
AS $function$
DECLARE
 v_project_id uuid;
 v_manifest jsonb;
 v_task_id uuid;
 v_run_id uuid;
 v_request text := btrim(p_request);
 v_previous_summary text;
 v_previous_count integer;
 v_original_requested_at text;
 v_requested_at timestamptz := clock_timestamp();
BEGIN
 IF p_request_id IS NULL OR nullif(btrim(p_project_key),'') IS NULL
    OR v_request IS NULL OR v_request = '' OR length(v_request)>6000
    OR p_attachment_count IS NULL OR p_attachment_count NOT BETWEEN 0 AND 10
 THEN RAISE EXCEPTION 'invalid continuation request' USING errcode='PT400'; END IF;

 -- This row lock serializes new continuations with every bootstrap using the same project.
 SELECT id, manifest INTO v_project_id, v_manifest
 FROM public.factory_projects
 WHERE project_key=btrim(p_project_key) AND is_active=true
 FOR UPDATE;
 IF v_project_id IS NULL THEN RAISE EXCEPTION 'active project not found' USING errcode='PT404'; END IF;

 -- Retries of the SAME request are idempotent, including after completion.
 SELECT r.id,t.id,r.metadata#>>'{continuation_request,summary}',
        nullif(r.metadata#>>'{continuation_request,attachment_count}','')::integer,
        r.metadata#>>'{continuation_request,requested_at}'
 INTO v_run_id,v_task_id,v_previous_summary,v_previous_count,v_original_requested_at
 FROM public.factory_runs r
 JOIN public.factory_tasks t ON t.id=r.task_id
 WHERE t.project_id=v_project_id AND r.metadata->>'continuation_request_id'=p_request_id::text
 ORDER BY r.created_at DESC LIMIT 1;
 IF v_run_id IS NOT NULL THEN
  IF v_previous_summary IS DISTINCT FROM v_request OR v_previous_count IS DISTINCT FROM p_attachment_count
  THEN RAISE EXCEPTION 'request id reused with different content' USING errcode='PT409'; END IF;
  RETURN jsonb_build_object('project_id',v_project_id,'task_id',v_task_id,'run_id',v_run_id,
     'request_id',p_request_id::text,'created',false,'requested_at',v_original_requested_at);
 END IF;

 -- Historical queued children of terminal parents are NOT live work.
 -- Unfinished roots, unfinished children of active parents and orphans all fail closed.
 IF EXISTS (
  SELECT 1 FROM public.factory_tasks t
  WHERE t.project_id=v_project_id
    AND t.status NOT IN ('completed','cancelled','failed','merged','integrated')
    AND (t.parent_task_id IS NULL OR NOT EXISTS (
      SELECT 1 FROM public.factory_tasks parent
      WHERE parent.id=t.parent_task_id AND parent.project_id=v_project_id
        AND parent.status IN ('completed','cancelled','failed','merged','integrated')
    ))
 ) THEN
  RAISE EXCEPTION 'another active project cycle exists' USING errcode='PT409';
 END IF;

 UPDATE public.factory_projects
 SET manifest=coalesce(v_manifest,'{}'::jsonb) || jsonb_build_object(
   'reconcile_first',true,
   'continuation_request',jsonb_build_object(
     'id',p_request_id::text,'summary',v_request,'requested_at',v_requested_at,
     'source','factory-console','attachment_count',p_attachment_count
   )
 ), updated_at=now()
 WHERE id=v_project_id;

 INSERT INTO public.factory_tasks(project_id,external_key,title,description,status,complexity,risk,acceptance_criteria,depends_on)
 VALUES(v_project_id,'project-reconciliation-v1',
  'Reconciliar projeto existente antes da continuidade',
  'Inspecionar as fontes de verdade disponíveis, registrar o estado atual, comparar com o briefing de continuidade e planejar somente as lacunas restantes.',
  'queued','medium','{}'::jsonb,
  '["evidencias das fontes de verdade reconciliadas","estado atual persistido","lacunas restantes explicitas","trabalho existente preservado"]'::jsonb,
  '[]'::jsonb
 ) RETURNING id INTO v_task_id;

 INSERT INTO public.factory_runs(task_id,status,execution_route,metadata)
 VALUES(v_task_id,'created','direct',jsonb_build_object(
   'stages',jsonb_build_array('reconciliation','gap_analysis','planning'),
   'source','factory-console','reconcile_first',true,
   'continuation_request_id',p_request_id::text,
   'continuation_request',jsonb_build_object('summary',v_request,'attachment_count',p_attachment_count,'requested_at',v_requested_at)
 )) RETURNING id INTO v_run_id;

 INSERT INTO public.factory_tool_usage(run_id,tool_family,operation,usage_units,estimated_cost,metadata)
 VALUES(v_run_id,'orchestrator','enqueue_project_reconciliation',0,0,
   jsonb_build_object('project_key',p_project_key,'request_id',p_request_id::text));

 INSERT INTO public.factory_audit_events(project_id,run_id,task_id,actor_type,actor_ref,event_type,payload)
 VALUES(v_project_id,v_run_id,v_task_id,'human','factory-console','project.continuation.requested',
   jsonb_build_object('request_id',p_request_id::text,'summary',v_request,
     'requested_at',v_requested_at,'attachment_count',p_attachment_count));

 INSERT INTO public.factory_audit_events(project_id,run_id,task_id,actor_type,actor_ref,event_type,payload)
 VALUES(v_project_id,v_run_id,v_task_id,'system','factory-console','project.reconciliation.enqueued',
   jsonb_build_object('task_id',v_task_id,'request_id',p_request_id::text));

 RETURN jsonb_build_object('project_id',v_project_id,'task_id',v_task_id,'run_id',v_run_id,
   'request_id',p_request_id::text,'requested_at',v_requested_at,'created',true,'mode','reconciliation');
END;
$function$;
REVOKE ALL ON FUNCTION public.factory_enqueue_project_continuation(text,text,uuid,integer) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.factory_enqueue_project_continuation(text,text,uuid,integer) TO service_role;
