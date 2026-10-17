# Routed execution lifecycle hardening — PR #910

Five privileged RPCs (Direct/Codex scheduling, Direct/Codex claim and
preapproved Work Unit dispatch) now call `factory_assert_project_running`
inside their database transaction. Function definitions were reconciled against
the live production catalog **read-only** on 2026-10-17; production migration was subsequently applied under explicit human approval on 2026-10-17.

The fence rejects new claims when a project is draft, pausing, paused,
stopping or stopped. Already-owned work may drain under the separate
`factory_assert_claimed_run_epoch` capability. It does not authorize a
new claim or new paid work. All human release gates remain in force.

## Validation and rollout

- Unit contract: `python -m unittest tests.test_routed_manual_control_migration -v`.
- Full CI: `test` and `factory-acceptance` must succeed on the exact PR head.
- The existing isolated-postgres CI job passes, but it must be verified that
  the new migration itself is exercised before relying on this as SQL coverage.
- No Console path changes: Preview is explicitly not applicable.
- Production migration applied under explicit human approval; future migrations require separate authorization.
- CI unit and isolated Postgres results do not establish an end-to-end live-worker test.

## Known remaining boundary

The database rejects new claims. Routed workers check their lease and project
execution generation before starting work, before each producer invocation and
before mutating GitHub via the supported adapter. A pause/stop deliberately
allows an already-owned run to drain; stopping/restarting revokes its epoch.
A checkpoint is not a cancellation of an already-started remote operation.
This is an explicit residual limitation, not an auto-merge authorization.
