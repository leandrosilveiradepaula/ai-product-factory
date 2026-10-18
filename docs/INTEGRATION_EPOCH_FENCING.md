# Change Set integration epoch fencing

## Current verified baseline

The **20261018003000** integration claim/checkpoint SQL was applied manually
to production Supabase project `fjplmxfcshhbmzgvyqlm` with the operator's
authorization. Read-only checks verified the two RPC definitions and their
`service_role`-only grants. SQL Editor application may not appear in migration
history. PR #927 then executed the exact SQL in isolated PostgreSQL 16 CI.

## Next candidate: atomic completion and release

`20261018013000_atomic_change_set_integration_epoch_writes.sql` is a **new,
independent production migration, NOT applied**. It requires a separate human
migration authorization after its PR is green and manually merged.

The existing code checked the project epoch immediately before a metadata RPC,
but the older RPCs did not atomically validate that claim and could accept a
revoked worker. This candidate closes that gap:

1. Completion RPC checks `running` and exact generation while holding a
   shared project-control lock before locking its Change Set.
2. The same transaction validates project ownership, worker identity,
   current wave, live lease and recorded attempt.
3. The commit must advance from the prior candidate; every work unit in the
   wave must be completed and based on the expected prior commit.
4. The changed-file array must match the complete set of work-unit paths,
   including no duplicates, unsafe paths or missing files.
5. Integration updates work units, linked tasks, attempt history and repair
   jobs together; failures roll the entire transaction back.
6. Intermediate waves advance without retaining the prior lease or any
   reusable final-release receipt.
7. A final wave creates a durable completion receipt bound to project UUID,
   generation, worker, wave and candidate SHA.
8. GitHub checkpoints remain valid during legitimate `review_ready` and
   `ci_pending` phases, only while the same receipt and release evidence are
   valid and the project still runs under the exact generation.
9. Release preparation atomically verifies receipt, exact branch and SHA,
   project issue URL, and valid run state, then records the run, usage,
   audit event and Change Set status.
10. Repeating the **identical** release request returns the existing run;
    conflicting retries are rejected without duplicating the run or ledger.
11. All three legacy integration mutation RPCs lose service-role EXECUTE.
    Only the guarded completion and release endpoints remain callable.
12. A versioned DB readiness RPC verifies the old grants stay revoked.
    The Python worker calls it **before claiming any work**, so deployment of
    the code before this SQL migration is fail-closed without a GitHub write
    or newly acquired integration lease.

No automatic merge, billing change, OpenAI paid test, preview fabrication,
Supabase RLS relaxation or auto-start is introduced.

## Rollout and human gates

1. Inspect the PR and confirm `test`, `factory-acceptance` and
   `isolated-postgres` all succeed on the **exact candidate SHA**.
   Factory Console was not modified, so Vercel Preview is explicitly N/A.
2. A human performs the production-publishing GitHub merge. Merging code
   **does not authorize or execute** a production database migration.
3. Until the new migration is applied, integration workers fail closed at
   `factory_integration_epoch_write_readiness`. This is an intentional
   temporary interruption of Change Set integration, not approval to restore
   unsafe legacy grants.
4. Obtain **separate explicit human authorization** for
   `20261018013000_atomic_change_set_integration_epoch_writes.sql`.
   Apply the reviewed, SHA-pinned migration through an approved Supabase path.
   Never apply implicitly or purchase credits.
5. Verify the actual functions and privileges directly against the project:

```sql
select proname,
  has_function_privilege('service_role',oid,'EXECUTE') as service_role,
  has_function_privilege('anon',oid,'EXECUTE') as anon,
  has_function_privilege('authenticated',oid,'EXECUTE') as authenticated
from pg_proc where pronamespace='public'::regnamespace
  and proname in (
    'factory_complete_change_set_integration',
    'factory_mark_repair_wave_integrated',
    'factory_prepare_change_set_release',
    'factory_complete_change_set_integration_epoch',
    'factory_prepare_change_set_release_epoch',
    'factory_integration_epoch_write_readiness'
  ) order by proname;
```

Expected: all three legacy mutations `service_role=false`; the three new
functions `service_role=true`; `anon=false`, `authenticated=false` for all.
Confirm the new readiness RPC returns
`{"version":1,"atomic_completion":true,"atomic_release":true,"phase_checkpoints":true}`.

The isolated PostgreSQL test covers wrong owner, stale generation, wrong wave,
wrong project, mismatched/duplicate files, expired lease, atomic repairs,
receipt gating, idempotent release, authorization grants, project pause/restart,
CI checkpoint and multi-wave progression. It does not claim the production
migration was applied or that a remote in-flight GitHub HTTP request can be
atomically canceled once already started.

## Fail-closed recovery

Do not grant EXECUTE back to legacy write RPCs to restore service. If the
migration fails, keep Change Set integration disabled, capture the SQL error
and reconcile the exact schema/functions. Direct/Codex task execution is
separate and remains subject to its existing quotas and human gates.
A stale `review_ready` candidate interrupted by pause/restart may require
a separately audited continuation policy; do not silently replay it under
the next generation.
