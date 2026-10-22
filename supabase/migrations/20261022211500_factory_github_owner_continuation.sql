-- Authorized owner-only continuation for an existing Factory project, without
-- impersonating the Console. Deploy only after a separately approved migration.
-- The GitHub Actions OIDC broker and exact issue-comment parser are independent
-- identity fences. This function is SECURITY INVOKER and service-role only.
CREATE OR REPLACE FUNCTION public.factory_enqueue_github_owner_continuation_v1(
  p_project_key text,
  p_request text,
  p_comment_id bigint,
  p_issue_number integer,
  p_actor_id bigint,
  p_actor_login text
) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path TO ''
AS $function$
DECLARE
  v_key text := btrim(p_project_key);
  v_request text := btrim(p_request);
  v_id uuid;
  v_manifest jsonb;
  v_kind text;
  v_generation bigint;
  v_state text;
  v_request_id uuid;
  v_task_id uuid;
  v_run_id uuid;
  v_previous jsonb;
  v_when timestamptz := clock_timestamp();
  v_origin jsonb;
BEGIN
  -- These are authorization assertions, NOT a substitute for signed GitHub
  -- OIDC and the job's exact event/issue/comment-owner verification.
  IF v_key IS NULL OR v_key !~ '^[a-z0-9][a-z0-9_-]{0,99}$'
     OR v_request IS NULL OR length(v_request) < 1 OR length(v_request) > 6000
     OR p_comment_id IS NULL OR p_comment_id <= 0
     OR p_issue_number IS DISTINCT FROM 1055
     OR p_actor_id IS DISTINCT FROM 256917842
     OR p_actor_login IS DISTINCT FROM 'leandrosilveiradepaula'
  THEN
    RAISE EXCEPTION 'invalid GitHub owner continuation' USING errcode='PT403';
  END IF;

  -- Deterministic immutable GitHub comment idempotency key. MD5 is only a
  -- namespace/identifier here, never used to authenticate a caller.
  v_request_id := pg_catalog.md5(
    'factory-owner-start-v1:' || p_issue_number::text || ':' || p_comment_id::text
  )::uuid;
  v_origin := jsonb_build_object(
    'repository','leandrosilveiradepaula/ai-product-factory',
    'issue_number',p_issue_number,'comment_id',p_comment_id,
    'actor_id',p_actor_id,'actor_login',p_actor_login
  );

  -- Same project row lock used by the Console's atomic continuation RPC.
  SELECT id,manifest,project_kind INTO v_id,v_manifest,v_kind
  FROM public.factory_projects
  WHERE project_key=v_key AND is_active=true
  FOR UPDATE;
  IF v_id IS NULL THEN
    RAISE EXCEPTION 'active project not found' USING errcode='PT404';
  END IF;
  IF v_kind IS DISTINCT FROM 'existing' THEN
    RAISE EXCEPTION 'GitHub owner continuation requires existing project'
      USING errcode='PT409';
  END IF;

  -- Repeated deliveries are idempotent even after pause/stop/completion.
  SELECT r.id,t.id,r.metadata INTO v_run_id,v_task_id,v_previous
  FROM public.factory_runs r
  JOIN public.factory_tasks t ON t.id=r.task_id
  WHERE t.project_id=v_id
    AND r.metadata->>'continuation_request_id'=v_request_id::text
  ORDER BY r.created_at DESC LIMIT 1;
  IF v_run_id IS NOT NULL THEN
    IF v_previous->>'source' IS DISTINCT FROM 'github-owner'
       OR v_previous#>>'{continuation_request,summary}' IS DISTINCT FROM v_request
       OR v_previous#>>'{continuation_request,attachment_count}' IS DISTINCT FROM '0'
       OR v_previous#>'{continuation_request,github}' IS DISTINCT FROM v_origin
    THEN
      RAISE EXCEPTION 'GitHub owner request id replay mismatch'
        USING errcode='PT409';
    END IF;
    RETURN jsonb_build_object(
      'project_id',v_id,'task_id',v_task_id,'run_id',v_run_id,
      'request_id',v_request_id::text,'created',false,'source','github-owner'
    );
  END IF;

  -- Fail closed on missing, paused, stopped or stale project controls.
  SELECT state,generation INTO v_state,v_generation
  FROM public.factory_project_execution_controls
  WHERE project_id=v_id FOR SHARE;
  IF v_state IS DISTINCT FROM 'running'
     OR v_generation IS NULL OR v_generation<1 THEN
    RAISE EXCEPTION 'project is not running' USING errcode='PT409';
  END IF;

  -- Historical orphan children of terminal parents are not live work.
  -- Unfinished roots, orphans and children of nonterminal parents block.
  IF EXISTS(
    SELECT 1 FROM public.factory_tasks t
    WHERE t.project_id=v_id
      AND t.status NOT IN ('completed','cancelled','failed','merged','integrated')
      AND (t.parent_task_id IS NULL OR NOT EXISTS(
        SELECT 1 FROM public.factory_tasks par
        WHERE par.id=t.parent_task_id AND par.project_id=v_id
          AND par.status IN ('completed','cancelled','failed','merged','integrated')
      ))
  ) THEN
    RAISE EXCEPTION 'another active project cycle exists'
      USING errcode='PT409';
  END IF;

  UPDATE public.factory_projects
  SET manifest=coalesce(v_manifest,'{}'::jsonb) || jsonb_build_object(
    'reconcile_first',true,
    'continuation_request',jsonb_build_object(
      'id',v_request_id::text,'summary',v_request,
      'requested_at',v_when,'source','github-owner',
      'attachment_count',0,'github',v_origin
    )
  ),updated_at=now()
  WHERE id=v_id;

  INSERT INTO public.factory_tasks(
    project_id,external_key,title,description,status,complexity,
    risk,acceptance_criteria,depends_on
  ) VALUES(
    v_id,'project-reconciliation-v1',
    'Reconciliar projeto existente antes da continuidade',
    'Reconciliar as fontes de verdade e implementar somente as lacunas restantes.',
    'queued','medium','{}'::jsonb,
    '["fontes reconciliadas","estado atual persistido","lacunas restantes explicitas","historico preservado"]'::jsonb,
    '[]'::jsonb
  ) RETURNING id INTO v_task_id;

  INSERT INTO public.factory_runs(task_id,status,execution_route,metadata)
  VALUES(
    v_task_id,'created','direct',jsonb_build_object(
      'stages',jsonb_build_array('reconciliation','gap_analysis','planning'),
      'source','github-owner','reconcile_first',true,
      'execution_generation',v_generation,
      'continuation_request_id',v_request_id::text,
      'continuation_request',jsonb_build_object(
        'summary',v_request,'attachment_count',0,
        'requested_at',v_when,'github',v_origin
      )
    )
  ) RETURNING id INTO v_run_id;

  INSERT INTO public.factory_tool_usage(
    run_id,tool_family,operation,usage_units,estimated_cost,metadata
  ) VALUES(
    v_run_id,'orchestrator','enqueue_project_reconciliation',0,0,
    jsonb_build_object(
      'project_key',v_key,'request_id',v_request_id::text,
      'source','github-owner','comment_id',p_comment_id
    )
  );

  -- The actor is the real verified GitHub owner, NEVER factory-console.
  INSERT INTO public.factory_audit_events(
    project_id,run_id,task_id,actor_type,actor_ref,event_type,payload
  ) VALUES(
    v_id,v_run_id,v_task_id,'human','github-owner',
    'project.continuation.requested',
    jsonb_build_object('request_id',v_request_id::text,'summary',v_request,
      'requested_at',v_when,'attachment_count',0,
      'source','github-owner','github',v_origin)
  );

  INSERT INTO public.factory_audit_events(
    project_id,run_id,task_id,actor_type,actor_ref,event_type,payload
  ) VALUES(
    v_id,v_run_id,v_task_id,'system','github-owner',
    'project.reconciliation.enqueued',
    jsonb_build_object('task_id',v_task_id,'request_id',v_request_id::text,
      'source','github-owner','github',v_origin)
  );

  RETURN jsonb_build_object(
    'project_id',v_id,'task_id',v_task_id,'run_id',v_run_id,
    'request_id',v_request_id::text,'created',true,
    'source','github-owner','generation',v_generation,
    'mode','reconciliation'
  );
END;
$function$;

REVOKE ALL ON FUNCTION public.factory_enqueue_github_owner_continuation_v1(
  text,text,bigint,integer,bigint,text
) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.factory_enqueue_github_owner_continuation_v1(
  text,text,bigint,integer,bigint,text
) TO service_role;
