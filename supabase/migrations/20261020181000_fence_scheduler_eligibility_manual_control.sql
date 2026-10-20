-- Read-only selection fences for the human-managed project lifecycle.
-- Captured from LIVE production definitions on 2026-10-20, with only
-- eligibility restrictions inserted; no work writes or permission expansion.
-- Existing transactional dispatch v2/worker claims remain authoritative.
BEGIN;
CREATE OR REPLACE FUNCTION public.factory_portfolio_candidates(p_limit integer DEFAULT 20)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
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
  join public.factory_project_execution_controls ctl on ctl.project_id=p.id and ctl.state='running' and ctl.generation>0
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
$function$

CREATE OR REPLACE FUNCTION public.factory_peek_planned_work(p_project_key text, p_limit integer DEFAULT 100)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare v_project_id uuid;v_team_id uuid;v_team_status text;v_items jsonb;
begin
 if p_limit<1 or p_limit>100 then raise exception 'invalid candidate limit';end if;
 select id into v_project_id from public.factory_projects
 where project_key=btrim(p_project_key) and is_active=true;
 if v_project_id is null then raise exception 'active project not found';end if;
 select id,status into v_team_id,v_team_status
 from public.factory_execution_team_plans
 where project_id=v_project_id order by version desc limit 1;
 if not exists(select 1 from public.factory_project_execution_controls ctl
               where ctl.project_id=v_project_id and ctl.state='running' and ctl.generation>0)
 then return '[]'::jsonb; end if;
 if v_team_status is distinct from 'ready' then return '[]'::jsonb; end if;
 select coalesce(jsonb_agg(q.data order by q.created_at,q.work_unit_id),'[]'::jsonb)
 into v_items from (
  select u.created_at,u.id as work_unit_id,
   jsonb_build_object(
    'work_unit_id',u.id,
    'fingerprint',md5(concat(
      to_jsonb(t)::text,'|',u.id::text,'|',u.status,'|',
      u.agent_key,'|',u.wave,'|',cs.id::text,'|',
      cs.status,'|',cs.current_wave,'|',v_team_id::text)),
    'task_id',t.id,'project_key',p_project_key,'title',t.title,
    'description',t.description,'complexity',t.complexity,'risk',t.risk,
    'metadata',jsonb_build_object(
       'acceptance_criteria',t.acceptance_criteria,'depends_on',t.depends_on,
       'change_set_id',cs.id,'work_unit_id',u.id,'wave',u.wave,
       'agent_key',u.agent_key)
   ) as data
  from public.factory_change_set_work_units u
  join public.factory_change_sets cs on cs.id=u.change_set_id
  join public.factory_tasks t on t.id=u.task_id
  where cs.project_id=v_project_id and cs.team_plan_id=v_team_id
    and cs.status in ('planned','building')
    and u.status='pending' and u.wave=cs.current_wave
    and t.status='queued'
    and not exists(select 1 from public.factory_runs prior
      where prior.task_id=t.id
        and prior.status in ('created','queued','implementing','completed'))
    and not exists(select 1 from public.factory_change_set_work_units older
      where older.task_id=t.id and older.id<>u.id
        and older.status in ('queued','running','completed','integrated'))
  order by u.created_at,u.id limit p_limit
 ) q;
 return v_items;
end;
$function$

REVOKE ALL ON FUNCTION public.factory_portfolio_candidates(integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.factory_portfolio_candidates(integer) TO service_role;
REVOKE ALL ON FUNCTION public.factory_peek_planned_work(text,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.factory_peek_planned_work(text,integer) TO service_role;
COMMIT;
