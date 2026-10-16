-- An externally merged pull request must never acquire CI/Preview/release
-- readiness retroactively.  Deterministic, per-run fail-closed reconciliation
-- after the trusted GitHub adapter verifies the exact PR head and merge SHA.
-- This migration defines a narrow RPC only. No live run is modified here.
create or replace function public.factory_block_early_merged_ci_candidate(
  p_run_id uuid,
  p_repository text,
  p_pr_number integer,
  p_candidate_commit text,
  p_merge_sha text
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $function$
declare
  v_run public.factory_runs%rowtype;
  v_set public.factory_change_sets%rowtype;
  v_project_id uuid;
  v_repository text;
  v_evidence jsonb;
  v_result jsonb;
begin
  if p_run_id is null
     or p_pr_number is null or p_pr_number < 1
     or p_repository is null or p_repository !~ '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$'
     or p_candidate_commit is null or p_candidate_commit !~ '^[0-9a-f]{40}$'
     or p_merge_sha is null or p_merge_sha !~ '^[0-9a-f]{40}$'
  then
    raise exception 'invalid immutable GitHub early-merge evidence';
  end if;

  select * into v_run from public.factory_runs
    where id = p_run_id for update;
  if v_run.id is null then
    raise exception 'run not found';
  end if;

  select t.project_id, project.repository into v_project_id, v_repository
  from public.factory_tasks t
  join public.factory_projects project on project.id = t.project_id
  where t.id = v_run.task_id;
  if v_project_id is null or v_repository is distinct from p_repository
     or v_run.candidate_commit is distinct from p_candidate_commit then
    raise exception 'run/project/candidate identity mismatch';
  end if;

  select * into v_set from public.factory_change_sets
  where release_run_id = p_run_id for update;
  if v_run.metadata->>'source' = 'change-set' and v_set.id is null then
    raise exception 'change-set release run has no matching change set';
  end if;
  if v_set.id is not null and
     (v_set.project_id <> v_project_id
      or v_set.candidate_commit is distinct from p_candidate_commit
      or v_run.metadata->>'change_set_id' is distinct from v_set.id::text) then
    raise exception 'change-set identity mismatch';
  end if;

  v_evidence = jsonb_build_object(
    'repository', p_repository,
    'pr_number', p_pr_number,
    'candidate_commit', p_candidate_commit,
    'merge_sha', p_merge_sha,
    'human_merge_observed', true,
    'quality_gate_passed', false,
    'preview_verified', false,
    'release_authorized', false,
    'needs_reconciliation', true
  );

  -- Stable, idempotent acknowledgment. No second mutation on a repeated job.
  if v_run.status = 'blocked' and
     v_run.metadata->'external_early_merge' = v_evidence then
    if v_set.id is not null and
       (v_set.status <> 'blocked' or
        v_set.metadata->'external_early_merge' is distinct from v_evidence) then
      raise exception 'early-merge reconciliation is only partially committed';
    end if;
    return jsonb_build_object('run_id',p_run_id,'status','blocked',
      'merge_sha',p_merge_sha,'idempotent',true,'change_set_id',v_set.id);
  end if;

  if v_run.status <> 'ci_pending' or
     (v_set.id is not null and v_set.status <> 'ci_pending') then
    raise exception 'early-merge reconciliation refused: incompatible run or change-set state';
  end if;

  if not exists (
    select 1 from public.factory_tool_usage usage
    where usage.run_id = p_run_id and usage.operation = 'create_pr'
      and usage.metadata->>'pr' = p_pr_number::text
      and usage.metadata->>'head_sha' = p_candidate_commit
  ) and not coalesce((
    v_run.metadata->>'source' = 'operator_reconciled_dogfood'
    and v_run.metadata->>'pr_number' = p_pr_number::text
  ), false) then
    raise exception 'candidate is missing exact durable pull-request creation evidence';
  end if;

  if exists (
    select 1 from public.factory_release_reports report
    where report.run_id = p_run_id and report.status = 'released'
  ) then
    raise exception 'refusing to override an already released report';
  end if;

  -- The actual GitHub CI state is not inferred from a GitHub merge. Do not
  -- insert synthetic CI success OR failure; the original evaluation stays.
  update public.factory_runs
  set status = 'blocked',
      metadata = metadata || jsonb_build_object('external_early_merge',v_evidence)
  where id = p_run_id and status = 'ci_pending';
  if not found then
    raise exception 'early-merge run update lost its guarded state';
  end if;

  if v_set.id is not null then
    update public.factory_change_sets
    set status = 'blocked',
        metadata = metadata || jsonb_build_object('external_early_merge',v_evidence)
    where id = v_set.id and status = 'ci_pending';
    if not found then
      raise exception 'early-merge change set update lost its guarded state';
    end if;
  end if;

  insert into public.factory_audit_events(
    project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
  ) values (
    v_project_id,v_run.task_id,p_run_id,'system','ci-followup',
    'release.human_merge_before_readiness_blocked',v_evidence
  );

  return jsonb_build_object(
    'run_id',p_run_id,'status','blocked','merge_sha',p_merge_sha,
    'idempotent',false,'change_set_id',v_set.id
  );
end;
$function$;

revoke all on function public.factory_block_early_merged_ci_candidate(
  uuid,text,integer,text,text
) from public, anon, authenticated;
grant execute on function public.factory_block_early_merged_ci_candidate(
  uuid,text,integer,text,text
) to service_role;
