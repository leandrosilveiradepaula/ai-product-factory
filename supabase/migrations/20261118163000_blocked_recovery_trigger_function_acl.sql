-- Follow-up to remote migration 20261118162404_operator_blocked_work_recovery.
-- Preserve the SECURITY INVOKER trigger, its body, and all production data.
-- Tighten only the inherited EXECUTE privilege; no worker activation.
begin;
revoke all on function public.factory_sync_blocked_work_recovery_request()
 from public, anon, authenticated;
grant execute on function public.factory_sync_blocked_work_recovery_request()
 to service_role;
commit;
