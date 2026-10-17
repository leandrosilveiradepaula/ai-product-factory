# Manual lifecycle acceptance — 17 October 2026

## Verified controls and deployment

- Production migration `20261017111500_factory_manual_project_execution_controls.sql` applied with explicit operator approval. Four historical projects remained `running` after backfill; do not use them for destructive lifecycle QA.
- PR #896 was merged and exact-commit Preview plus authenticated Console visual evidence succeeded.
- PR #899 was merged as `d052642bf353de2f045995a62290856c810448cd`; its main-branch `validate` workflow succeeded.
- The existing autonomous runner periodically invokes the privileged, fail-closed settlement adapter. Only `pausing` and `stopping` states are considered; the database RPC decides quiescence transactionally.

## Acceptance gates

1. Register a disposable project and verify it is `draft` without enqueuing execution.
2. Explicit start admits one bootstrap; replaying the same command ID does not duplicate work.
3. Pause prevents new claims and stale execution generations from writing; only after quiescence does settlement acknowledge `paused`.
4. Resume advances generation and rejects old-generation side effects.
5. Stop waits for quiescence and cancels only eligible pending tasks; restart is explicit and idempotent.
6. Reject unauthorized callers, stale versions, invalid commands and concurrent claims.
7. Verify Console actions and errors in authenticated Preview; do not mutate existing production projects for a smoke test.

The isolated PostgreSQL QA covers database invariants without production writes. CI now reruns that QA when runtime/settlement paths change. End-to-end execution against a newly registered disposable project and operator-authenticated Console remains a separate release acceptance step, not implied by unit tests or visual screenshots.
