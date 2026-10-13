-- Keep portfolio selection and dispatcher consistent: orphan plan-* tasks are not dispatchable.
-- Zero data rewrites, no new grants, no change to incident priorities or worker budgets.
create or replace function public.factory_portfolio_candidates(p_limit integer default 20)
returns jsonb
language plpgsql security invoker set search_path=''
as $$
declare v_has_p0 boolean;v_rows jsonb;
begin
 if p_limit<1 or p_limit>100 then raise exception 'invalid portfolio candidate limit'; end if;
 select exists(
   select 1 from public.factory_incidents i
   where i.severity='P0' and i.status not in ('resolved','blocked')
 ) into v_has_p0;
 with project_state as (
  select
   p.id,p.project_key,
   coalesce(s.priority,'P2') priority,s.deadline,coalesce(s.customer_impact,1) customer_impact,
   coalesce(s.max_active_workers,4) max_active_workers,coalesce(s.paused,false) paused,
   min(case i.severity when 'P0' then 0 when 'P1' then 1 when 'P2' then 2 when 'P3' then 3 else 9 end)
     filter(where i.status not in ('resolved','blocked')) incident_rank,
   count(distinct r.id) filter(where
     r.status in ('queued','implementing','ci_pending','specialist_review_pending','preview_ready','repair_pending')
     and (r.status<>'preview_ready' or r.metadata->>'source' is distinct from 'dogfood_manual_audit')
   ) active_runs,
   exists(
    select 1 from public.factory_change_sets cs
    join public.factory_execution_team_plans tp on tp.id=cs.team_plan_id
    join public.factory_change_set_work_units u on u.change_set_id=cs.id
    join public.factory_tasks unit_task on unit_task.id=u.task_id
    where cs.project_id=p.id
      and tp.project_id=p.id and tp.status='ready'
      and tp.version=(
        select max(latest.version)
        from public.factory_execution_team_plans latest
        where latest.project_id=p.id
      )
      and cs.status in ('planned','building')
      and u.status='pending' and u.wave=cs.current_wave
      and unit_task.status='queued'
      and not exists(
        select 1 from public.factory_runs prior
        where prior.task_id=u.task_id
          and prior.status in ('created','queued','implementing','completed')
      )
      and not exists(
        select 1 from public.factory_change_set_work_units older
        where older.task_id=u.task_id and older.id<>u.id
          and older.status in ('queued','running','completed','integrated')
      )
   ) has_runnable_work
  from public.factory_projects p
  left join public.factory_project_scheduling s on s.project_id=p.id
  left join public.factory_incidents i on i.project_id=p.id
  left join public.factory_tasks t on t.project_id=p.id
  left join public.factory_runs r on r.task_id=t.id
  where p.is_active=true
  group by p.id,p.project_key,s.priority,s.deadline,s.customer_impact,s.max_active_workers,s.paused
 ), eligible as (
  select *,case priority when 'P0' then 0 when 'P1' then 1 when 'P2' then 2 else 3 end priority_rank
  from project_state
  where has_runnable_work and not paused and active_runs<max_active_workers
    and (not v_has_p0 or incident_rank=0)
 )
 select coalesce(jsonb_agg(jsonb_build_object(
   'project_id',id,'project_key',project_key,'priority',priority,'deadline',deadline,
   'customer_impact',customer_impact,'max_active_workers',max_active_workers,'active_runs',active_runs,
   'open_incident_severity',case incident_rank when 0 then 'P0' when 1 then 'P1' when 2 then 'P2' when 3 then 'P3' else null end,
   'soft_preemption_active',v_has_p0
 ) order by coalesce(incident_rank,9),priority_rank,deadline nulls last,customer_impact desc,project_key)
 , '[]'::jsonb) into v_rows
 from (select * from eligible order by coalesce(incident_rank,9),priority_rank,deadline nulls last,customer_impact desc,project_key limit p_limit) q;
 return v_rows;
end;
$$;
revoke all on function public.factory_portfolio_candidates(integer) from public,anon,authenticated;
grant execute on function public.factory_portfolio_candidates(integer) to service_role;
