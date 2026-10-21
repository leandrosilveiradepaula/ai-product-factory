# Recuperação de prontidão de releases humanos legados

## Objetivo e escopo

Este procedimento corrige exclusivamente a **representação de evidências** de um release já mergeado por humano, que foi gravado por múltiplas chamadas REST na versão antiga do observer. Um `project.state.reconciled_after_release` legado podia existir mesmo quando `factory_project_state_snapshots.gaps=[]` e `manifest.product_readiness_followup` não havia sido persistido. A nova rotina NÃO promove `product_ready`, reexecuta código, cria um projeto, faz merge, Preview, CI, chamadas pagas, ou reabre uma run.

No checkpoint 21/10/2026, a release Factory #997 está nesse estado; a release do Service Desk #7, mergeada **antes** de quality/Preview/release gate, está bloqueada legitimamente e não é elegível. Este é um mecanismo genérico, independente do nome dos projetos.

## Cinco componentes

1. **Admissão transacional:** a RPC `factory_pending_legacy_release_readiness_v1` retorna só o último release que coincide com `manifest.last_release`, projeto ativo `operations`, `running`/generation positiva, run merged, report released e `release.human_merge_observed` no mesmo run/SHA; exige que não exista outro report released mais recente. Se o manifesto já tem o followup válido **e** snapshot válido com os seis domínios, não é elegível.
2. **Atomicidade:** `factory_reconcile_latest_legacy_release_v1` tranca controle antes do projeto (compatível Pause), confere o último release e chama a RPC atômica `factory_reconcile_observed_release_v1`; grava o evento `release.legacy_readiness_backfilled` apenas quando houver correção. Não altera `released` nem `merged`.
3. **Revisão fail-closed:** inconsistência permanente gera `release.legacy_readiness_needs_review` via `factory_defer_legacy_release_readiness_v1`. Ausência de banco/rede permanece retryable; novo lançamento ou projeto parado não é reclassificado.
4. **Worker Python:** `runtime_cli --mode legacy-release-readiness-repair --batch-items 4` seleciona por UUID ordenado, valida página inteira antes de qualquer efeito, limita até quatro projetos por wake e nunca chama model provider. A migration ausente produz `blocked_migration_not_applied`, sem fallback.
5. **Evidências:** `tests/test_legacy_release_readiness_recovery.py` verifica os contratos; `scripts/verify_atomic_project_release_postgres.py` usa PostgreSQL 16 efêmero para executar as duas migrations e comprovar isolamento, replay, revisão, idempotência e rollback.

## Rollout, gates e não-ação

- **Antes de merge**: revisar migration e executar CI em SHA exato. Preview da Factory é N/A se `apps/console/**` não mudou; não criar Vercel deployment.
- **Produção**: a PR deve ser mergeada por humano e a migration `20261021135000_recover_latest_legacy_release_readiness.sql` aplicada somente após autorização específica. Nunca executar `supabase db push` globalmente: os IDs MCP não coincidem com timestamps Git.
- **Após migration**: confirmar versões do histórico, três RPCs `SECURITY INVOKER`, grants somente `service_role` e seleção read-only. Observar o próximo scheduler real; conferir audit `release.legacy_readiness_backfilled` e novo snapshot com seis `global_readiness_evidence_required`. O estado global deve permanecer `not_assessed` até auditoria independente.
- **Se houver erro**: não atualizar manualmente `factory_projects`, `factory_runs`, `factory_change_sets`, snapshots ou auditoria. Consultar evidence sanitized e `needs_review`, preservar release antigo e abrir correção em código.
- **Rollback**: desabilitar o passo agendado em nova PR/release humano. A migration cria somente funções novas, sem alterar dados por si; não apagar registros de auditoria ou snapshots históricos na reversão.

Todos os testes deste bloco evitam chaves e chamadas pagas.
