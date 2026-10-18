# Change Set integration epoch fencing

Status: **candidate PR; production migration not applied**.

The integration claim now requires a running project, returns the project UUID, execution generation and lease owner, and issues a bounded worker lease. The runtime checks the exact Change Set, project, generation, worker, wave, status and unexpired lease before every wrapped GitHub mutation and Control Plane integration metadata write.

## Deployment gate

1. Merge the reviewed PR manually. Merging code alone does **not** apply the SQL migration.
2. Obtain explicit human authorization for applying `20261018003000_fence_change_set_integration_epoch.sql` to production Supabase project `fjplmxfcshhbmzgvyqlm`.
3. Apply the migration once, verify both RPC signatures, role grants, and actual claim/checkpoint behavior with controlled disposable fixtures.
4. Until migration is applied, integration claims must **fail closed** (no legacy fallback). Direct/Codex run execution is independent.
5. Confirm a paused/stopped project cannot claim integration, and a worker with an expired lease, changed generation, wrong worker or changed wave cannot mutate GitHub or integration metadata.

## Limitations

A checkpoint before a remote mutation does not atomically cancel an already-started GitHub request. A worker lease is 600 seconds maximum; long-running integrations require explicit renewal in a future change. The new isolated-postgres job currently verifies the existing manual lifecycle fixture, while the new integration SQL is covered by offline contract assertions; do not report this migration as independently executed in PostgreSQL until a dedicated fixture is added.
