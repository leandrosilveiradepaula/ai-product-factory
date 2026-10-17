# Routed execution lifecycle hardening — PR #910

Five privileged RPCs (Direct/Codex scheduling, Direct/Codex claim and
preapproved Work Unit dispatch) now call `factory_assert_project_running`
inside their database transaction. Function definitions were reconciled against
the live production catalog **read-only** on 2026-10-17; production was not
modified.

The fence rejects new claims when a project is draft, pausing, paused,
stopping or stopped. Already-owned work may drain under the separate
`factory_assert_claimed_run_epoch` capability. It does not authorize a
new claim or new paid work. All human release gates remain in force.

## Validation and rollout

- Unit contract: `python -m unittest tests.test_routed_manual_control_migration -v`.
- Full CI: `test` and `factory-acceptance` must succeed on the exact PR head.
- SQL execution in an isolated disposable PostgreSQL instance is still
  required before production rollout. Static tests are **not** SQL integration tests.
- No Console path changes: Preview is explicitly not applicable.
- The migration must be separately approved for production after merge.
- Do not merge this PR until integration testing and review of in-flight
  Direct/Codex external-side-effect fencing are complete.

## Known remaining boundary

The database rejects *new* claims; Direct/Codex worker external GitHub writes
and model invocations are not yet uniformly fenced with a per-run
generation/lease checkpoint. A worker already holding a claim can continue
through a pause/stop until those checkpoints are added. Treat this as a
separate security-sensitive blocker, not as completed functionality.
