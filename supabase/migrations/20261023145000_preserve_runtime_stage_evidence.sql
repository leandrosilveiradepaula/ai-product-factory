-- Durably persist Product Stage receipts. The old two-key jsonb_set
-- silently returned unchanged metadata when stage_evidence was absent.
-- This is an incremental, service-only function correction. No backfill.
-- Applying to production is a separate human database gate.
begin;
create or replace function public.factory_record_runtime_stage(
 p_run_id uuid, p_stage text, p_status text, p_output jsonb
) returns void language plpgsql security invoker set search_path='' as $f$
declare v_task_id uuid; v_project_id uuid; v_parent jsonb;
begin
 select r.task_id,t.project_id,coalesce(r.metadata->'stage_evidence','{}'::jsonb)
 into v_task_id,v_project_id,v_parent
 from public.factory_runs r join public.factory_tasks t on t.id=r.task_id
 where r.id=p_run_id for update of r;
 if v_task_id is null then raise exception 'run not found'; end if;
 if jsonb_typeof(v_parent) is distinct from 'object' then
  raise exception 'runtime stage evidence parent malformed' using errcode='PT409';
 end if;
 -- Update the entire stage_evidence parent under a run row lock.
 update public.factory_runs
 set metadata=jsonb_set(
   metadata,'{stage_evidence}',
   v_parent || jsonb_build_object(p_stage,jsonb_build_object(
     'status',p_status,'output',coalesce(p_output,'{}'::jsonb),
     'recorded_at',now()
   )),true)
 where id=p_run_id;
 insert into public.factory_audit_events(
   project_id,task_id,run_id,actor_type,actor_ref,event_type,payload
 ) values (
   v_project_id,v_task_id,p_run_id,'system','runtime-worker',
   'run.stage.recorded',jsonb_build_object('stage',p_stage,'status',p_status)
 );
end;
$f$;
revoke all on function public.factory_record_runtime_stage(uuid,text,text,jsonb)
 from public,anon,authenticated;
grant execute on function public.factory_record_runtime_stage(uuid,text,text,jsonb)
 to service_role;
commit;
