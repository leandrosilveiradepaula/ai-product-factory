-- Bind specialist review, repair, requirements and Definition of Done in ONE
-- PostgreSQL transaction. Rollout is fail-closed: new runtime calls only this
-- versioned RPC, which does not exist until this migration is activated.
-- Depends on 20261021030000 and 20261021040500; operator approval required.
BEGIN;
CREATE OR REPLACE FUNCTION public.factory_complete_specialist_lane_with_trace(
 p_job_id uuid, p_status text,
 p_findings jsonb DEFAULT '[]'::jsonb,
 p_evidence jsonb DEFAULT '{}'::jsonb
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path TO ''
AS $function$
DECLARE
 v_completion jsonb;
 v_job public.factory_specialist_lane_jobs%rowtype;
 v_trace jsonb;
BEGIN
 IF p_status NOT IN ('passed','failed','blocked')
    OR jsonb_typeof(coalesce(p_findings,'[]'::jsonb)) <> 'array' THEN
  RAISE EXCEPTION 'invalid specialist evidence input' USING errcode='PT409';
 END IF;

 -- Called atomic completion holds project-control row locks until the
 -- current transaction ends, including the traceability evidence below.
 v_completion:=public.factory_complete_specialist_lane_atomic(
  p_job_id,p_status,p_findings,p_evidence);
 IF jsonb_typeof(v_completion)<>'object'
    OR v_completion->>'job_id' IS DISTINCT FROM p_job_id::text
    OR v_completion->>'status' IS DISTINCT FROM p_status
    OR v_completion->>'post_review_applied' IS DISTINCT FROM 'true' THEN
  RAISE EXCEPTION 'specialist atomic completion receipt invalid' USING errcode='PT409';
 END IF;

 SELECT * INTO v_job FROM public.factory_specialist_lane_jobs j WHERE j.id=p_job_id;
 IF NOT FOUND OR v_job.status IS DISTINCT FROM p_status
    OR v_job.role NOT IN ('security','qa','operations')
    OR v_job.candidate_commit IS NULL OR v_job.run_id IS NULL THEN
  RAISE EXCEPTION 'specialist traceability identity unverified' USING errcode='PT409';
 END IF;

 -- Existing traceability RPC writes linked requirement, DoD and audit rows.
 -- If any part fails, the atomic completion/review/repair also rolls back.
 v_trace:=public.factory_record_delivery_evidence(
  v_job.run_id,v_job.role,p_status,v_job.candidate_commit,
  jsonb_build_object('source','specialist_lane','role',v_job.role,
   'job_id',v_job.id,
   'findings_count',jsonb_array_length(coalesce(p_findings,'[]'::jsonb))));
 IF jsonb_typeof(v_trace)<>'object'
    OR jsonb_typeof(v_trace->'requirements_linked')<>'number'
    OR jsonb_typeof(v_trace->'dod_checks_linked')<>'number' THEN
  RAISE EXCEPTION 'specialist traceability receipt invalid' USING errcode='PT409';
 END IF;
 RETURN v_completion||jsonb_build_object(
  'traceability_recorded',true,'traceability',v_trace);
END;
$function$;
REVOKE ALL ON FUNCTION public.factory_complete_specialist_lane_with_trace(uuid,text,jsonb,jsonb)
 FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.factory_complete_specialist_lane_with_trace(uuid,text,jsonb,jsonb)
 TO service_role;
COMMIT;
