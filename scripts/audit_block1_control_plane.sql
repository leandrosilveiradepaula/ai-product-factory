-- Block 1: independently executable, read-only Control Plane access audit.
-- Run with a privileged read-only database session. Never changes grants/RLS.
-- A zero blocker count is an inventory result, NOT an adversarial RLS certification.
BEGIN TRANSACTION READ ONLY;
WITH factory_tables AS (
 SELECT c.oid,c.relname,c.relrowsecurity
 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND c.relkind IN ('r','p')
   AND c.relname LIKE 'factory\_%' ESCAPE '\'
), public_grants AS (
 SELECT t.relname, role_name, privilege
 FROM factory_tables t
 CROSS JOIN (VALUES ('anon'),('authenticated')) roles(role_name)
 CROSS JOIN (VALUES ('INSERT'),('UPDATE'),('DELETE'),('TRUNCATE'),('REFERENCES'),('TRIGGER')) privileges(privilege)
 WHERE has_table_privilege(roles.role_name,t.oid,privilege)
), public_policies AS (
 SELECT p.tablename,p.policyname,p.cmd,p.roles
 FROM pg_policies p WHERE p.schemaname='public'
 AND p.tablename LIKE 'factory\_%' ESCAPE '\'
 AND (p.cmd <> 'SELECT' OR p.roles && ARRAY['anon','public']::name[])
), exposed_functions AS (
 SELECT p.proname,p.prosecdef,
 has_function_privilege('anon',p.oid,'EXECUTE') AS anon_execute,
 has_function_privilege('authenticated',p.oid,'EXECUTE') AS authenticated_execute
 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname='public' AND p.proname LIKE 'factory\_%' ESCAPE '\'
), unsafe_definers AS (
 SELECT proname FROM exposed_functions
 WHERE prosecdef AND (anon_execute OR authenticated_execute)
)
SELECT 'factory_control_plane_access_inventory_v1' AS schema,
 (SELECT count(*) FROM factory_tables) AS table_count,
 (SELECT count(*) FROM factory_tables WHERE relrowsecurity) AS rls_enabled,
 (SELECT count(*) FROM public_grants) AS public_write_grants,
 (SELECT count(*) FROM public_policies) AS public_or_write_policies,
 (SELECT count(*) FROM exposed_functions WHERE anon_execute) AS anon_executable_rpcs,
 (SELECT count(*) FROM exposed_functions WHERE authenticated_execute) AS authenticated_executable_rpcs,
 (SELECT count(*) FROM unsafe_definers) AS publicly_executable_security_definers,
 (SELECT count(*) FROM factory_tables WHERE NOT relrowsecurity)
 + (SELECT count(*) FROM public_grants)
 + (SELECT count(*) FROM public_policies)
 + (SELECT count(*) FROM unsafe_definers) AS blockers,
 false AS adversarial_rls_certified,
 false AS product_ready;
COMMIT;
