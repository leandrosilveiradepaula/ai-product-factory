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
- The existing isolated-postgres CI job passes, but it must be verified that\n  the new migration itself is exercised before relying on this as SQL coverage.
- No Console path changes: Preview is explicitly not applicable.
- The migration must be separately approved for production after merge.
- Do not merge this PR until integration testing and review of in-flight
  Direct/Codex external-side-effect fencing are complete.

## Known remaining boundary

The database rejects new claims. Routed workers check their lease and project\nexecution generation before starting work, before each producer invocation and\nbefore mutating GitHub via the supported adapter. A pause/stop deliberately\nallows an already-owned run to drain; stopping/restarting revokes its epoch.\nA checkpoint is not a cancellation of an already-started remote operation.\nThis is an explicit residual limitation, not an auto-merge authorization.
