-- B4: repair terminal V2 Preview journey state only AFTER exact human
-- nonproduction merge and separately verified CI/quality/browser/release facts.
-- Historical #209: an observer moved its run to integrated/completed before
-- the journey reconciler could observe a transient awaiting_release status.
-- This change cannot merge GitHub, promote main, close a main-target journey,
-- manufacture a human release, alter Auth/RLS or extend public RPC privileges.
-- SOURCE: current live public.factory_reconcile_journey_v2, verified before edit.
-- APPLY TO PRODUCTION ONLY AFTER EXPLICIT HUMAN MIGRATION APPROVAL.
begin;
CREATE OR REPLACE FUNCTION public.factory_reconcile_journey_v2(p_run_id uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare
  v_run public.factory_runs%rowtype;
  v_task public.factory_tasks%rowtype;
  j public.factory_journeys%rowtype;
  c public.factory_change_sets%rowtype;
  rr public.factory_runs%rowtype;
  v_control_state text;
  v_control_generation bigint;
  v_candidate text;
  v_pr text;
  v_preview_url text;
  v_preview_merge text;
  v_not_required boolean := false;
  v_verified boolean := false;
  v_release_ready boolean := false;
  v_merge text;
  v_release_candidate text;
  v_release_status text;
begin
  select * into v_run from public.factory_runs where id=p_run_id;
  if v_run.id is null or v_run.journey_id is null then
    return jsonb_build_object('status','legacy_not_applicable');
  end if;
  select * into j from public.factory_journeys where id=v_run.journey_id for update;
  select * into v_task from public.factory_tasks where id=v_run.task_id;
  if j.id is null or v_task.id is null or v_task.project_id is distinct from j.project_id
     or v_task.journey_id is distinct from j.id
     or v_run.metadata->>'execution_generation' is distinct from j.execution_generation::text
     or j.binding->>'journey_id' is distinct from j.id::text
     or j.binding->>'request_id' is distinct from j.request_id::text
     or j.binding->>'project_id' is distinct from j.project_id::text
     or j.binding->>'source_commit' is distinct from j.source_commit
     or j.binding->>'policy_digest' is distinct from j.policy_digest
  then raise exception 'journey reconciliation identity mismatch' using errcode='PT409'; end if;
  if j.state='closed' then
    return jsonb_build_object('journey_id',j.id,'state',j.state,
      'preview_merge_sha',j.preview_merge_sha,'production_release_sha',j.production_release_sha);
  end if;
  if j.state in ('intake_accepted','awaiting_source') then
    raise exception 'journey reconciliation state is not executable' using errcode='PT409';
  end if;
  select state,generation into v_control_state,v_control_generation
    from public.factory_project_execution_controls where project_id=j.project_id;
  -- Pause/stop/epoch rotation freezes advancement, but an independently
  -- observed human merge can still be recorded after it actually occurred.
  if v_control_state='running' and v_control_generation=j.execution_generation then
    if j.state='source_bound' and exists(
      select 1 from public.factory_runs r
      where r.journey_id=j.id
        and r.metadata->>'execution_generation'=j.execution_generation::text
        and r.status in ('running','completed','preview_ready','awaiting_release','integrated','merged')
    ) then
      update public.factory_journeys set state='executing',updated_at=now() where id=j.id;
      insert into public.factory_audit_events(project_id,run_id,actor_type,actor_ref,event_type,payload)
      values(j.project_id,p_run_id,'system','journey-v2-reconciler','journey.executing',
        jsonb_build_object('journey_id',j.id,'request_id',j.request_id,'generation',j.execution_generation));
      j.state:='executing';
    end if;

    select cs.* into c from public.factory_change_sets cs
    join public.factory_runs release_run on release_run.id=cs.release_run_id
    where cs.journey_id=j.id and cs.project_id=j.project_id
      and release_run.journey_id=j.id and release_run.task_id=cs.root_task_id
      and release_run.metadata->>'execution_generation'=j.execution_generation::text
      and cs.source_commit=j.source_commit
      and cs.integration_branch=j.binding->>'integration_branch'
      and release_run.branch_name=cs.integration_branch
      and cs.candidate_commit=release_run.candidate_commit
      and cs.candidate_commit ~ '^[0-9a-f]{40}$'
      and cs.metadata->'integration_release_request'->>'candidate_commit'=cs.candidate_commit
      and cs.metadata->'integration_release_request'->>'branch'=cs.integration_branch
    order by cs.updated_at desc,cs.id desc limit 1;
    if c.id is not null then
      select * into rr from public.factory_runs where id=c.release_run_id;
      v_candidate:=c.candidate_commit;
      v_pr:=c.metadata->'integration_release_request'->>'pr_number';
      if v_pr ~ '^[1-9][0-9]*$'
         and exists(select 1 from public.factory_evaluations e
           where e.run_id=rr.id and e.eval_type='github_ci'
             and e.status='success' and e.baseline_ref=v_candidate)
         and exists(select 1 from public.factory_evaluations e
           where e.run_id=rr.id and e.eval_type='quality_gate'
             and e.status='success' and e.baseline_ref=v_candidate
             and e.result->>'passed'='true')
      then
        -- A V2 Preview must have used the journey-specific promotion branch,
        -- plus the exact candidate deployment and browser-e2e receipts.
        select d.metadata->>'preview_url' into v_preview_url
        from public.factory_deployments d
        where d.run_id=rr.id and d.environment='preview' and d.status='success'
          and d.metadata->>'candidate_commit'=v_candidate
          and nullif(d.metadata->>'preview_url','') is not null
          and exists(select 1 from public.factory_evaluations e
            where e.run_id=rr.id and e.eval_type='browser_e2e'
              and e.status='success' and e.baseline_ref=d.metadata->>'preview_url')
          and exists(select 1 from public.factory_audit_events a
            where a.run_id=rr.id and a.event_type='preview.promotion_completed'
              and a.payload->>'candidate_commit'=v_candidate
              and a.payload->>'branch'=(j.binding->>'preview_branch_prefix'||'-'||c.id::text)
              and a.payload->>'pr_number'=v_pr)
        order by d.created_at desc limit 1;
        v_not_required:=exists(
          select 1 from public.factory_tool_usage u
          where u.run_id=rr.id and u.operation='preview_not_required_awaiting_human_merge'
            and u.metadata->>'head_sha'=v_candidate and u.metadata->>'pr'=v_pr
        ) and exists(
          select 1 from public.factory_audit_events a
          where a.run_id=rr.id and a.event_type='release.preview_not_required'
            and a.payload->>'head_sha'=v_candidate and a.payload->>'pr'=v_pr
        );
        v_verified:=v_preview_url is not null or v_not_required;
        if v_verified and j.state in ('executing','preview_verified','awaiting_release') then
          if j.candidate_commit is not null and j.candidate_commit is distinct from v_candidate then
            raise exception 'journey candidate changed after verified Preview' using errcode='PT409';
          end if;
          if j.state='executing' then
            update public.factory_journeys set state='preview_verified',
              candidate_commit=v_candidate,updated_at=now() where id=j.id;
            insert into public.factory_audit_events(project_id,run_id,actor_type,actor_ref,event_type,payload)
            values(j.project_id,rr.id,'system','journey-v2-reconciler','journey.preview_verified',
              jsonb_build_object('journey_id',j.id,'candidate_commit',v_candidate,
                'preview_disposition',case when v_not_required then 'not_applicable' else 'browser_verified' end,
                'preview_url',v_preview_url,'pr_number',v_pr::bigint));
            j.state:='preview_verified';
            j.candidate_commit:=v_candidate;
          end if;
          v_release_ready:=rr.status='awaiting_release'
            and j.binding->>'release_base_ref'='main'
            and (
              (j.binding->>'preview_base_ref'='main' and exists(
                select 1 from public.factory_release_reports report
                where report.run_id=rr.id and report.project_id=j.project_id
                  and report.status='ready_for_human_release'
                  and report.candidate_commit=v_candidate
                  and report.report->'blockers'='[]'::jsonb
              ))
              or
              -- A Preview-only candidate has a production-blocked report.
              -- This *exact* production-specific blocker permits only the
              -- human nonproduction merge gate; it never releases main.
              (j.binding->>'preview_base_ref' like 'preview/%' and exists(
                select 1 from public.factory_release_reports report
                where report.run_id=rr.id and report.project_id=j.project_id
                  and report.status='blocked'
                  and report.candidate_commit=v_candidate
                  and report.report->'blockers'=jsonb_build_array(
                    'production requires a separate verified main-target release candidate')
              ))
            )
            and (v_not_required or exists(
              select 1 from public.factory_tool_usage u
              where u.run_id=rr.id and u.operation='verified_preview_awaiting_human_merge'
                and u.metadata->>'head_sha'=v_candidate and u.metadata->>'pr'=v_pr
                and u.metadata->>'preview_url'=v_preview_url))
            and exists(select 1 from public.factory_audit_events a
              where a.run_id=rr.id and a.event_type in ('release.awaiting_human_merge','release.preview_not_required')
                and a.payload->>'head_sha'=v_candidate and a.payload->>'pr'=v_pr);
          if v_release_ready and j.state='preview_verified' then
            update public.factory_journeys set state='awaiting_release',updated_at=now() where id=j.id;
            insert into public.factory_audit_events(project_id,run_id,actor_type,actor_ref,event_type,payload)
            values(j.project_id,rr.id,'system','journey-v2-reconciler','journey.awaiting_release',
              jsonb_build_object('journey_id',j.id,'candidate_commit',v_candidate,
                'pr_number',v_pr::bigint,'automatic_merge',false,
                'gate_kind',case when j.binding->>'preview_base_ref'='main'
                  then 'production_main' else 'nonproduction_preview' end,
                'target_ref',j.binding->>'preview_base_ref',
                'production_release_eligible',(j.binding->>'preview_base_ref'='main')));
            j.state:='awaiting_release';
          end if;
        end if;
      end if;

    end if;
  end if;


  -- The separate nonproduction observer verifies a HUMAN Preview merge.
  -- This can settle while the project is paused; it never authorizes main.
  -- Recovery for an ALREADY VERIFIED human Preview merge observed after
  -- the release observer changed the run to integrated/completed. No
  -- production release, main branch write, or simulated release success.
  -- Every source below is a durable exact-identity Control Plane receipt.
  if (j.state='awaiting_release'
      or (j.state='preview_verified'
        and exists (
          select 1 from public.factory_change_sets cs
          join public.factory_runs completed_run on completed_run.id=cs.release_run_id
          join public.factory_release_reports report on report.run_id=completed_run.id
          where cs.journey_id=j.id and cs.project_id=j.project_id
            and cs.status='completed' and completed_run.status='integrated'
            and completed_run.journey_id=j.id
            and completed_run.metadata->>'execution_generation'=j.execution_generation::text
            and cs.root_task_id=completed_run.task_id
            and cs.source_commit=j.source_commit
            and cs.candidate_commit=j.candidate_commit
            and completed_run.candidate_commit=j.candidate_commit
            and cs.integration_branch=j.binding->>'integration_branch'
            and completed_run.branch_name=cs.integration_branch
            and cs.metadata->'integration_release_request'->>'candidate_commit'=j.candidate_commit
            and cs.metadata->'integration_release_request'->>'branch'=cs.integration_branch
            and report.project_id=j.project_id
            and report.status='blocked'
            and report.candidate_commit=j.candidate_commit
            and report.report->'blockers'=jsonb_build_array(
              'production requires a separate verified main-target release candidate')
            and exists (
              select 1 from public.factory_tool_usage u
              where u.run_id=completed_run.id
                and u.operation='verified_preview_awaiting_human_merge'
                and u.metadata->>'head_sha'=j.candidate_commit
                and u.metadata->>'pr'=cs.metadata->'integration_release_request'->>'pr_number'
                and nullif(u.metadata->>'preview_url','') is not null)
            and exists (
              select 1 from public.factory_audit_events a
              where a.run_id=completed_run.id
                and a.event_type='release.awaiting_human_merge'
                and a.payload->>'head_sha'=j.candidate_commit
                and a.payload->>'pr'=cs.metadata->'integration_release_request'->>'pr_number')
        )))
     and j.binding->>'preview_base_ref' like 'preview/%' then
    select a.payload->>'merge_sha' into v_preview_merge
    from public.factory_audit_events a
    join public.factory_change_sets cs on cs.release_run_id=a.run_id
    where a.run_id is not null and cs.journey_id=j.id
      and cs.project_id=j.project_id and cs.candidate_commit=j.candidate_commit
      and cs.source_commit=j.source_commit
      and cs.integration_branch=j.binding->>'integration_branch'
      and a.event_type='change_set.nonproduction_merge.observed'
      and a.payload->>'candidate_commit'=cs.candidate_commit
      and a.payload->>'base_ref'=j.binding->>'preview_base_ref'
      and a.payload->>'head_ref'=j.binding->>'integration_branch'
      and a.payload->>'repository'=j.binding->>'repository'
      and a.payload->>'pr_number'=cs.metadata->'integration_release_request'->>'pr_number'
      and a.payload->>'merge_sha' ~ '^[0-9a-f]{40}$'
      and a.payload->>'environment'='preview'
      and a.payload->>'merged'='true'
      and a.payload->>'merge_is_ancestor'='true'
      and a.payload->>'vercel_state'='success'
      and a.payload->>'production_released'='false'
      and a.payload->>'evidence_source'='github_exact_pr_and_merge_commit_status'
    order by a.id desc limit 1;
    if v_preview_merge is not null then
      if j.preview_merge_sha is not null and j.preview_merge_sha is distinct from v_preview_merge then
        raise exception 'journey Preview merge receipt conflict' using errcode='PT409';
      end if;
      update public.factory_journeys set state='closed',
        preview_merge_sha=v_preview_merge,updated_at=now() where id=j.id;
      insert into public.factory_audit_events(project_id,run_id,actor_type,actor_ref,event_type,payload)
      values(j.project_id,p_run_id,'system','journey-v2-reconciler','journey.closed',
        jsonb_build_object('journey_id',j.id,'candidate_commit',j.candidate_commit,
          'preview_merge_sha',v_preview_merge,'closure_reason','observed_nonproduction_merge',
          'production_released',false,'automatic_merge',false));
      j.state:='closed'; j.preview_merge_sha:=v_preview_merge;
    end if;
  end if;

  -- Production remains a distinct main-target candidate and human gate.
  -- A Preview-only candidate never becomes released_observed.
  if j.state='awaiting_release' and j.binding->>'preview_base_ref'='main' then
    select report.status,report.candidate_commit,report.report->>'merge_sha'
      into v_release_status,v_release_candidate,v_merge
    from public.factory_release_reports report
    join public.factory_runs release_run on release_run.id=report.run_id
    where release_run.journey_id=j.id and report.project_id=j.project_id
      and report.status='released' and report.candidate_commit=j.candidate_commit
      and release_run.status='merged'
      and release_run.candidate_commit=report.report->>'merge_sha'
      and release_run.metadata->>'execution_generation'=j.execution_generation::text
    order by report.updated_at desc limit 1;
    if v_release_status='released' and v_merge ~ '^[0-9a-f]{40}$'
       and exists(select 1 from public.factory_audit_events a
         join public.factory_runs release_run on release_run.id=a.run_id
         where release_run.journey_id=j.id
           and a.event_type='release.human_merge_observed'
           and a.payload->>'merge_sha'=v_merge
           and coalesce(a.payload->>'candidate_commit',a.payload->>'head_sha')
               =j.candidate_commit)
    then
      if j.production_release_sha is not null and j.production_release_sha is distinct from v_merge then
        raise exception 'journey production release receipt conflict' using errcode='PT409';
      end if;
      update public.factory_journeys set state='released_observed',
        production_release_sha=v_merge,updated_at=now() where id=j.id;
      insert into public.factory_audit_events(project_id,run_id,actor_type,actor_ref,event_type,payload)
      values(j.project_id,p_run_id,'system','journey-v2-reconciler','journey.released_observed',
        jsonb_build_object('journey_id',j.id,'candidate_commit',j.candidate_commit,
          'merge_sha',v_merge,'automatic_merge',false));
      j.state:='released_observed';
    end if;
  end if;
  return jsonb_build_object('journey_id',j.id,'state',j.state,
    'candidate_commit',j.candidate_commit,'preview_merge_sha',j.preview_merge_sha,
    'production_release_sha',case when j.state='released_observed' then v_merge else j.production_release_sha end);
end $function$;
commit;
