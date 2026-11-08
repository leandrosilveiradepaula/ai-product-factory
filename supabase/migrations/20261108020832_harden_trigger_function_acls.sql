-- Trigger functions are internal integrity guards, not PostgREST RPCs.
-- Explicitly close the default PUBLIC EXECUTE grant while retaining the
-- service-role execution context used by Factory writes and their triggers.
revoke all on function public.factory_propagate_journey_binding_v2()
  from public, anon, authenticated;
grant execute on function public.factory_propagate_journey_binding_v2()
  to service_role;

revoke all on function public.factory_stamp_ci_release_epoch()
  from public, anon, authenticated;
grant execute on function public.factory_stamp_ci_release_epoch()
  to service_role;

revoke all on function public.factory_sync_ci_repair_lease()
  from public, anon, authenticated;
grant execute on function public.factory_sync_ci_repair_lease()
  to service_role;

revoke all on function public.factory_sync_ci_repair_request()
  from public, anon, authenticated;
grant execute on function public.factory_sync_ci_repair_request()
  to service_role;
