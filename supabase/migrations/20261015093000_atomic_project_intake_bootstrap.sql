-- Atomic bootstrap: safe for new Console intake only after human-approved migration.
CREATE OR REPLACE FUNCTION public.factory_start_project_intake_v1(
 p_project_key text,p_name text,p_repository text,p_project_kind text,
 p_manifest jsonb,p_spec jsonb,p_draft_id uuid,p_operator_user_id uuid,
 p_expected_attachments integer
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path TO ''
AS $function$
DECLARE
 v_id uuid; v_name text; v_repo text; v_kind text; v_manifest jsonb;
 v_spec jsonb; v_count integer; v_task uuid; v_run uuid;
 v_external text; v_cycle jsonb;
BEGIN
 IF nullif(btrim(p_project_key),'') IS NULL OR nullif(btrim(p_name),'') IS NULL
    OR p_project_kind IS NULL OR p_project_kind NOT IN ('greenfield','existing')
    OR p_draft_id IS NULL OR p_operator_user_id IS NULL
    OR p_expected_attachments IS NULL OR p_expected_attachments NOT BETWEEN 0 AND 10
    OR jsonb_typeof(p_manifest) IS DISTINCT FROM 'object'
    OR jsonb_typeof(p_spec) IS DISTINCT FROM 'object'
    OR p_manifest->>'source' IS DISTINCT FROM 'factory-console'
    OR p_manifest->>'onboarding_mode' IS DISTINCT FROM p_project_kind
 THEN RAISE EXCEPTION 'invalid atomic project intake' USING errcode='PT400'; END IF;
 -- Serialize a not-yet-existing project key: row-level FOR UPDATE is
 -- insufficient when two starts race before the first INSERT.
 PERFORM pg_catalog.pg_advisory_xact_lock(
   pg_catalog.hashtextextended('factory-intake:' || btrim(p_project_key),0)
 );
 v_external := CASE WHEN p_project_kind='existing' OR p_manifest->>'reconcile_first'='true'
   THEN 'project-reconciliation-v1' ELSE 'product-bootstrap-v1' END;
 -- Exact request retry: an already committed start must never enqueue a second run.
 SELECT id,name,repository,project_kind,manifest INTO v_id,v_name,v_repo,v_kind,v_manifest
 FROM public.factory_projects
 WHERE project_key=btrim(p_project_key) AND is_active=true FOR UPDATE;
 IF v_id IS NOT NULL THEN
   SELECT spec INTO v_spec FROM public.factory_product_specs
    WHERE project_id=v_id AND version=1 LIMIT 1;
   IF v_manifest->>'bootstrap_request_id' IS DISTINCT FROM p_draft_id::text
      OR v_manifest->>'bootstrap_attachment_count' IS DISTINCT FROM p_expected_attachments::text
      OR v_manifest->>'bootstrap_operator_id' IS DISTINCT FROM p_operator_user_id::text
      OR v_name IS DISTINCT FROM btrim(p_name)
      OR coalesce(v_repo,'') IS DISTINCT FROM coalesce(nullif(btrim(p_repository),''),'')
      OR v_kind IS DISTINCT FROM p_project_kind
      OR v_spec IS DISTINCT FROM p_spec
   THEN RAISE EXCEPTION 'project key belongs to different intake' USING errcode='PT409'; END IF;
   SELECT count(*) INTO v_count FROM public.factory_project_attachments
    WHERE project_id=v_id AND draft_id=p_draft_id
      AND operator_user_id=p_operator_user_id AND finalized_at IS NOT NULL;
   IF v_count IS DISTINCT FROM p_expected_attachments THEN
     RAISE EXCEPTION 'replayed intake attachment mismatch' USING errcode='PT409'; END IF;
   SELECT t.id,r.id INTO v_task,v_run FROM public.factory_tasks t
    JOIN public.factory_runs r ON r.task_id=t.id
    WHERE t.project_id=v_id AND t.external_key=v_external
      AND r.metadata->>'source'='factory-console'
    ORDER BY t.created_at ASC,r.created_at ASC LIMIT 1;
   IF v_run IS NULL THEN RAISE EXCEPTION 'previous intake lacks initial run'
     USING errcode='PT409'; END IF;
   RETURN jsonb_build_object('project_id',v_id,'task_id',v_task,'run_id',v_run,
     'created',false,'attachment_count',v_count,'request_id',p_draft_id::text);
 END IF;
 -- All three existing SECURITY INVOKER functions share this transaction:
 -- an exception rolls back the project, attachment association and first run.
 v_id := public.factory_create_project_intake(
   p_project_key,p_name,p_repository,p_project_kind,
   p_manifest || jsonb_build_object(
     'bootstrap_request_id',p_draft_id::text,
     'bootstrap_attachment_count',p_expected_attachments,
     'bootstrap_operator_id',p_operator_user_id::text
   ),p_spec
 );
 v_count := public.factory_finalize_project_attachments(
   p_draft_id,p_operator_user_id,v_id
 );
 IF v_count IS DISTINCT FROM p_expected_attachments THEN
   RAISE EXCEPTION 'draft attachment count changed during start' USING errcode='PT409'; END IF;
 v_cycle := public.factory_enqueue_project_bootstrap(p_project_key);
 IF v_cycle IS NULL OR v_cycle->>'project_id' IS DISTINCT FROM v_id::text
    OR nullif(v_cycle->>'run_id','') IS NULL OR nullif(v_cycle->>'task_id','') IS NULL
    OR v_cycle->>'created' IS DISTINCT FROM 'true'
 THEN RAISE EXCEPTION 'missing initial durable run' USING errcode='PT409'; END IF;
 RETURN v_cycle || jsonb_build_object('attachment_count',v_count,'request_id',p_draft_id::text);
END;
$function$;
REVOKE ALL ON FUNCTION public.factory_start_project_intake_v1(
 text,text,text,text,jsonb,jsonb,uuid,uuid,integer
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.factory_start_project_intake_v1(
 text,text,text,text,jsonb,jsonb,uuid,uuid,integer
) TO service_role;
