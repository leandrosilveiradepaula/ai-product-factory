-- A new, narrowly scoped, service-only recovery for failed Product Stage runs.
-- Do not use factory_retry_failed_run: it repeats charged stages.
-- Review and explicitly authorize this migration before applying in production.
CREATE OR REPLACE FUNCTION public.factory_resume_failed_product_planning_v1(
    p_source_run_id uuid,
    p_comment_id bigint,
    p_issue_number integer,
    p_actor_id bigint,
    p_actor_login text
) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path TO ''
AS $function$
DECLARE
    v_project public.factory_projects%rowtype;
    v_task public.factory_tasks%rowtype;
    v_source public.factory_runs%rowtype;
    v_snapshot public.factory_project_state_snapshots%rowtype;
    v_generation bigint;
    v_control_state text;
    v_recon_persist bigint;
    v_gap_persist bigint;
    v_new_run_id uuid;
    v_prior_id uuid;
    v_origin text;
    v_request_id text;
    v_gap jsonb;
    v_reconciliation jsonb;
    v_checkpoint jsonb;
    v_metadata jsonb;
BEGIN
    IF p_comment_id IS NULL OR p_comment_id<=0
       OR p_issue_number IS DISTINCT FROM 1055
       OR p_actor_id IS DISTINCT FROM 256917842
       OR p_actor_login IS DISTINCT FROM 'leandrosilveiradepaula' THEN
        RAISE EXCEPTION 'invalid GitHub owner resume authority'
            USING errcode='PT403';
    END IF;
    IF p_source_run_id IS NULL THEN
        RAISE EXCEPTION 'source run identity is required' USING errcode='PT400';
    END IF;

    -- Project lock first: same serialization point as Owner Start/Console.
    -- Do not lock a run and then the project, which can invert lock order.
    SELECT p.* INTO v_project
    FROM public.factory_projects p
    JOIN public.factory_tasks t ON t.project_id=p.id
    JOIN public.factory_runs r ON r.task_id=t.id
    WHERE r.id=p_source_run_id AND p.is_active=true
    FOR UPDATE OF p;
    IF v_project.id IS NULL OR v_project.project_kind NOT IN ('existing','platform') THEN
        RAISE EXCEPTION 'source project unavailable for planning checkpoint'
            USING errcode='PT409';
    END IF;

    SELECT state,generation INTO v_control_state,v_generation
    FROM public.factory_project_execution_controls
    WHERE project_id=v_project.id FOR SHARE;
    IF v_control_state IS DISTINCT FROM 'running' OR v_generation IS NULL OR v_generation<1 THEN
        RAISE EXCEPTION 'project execution control not running' USING errcode='PT409';
    END IF;

    SELECT r.* INTO v_source FROM public.factory_runs r
    WHERE r.id=p_source_run_id FOR UPDATE;
    SELECT t.* INTO v_task FROM public.factory_tasks t
    WHERE t.id=v_source.task_id AND t.project_id=v_project.id FOR UPDATE;

    IF v_source.status IS DISTINCT FROM 'failed'
       OR v_task.id IS NULL OR v_task.status IS DISTINCT FROM 'failed'
       OR v_task.parent_task_id IS NOT NULL
       OR v_source.execution_route IS DISTINCT FROM 'direct'
       OR v_source.metadata->'stages' IS DISTINCT FROM
          '["reconciliation","gap_analysis","planning"]'::jsonb
       OR v_source.metadata->>'error' IS DISTINCT FROM
          'reserved provider cost exceeds remaining budget'
       OR v_source.metadata->>'execution_generation' IS DISTINCT FROM v_generation::text
    THEN
        RAISE EXCEPTION 'source is not eligible for checkpointed planning resume'
            USING errcode='PT409';
    END IF;

    v_origin:=v_source.metadata->>'source';
    v_request_id:=v_source.metadata->>'continuation_request_id';
    IF v_origin IS NULL OR v_origin NOT IN ('github-owner','factory-console')
       OR v_request_id IS NULL
       OR v_request_id IS DISTINCT FROM v_project.manifest#>>'{continuation_request,id}'
       OR v_origin IS DISTINCT FROM v_project.manifest#>>'{continuation_request,source}'
       OR (v_source.metadata->'continuation_request') IS DISTINCT FROM
          ((v_project.manifest->'continuation_request' - 'id'::text) - 'source'::text)
    THEN
        -- Reconcile any request shape drift before adding a new paid run.
        RAISE EXCEPTION 'continuation provenance drift' USING errcode='PT409';
    END IF;

    -- Same-source idempotency: repeated operator requests cannot create a
    -- second planning run or repeat a paid stage. No generic retry_of bypass.
    SELECT r.id INTO v_prior_id FROM public.factory_runs r
    WHERE r.task_id=v_task.id
      AND r.metadata#>>'{resume_checkpoint,source_run_id}'=p_source_run_id::text
    ORDER BY r.created_at DESC LIMIT 1;
    IF v_prior_id IS NOT NULL THEN
        RETURN jsonb_build_object('created',false,'run_id',v_prior_id,
            'source_run_id',p_source_run_id,'project_id',v_project.id,
            'project_key',v_project.project_key,
            'task_id',v_task.id,'stages',jsonb_build_array('planning'),
            'source','checkpointed_product_planning_v1');
    END IF;

    -- Historical descendants of terminal parents do not reactivate.
    IF EXISTS(
        SELECT 1 FROM public.factory_tasks t
        WHERE t.project_id=v_project.id AND t.id<>v_task.id
          AND t.status NOT IN ('completed','cancelled','failed','merged','integrated')
          AND (t.parent_task_id IS NULL OR NOT EXISTS(
              SELECT 1 FROM public.factory_tasks par
              WHERE par.id=t.parent_task_id AND par.project_id=v_project.id
                AND par.status IN ('completed','cancelled','failed','merged','integrated')
          ))
    ) OR EXISTS(
        SELECT 1 FROM public.factory_runs r
        WHERE r.task_id=v_task.id AND r.id<>p_source_run_id
          AND r.created_at>=v_source.created_at
    ) THEN
        RAISE EXCEPTION 'another current cycle or retry exists' USING errcode='PT409';
    END IF;

    -- Each paid stage must have completed and been durably persisted by the
    -- SAME source run, task, project and generation. Merely finding a manifest
    -- with nonempty text is insufficient to resume paid work.
    SELECT max(a.id) INTO v_recon_persist FROM public.factory_audit_events a
    WHERE a.project_id=v_project.id AND a.task_id=v_task.id
      AND a.run_id=p_source_run_id
      AND a.event_type='product.stage.persisted'
      AND a.payload->>'stage'='reconciliation';
    SELECT max(a.id) INTO v_gap_persist FROM public.factory_audit_events a
    WHERE a.project_id=v_project.id AND a.task_id=v_task.id
      AND a.run_id=p_source_run_id
      AND a.event_type='product.stage.persisted'
      AND a.payload->>'stage'='gap_analysis';
    IF v_recon_persist IS NULL OR v_gap_persist IS NULL
       OR v_recon_persist>=v_gap_persist
       OR (SELECT count(*) FROM public.factory_audit_events a
           WHERE a.project_id=v_project.id AND a.task_id=v_task.id
             AND a.run_id=p_source_run_id
             AND a.event_type='product.stage.persisted'
             AND a.payload->>'stage' IN ('reconciliation','gap_analysis'))<>2
       OR NOT EXISTS(
           SELECT 1 FROM public.factory_audit_events a
           WHERE a.project_id=v_project.id AND a.task_id=v_task.id
             AND a.run_id=p_source_run_id AND a.id<v_recon_persist
             AND a.event_type='run.stage.recorded'
             AND a.payload @> '{"stage":"reconciliation","status":"completed"}'::jsonb
       )
       OR NOT EXISTS(
           SELECT 1 FROM public.factory_audit_events a
           WHERE a.project_id=v_project.id AND a.task_id=v_task.id
             AND a.run_id=p_source_run_id AND a.id>v_recon_persist AND a.id<v_gap_persist
             AND a.event_type='run.stage.recorded'
             AND a.payload @> '{"stage":"gap_analysis","status":"completed"}'::jsonb
       )
       OR NOT EXISTS(
           SELECT 1 FROM public.factory_audit_events a
           WHERE a.project_id=v_project.id AND a.task_id=v_task.id
             AND a.run_id=p_source_run_id AND a.id>v_gap_persist
             AND a.event_type='run.stage.recorded'
             AND a.payload @> '{"stage":"planning","status":"failed"}'::jsonb
       )
    THEN
        RAISE EXCEPTION 'incomplete or contradictory source stage evidence'
            USING errcode='PT409';
    END IF;

    SELECT s.* INTO v_snapshot FROM public.factory_project_state_snapshots s
    WHERE s.run_id=p_source_run_id AND s.project_id=v_project.id
      AND s.observed_stage IS DISTINCT FROM 'verification'
    ORDER BY s.created_at DESC LIMIT 1;
    IF v_snapshot.id IS NULL
       OR (SELECT count(*) FROM public.factory_project_state_snapshots s
           WHERE s.run_id=p_source_run_id AND s.project_id=v_project.id
             AND s.observed_stage IS DISTINCT FROM 'verification')<>1
       OR NOT EXISTS(
           SELECT 1 FROM public.factory_audit_events a
           WHERE a.id=v_recon_persist AND a.run_id=p_source_run_id
             AND a.payload->>'snapshot_id'=v_snapshot.id::text
       )
       OR length(btrim(v_snapshot.summary))=0
       OR (jsonb_typeof(v_snapshot.evidence) NOT IN ('array','object')
           OR v_snapshot.evidence IN ('[]'::jsonb,'{}'::jsonb))
          AND (jsonb_typeof(v_snapshot.source_status) IS DISTINCT FROM 'object'
               OR v_snapshot.source_status='{}'::jsonb)
    THEN
        RAISE EXCEPTION 'reconciliation snapshot has no exact source proof'
            USING errcode='PT409';
    END IF;

    -- Source proof must still be the latest writer of project-scoped state.
    IF EXISTS(
        SELECT 1 FROM public.factory_audit_events a
        WHERE a.project_id=v_project.id AND a.id>v_gap_persist
          AND a.event_type='product.stage.persisted'
          AND a.payload->>'stage' IN ('gap_analysis','reconciliation','planning')
    ) THEN
        RAISE EXCEPTION 'project stage state changed since source' USING errcode='PT409';
    END IF;

    v_gap:=v_project.manifest->'gap_analysis';
    IF jsonb_typeof(v_gap) IS DISTINCT FROM 'object'
       OR jsonb_typeof(v_gap->'gaps') IS DISTINCT FROM 'array'
       OR jsonb_typeof(v_gap->'recommended_next_work') IS DISTINCT FROM 'array'
       OR jsonb_array_length(v_gap->'recommended_next_work')<1
       OR jsonb_typeof(v_gap->'_evidence') IS DISTINCT FROM 'object'
    THEN
        RAISE EXCEPTION 'gap analysis checkpoint missing or invalid'
            USING errcode='PT409';
    END IF;

    v_reconciliation:=jsonb_build_object(
        'summary',v_snapshot.summary,'observed_stage',v_snapshot.observed_stage,
        'evidence',v_snapshot.evidence,'gaps',v_snapshot.gaps,
        'constraints',v_snapshot.constraints,'source_status',v_snapshot.source_status
    );
    v_checkpoint:=jsonb_build_object(
        'schema','checkpointed_product_planning_v1',
        'source_run_id',p_source_run_id,
        'source_generation',v_generation,
        'snapshot_id',v_snapshot.id,
        'request_id',v_request_id,
        'github_owner',jsonb_build_object(
            'repository','leandrosilveiradepaula/ai-product-factory',
            'issue_number',p_issue_number,'comment_id',p_comment_id,
            'actor_id',p_actor_id,'actor_login',p_actor_login),
        'project_id',v_project.id,
        'reconciliation',v_reconciliation,
        'gap_analysis',v_gap
    );
    IF octet_length(v_checkpoint::text)>262144 THEN
        RAISE EXCEPTION 'checkpoint exceeds bounded size' USING errcode='PT409';
    END IF;

    v_metadata:=(v_source.metadata
        - 'worker_id' - 'claimed_at' - 'error'
        - 'execution_worker_id' - 'execution_claimed_at'
        - 'recovery_quarantined_epoch' - 'recovery_quarantined_at'
        - 'recovery_observed_generation' - 'stage_evidence')
        || jsonb_build_object(
          'stages',jsonb_build_array('planning'),
          'execution_generation',v_generation,
          'resume_checkpoint',v_checkpoint
        );

    INSERT INTO public.factory_runs(task_id,status,execution_route,metadata)
    VALUES(v_task.id,'queued','direct',v_metadata)
    RETURNING id INTO v_new_run_id;

    UPDATE public.factory_tasks SET status='queued',updated_at=now()
    WHERE id=v_task.id;

    INSERT INTO public.factory_audit_events(
        project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
    ) VALUES(
        v_project.id,v_task.id,v_new_run_id,'human','github-owner',
        'product.planning.resume.requested',
        jsonb_build_object(
            'source_run_id',p_source_run_id,'request_id',v_request_id,
            'issue_number',p_issue_number,'comment_id',p_comment_id,
            'actor_id',p_actor_id,'actor_login',p_actor_login,
            'source','github-owner','paid_calls',0
        )
    );
    INSERT INTO public.factory_audit_events(
        project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
    ) VALUES(
        v_project.id,v_task.id,v_new_run_id,'system','checkpoint-resume',
        'product.planning.resume_queued',
        jsonb_build_object(
            'source_run_id',p_source_run_id,
            'snapshot_id',v_snapshot.id,
            'request_id',v_request_id,
            'execution_generation',v_generation,
            'stages',jsonb_build_array('planning'),
            'source','checkpointed_product_planning_v1',
            'paid_calls',0
        )
    );

    RETURN jsonb_build_object(
        'created',true,'source_run_id',p_source_run_id,
        'run_id',v_new_run_id,'task_id',v_task.id,
        'project_id',v_project.id,'project_key',v_project.project_key,
        'generation',v_generation,
        'stages',jsonb_build_array('planning'),
        'source','checkpointed_product_planning_v1'
    );
END;
$function$;

REVOKE ALL ON FUNCTION public.factory_resume_failed_product_planning_v1(uuid,bigint,integer,bigint,text)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.factory_resume_failed_product_planning_v1(uuid,bigint,integer,bigint,text)
  TO service_role;
