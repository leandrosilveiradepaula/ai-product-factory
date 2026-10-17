-- Read-only production preflight for migration 20261017193000.
-- This query must not claim that the Supabase migration-history record exists.
-- It checks the installed schema and grants without creating runs or changing projects.
with functions as (
 select
   to_regprocedure('public.factory_guard_project_execution_dml()') as guard_oid,
   to_regprocedure('public.factory_control_project_v1(text,text,uuid,bigint,uuid)') as control_oid,
   to_regprocedure('public.factory_settle_project_control_v1(text)') as settle_oid,
   to_regprocedure('public.factory_assert_claimed_run_epoch(uuid,bigint,uuid,text)') as capability_oid,
   to_regprocedure('public.factory_claim_next_run(text)') as claim_oid
), evidence as (
 select
   (guard_oid is not null and control_oid is not null
     and settle_oid is not null and capability_oid is not null
     and claim_oid is not null) as all_five_functions_present,
   coalesce((select not p.prosecdef from pg_proc p where p.oid=capability_oid),false)
     as capability_security_invoker,
   coalesce((select not p.prosecdef from pg_proc p where p.oid=claim_oid),false)
     as claim_security_invoker,
   coalesce((select position('stopping' in pg_get_functiondef(p.oid))>0
     from pg_proc p where p.oid=control_oid),false) as stop_control_logic_present,
   coalesce((select position('stopping' in pg_get_functiondef(p.oid))>0
     from pg_proc p where p.oid=settle_oid),false) as stop_settlement_logic_present,
   coalesce((select position('lease_owner' in pg_get_functiondef(p.oid))>0
     from pg_proc p where p.oid=guard_oid),false) as guard_lease_logic_present,
   coalesce((select position('lease_owner=p_worker_id' in pg_get_functiondef(p.oid))>0
     from pg_proc p where p.oid=claim_oid),false) as claim_lease_binding_present,
   case when capability_oid is not null
     then has_function_privilege('service_role',capability_oid,'EXECUTE')
     else false end as service_role_can_execute,
   case when capability_oid is not null
     then not has_function_privilege('anon',capability_oid,'EXECUTE')
     else false end as anon_cannot_execute,
   case when capability_oid is not null
     then not has_function_privilege('authenticated',capability_oid,'EXECUTE')
     else false end as authenticated_cannot_execute
 from functions
)
select
 case when all_five_functions_present and capability_security_invoker
   and claim_security_invoker and stop_control_logic_present
   and stop_settlement_logic_present and guard_lease_logic_present
   and claim_lease_binding_present and service_role_can_execute
   and anon_cannot_execute and authenticated_cannot_execute
   then 'PASS' else 'FAIL' end as status,
 evidence.*
from evidence;
