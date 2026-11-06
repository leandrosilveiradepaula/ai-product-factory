-- Block 1: PostgreSQL RLS role/claim boundary probes (read-only, no credentials).
-- Simulates effective database role and JWT subject via SET LOCAL. It does NOT verify signed JWTs or Console routes.
-- Run only in privileged PostgreSQL session with rights to SET ROLE; never use a browser/client service key.
-- Each transaction rolls back even its LOCAL role and claim changes. No user IDs are returned.

-- (1) Anonymous access to the operator table must have no SELECT grant.
BEGIN TRANSACTION READ ONLY;
SELECT 'anon_table_grant_denied' AS probe,
       NOT has_table_privilege('anon','public.factory_console_operators','SELECT') AS passed;
ROLLBACK;

-- (2) Authenticated role without subject cannot read a row.
BEGIN TRANSACTION READ ONLY;
SET LOCAL ROLE authenticated;
SELECT 'missing_subject_denied' AS probe,
       count(*) = 0 AS passed FROM public.factory_console_operators;
ROLLBACK;

-- (3) Authenticated with a synthetic unauthorized subject cannot read a row.
BEGIN TRANSACTION READ ONLY;
SELECT set_config('request.jwt.claim.sub','00000000-0000-4000-8000-000000000000',true) IS NOT NULL AS claim_fixture_installed;
SET LOCAL ROLE authenticated;
SELECT 'unauthorized_subject_denied' AS probe,
       count(*) = 0 AS passed FROM public.factory_console_operators;
ROLLBACK;

-- (4) An active operator subject sees only its own active row.
-- Chosen under privileged read-only role; subject value is never selected into the output.
BEGIN TRANSACTION READ ONLY;
SELECT set_config('request.jwt.claim.sub',
  (SELECT user_id::text FROM public.factory_console_operators WHERE is_active = true ORDER BY user_id LIMIT 1), true) IS NOT NULL AS active_fixture_installed;
SET LOCAL ROLE authenticated;
SELECT 'active_operator_self_only' AS probe,
       count(*) = 1 AND coalesce(bool_and(user_id = auth.uid() AND is_active),false) AS passed
FROM public.factory_console_operators;
ROLLBACK;

-- Separate actual anonymous SELECT should raise SQLSTATE 42501 if run manually:
-- BEGIN TRANSACTION READ ONLY; SET LOCAL ROLE anon;
-- SELECT count(*) FROM public.factory_console_operators; ROLLBACK;
-- Do not run the deliberately failing statement in the main battery.
