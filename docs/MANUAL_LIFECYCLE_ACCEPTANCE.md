# Manual lifecycle acceptance — histórico de 17/10/2026, escopo vigente 27/10/2026

Os cenários abaixo são para PostgreSQL **isolado**, não autorização para registrar projetos. O CRM Infodive real é o piloto existing quando houver Start legítimo. Não criar projetos descartáveis no Control Plane de produção para fabricar E2E. Service Desk standalone está parado e aposentado.

## Verified controls and deployment

- Production migration `20261017111500_factory_manual_project_execution_controls.sql` applied with explicit operator approval. Four historical projects remained `running` after backfill; do not use them for destructive lifecycle QA.
- PR #896 was merged and exact-commit Preview plus authenticated Console visual evidence succeeded.
- PR #899 was merged as `d052642bf353de2f045995a62290856c810448cd`; its main-branch `validate` workflow succeeded.
- The existing autonomous runner periodically invokes the privileged, fail-closed settlement adapter. Only `pausing` and `stopping` states are considered; the database RPC decides quiescence transactionally.

## Acceptance gates

1. Em PostgreSQL isolado, verificar que um cadastro `draft` não enfileira trabalho; em produção, só registrar produto legítimo autorizado.
2. Explicit start admits one bootstrap; replaying the same command ID does not duplicate work.
3. Pause prevents new claims and stale execution generations from writing; only after quiescence does settlement acknowledge `paused`.
4. Resume advances generation and rejects old-generation side effects.
5. Stop waits for quiescence and cancels only eligible pending tasks; restart is explicit and idempotent.
6. Reject unauthorized callers, stale versions, invalid commands and concurrent claims.
7. Verify Console actions and errors in authenticated Preview; do not mutate existing production projects for a smoke test.

The isolated PostgreSQL QA covers database invariants without production writes. CI now reruns that QA when runtime/settlement paths change. End-to-end autenticado requer projeto existing legítimo ou greenfield real autorizado; não criar projeto descartável em produção. Unit tests e screenshots não bastam.
