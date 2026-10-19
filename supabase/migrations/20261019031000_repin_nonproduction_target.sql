-- Controlled exact-SHA nonproduction re-pin. Requires separate production migration approval.
-- Only a trusted service-role reconciler can attest verified GitHub facts.
begin;
create function public.factory_repin_nonproduction_target_v1(
 p_project_key text,
 p_expected_sha text,
 p_new_sha text,
 p_expected_generation bigint,
 p_expected_version bigint,
 p_evidence jsonb,
 p_actor_ref text
) returns jsonb
 language plpgsql security invoker set search_path=''
as $repin$
declare
 v_project public.factory_projects%rowtype;
 v_control public.factory_project_execution_controls%rowtype;
 v_target jsonb;
 v_old text;
 v_receipt jsonb;
begin
 if p_project_key is null or p_project_key !~ '^[a-z0-9][a-z0-9-]{0,63}$'
  or p_expected_sha is null or p_expected_sha !~ '^[a-f0-9]{40}$'
  or p_new_sha is null or p_new_sha !~ '^[a-f0-9]{40}$'
  or p_expected_sha=p_new_sha
  or p_expected_generation is null or p_expected_generation < 1
  or p_expected_version is null or p_expected_version < 0
  or p_actor_ref is null or length(p_actor_ref) not between 3 and 128
  or p_actor_ref ~ '[^A-Za-z0-9_.:-]'
  or p_evidence is null or jsonb_typeof(p_evidence) <> 'object'
  or length(p_evidence::text)>8192
 then raise exception 'invalid candidate repin request' using errcode='PT400'; end if;

 select * into v_project from public.factory_projects
 where project_key=p_project_key for update;
 if not found or v_project.is_active is distinct from true
  or v_project.project_kind <> 'existing'
  or v_project.repository is null
 then raise exception 'existing project not active or not found' using errcode='PT409'; end if;
 select * into v_control from public.factory_project_execution_controls
 where project_id=v_project.id for update;
 if not found or v_control.state <> 'running'
  or v_control.generation is distinct from p_expected_generation
  or v_control.version is distinct from p_expected_version
 then raise exception 'project control epoch changed' using errcode='PT409'; end if;

 v_target:=v_project.manifest->'delivery_target';
 v_old:=v_target->>'sha';
 if v_target is null or v_target->>'mode'<>'open_pr_candidate'
  or v_target->>'schema_version'<>'1'
  or v_target->>'repository' is distinct from v_project.repository
  or v_target->>'branch' not like 'preview/%'
  or (v_target->>'candidate_pr_number') is null
 then raise exception 'project lacks verified pinned candidate' using errcode='PT409'; end if;
 if v_old is distinct from p_expected_sha
 then raise exception 'candidate SHA changed concurrently' using errcode='PT409'; end if;

 -- These are signed-by-possession-of-service-role attestations, not user input.
 -- The worker checks live GitHub PR/ref/ancestry/Actions before requesting this CAS.
 if p_evidence->>'source' <> 'github_actions_exact_sha'
  or p_evidence->>'repository' is distinct from v_project.repository
  or p_evidence->>'branch' is distinct from v_target->>'branch'
  or p_evidence->>'pr_number' is distinct from v_target->>'candidate_pr_number'
  or p_evidence->>'expected_sha' is distinct from p_expected_sha
  or p_evidence->>'new_sha' is distinct from p_new_sha
  or p_evidence->>'pr_head_sha' is distinct from p_new_sha
  or p_evidence->>'branch_head_sha' is distinct from p_new_sha
  or p_evidence->>'pr_base' <> 'main'
  or p_evidence->>'pr_state' <> 'open'
  or p_evidence->>'compare_status' <> 'ahead'
  or p_evidence->>'ci_conclusion' <> 'success'
  or p_evidence->>'ci_sha' is distinct from p_new_sha
  or jsonb_typeof(p_evidence->'ahead_by') <> 'number'
  or jsonb_typeof(p_evidence->'behind_by') <> 'number'
  or jsonb_typeof(p_evidence->'ci_run_id') <> 'number'
  or (p_evidence->>'ahead_by')::integer not between 1 and 10000
  or (p_evidence->>'behind_by')::integer <> 0
  or (p_evidence->>'ci_run_id')::bigint <= 0
 then raise exception 'unverified candidate evidence' using errcode='PT400'; end if;

 if not public.factory_control_quiescent(v_project.id)
  or exists(
    select 1 from public.factory_runs r
    join public.factory_tasks t on t.id=r.task_id
    where t.project_id=v_project.id and r.status in (
      'queued','claimed','running','dispatch_pending','ci_pending',
      'integration_pending','review_pending','specialist_review_pending',
      'preview_pending','repair_pending','release_pending'
    )
  )
  or exists(
    select 1 from public.factory_change_sets cs
    where cs.project_id=v_project.id and cs.status in (
      'queued','running','claimed','integration_pending','ci_pending',
      'dispatch_pending','review_pending','specialist_review_pending',
      'preview_pending','release_pending'
    )
  )
 then raise exception 'project has live work, repin refused' using errcode='PT409'; end if;

 -- Keep the former target in immutable audit provenance. Do not rewrite any
 -- historical task, run, change set, evaluation or release report.
 update public.factory_projects
 set manifest=jsonb_set(v_project.manifest,'{delivery_target,sha}',to_jsonb(p_new_sha)),
     updated_at=now()
 where id=v_project.id;
 update public.factory_project_execution_controls
 set version=version+1,generation=generation+1,updated_at=now()
 where project_id=v_project.id;
 v_receipt:=jsonb_build_object(
   'status','updated','project_key',p_project_key,
   'old_sha',p_expected_sha,'new_sha',p_new_sha,
   'generation',p_expected_generation+1,'version',p_expected_version+1,
   'repository',v_project.repository,'branch',v_target->>'branch');
 insert into public.factory_audit_events(
  project_id,actor_type,actor_ref,event_type,payload
 ) values(
  v_project.id,'system',p_actor_ref,
  'project.delivery_target.reconciled',
  v_receipt||jsonb_build_object(
   'pr_number',v_target->'candidate_pr_number',
   'ci_run_id',p_evidence->'ci_run_id',
   'compare_status',p_evidence->>'compare_status',
   'ahead_by',p_evidence->'ahead_by',
   'behind_by',p_evidence->'behind_by',
   'ci_sha',p_evidence->>'ci_sha',
   'source','github_actions_exact_sha')
 );
 return v_receipt;
end;
$repin$;
revoke all on function public.factory_repin_nonproduction_target_v1(
 text,text,text,bigint,bigint,jsonb,text
) from public,anon,authenticated;
grant execute on function public.factory_repin_nonproduction_target_v1(
 text,text,text,bigint,bigint,jsonb,text
) to service_role;
commit;
