# UX/UI #1506 — recuperação por checkpoint do planejamento vazio

A solicitação autenticada criou a run `6d16d422-8b7b-41cf-b7ea-27f73fd49700`: `reconciliation` e `gap_analysis` têm recibos persistidos; `planning` terminou com `planning_non_actionable`.
A admissão de código e tarefas de auditoria foi corrigida na PR #1507 (merge humano, SHA `62ab227a058cab86c5d780c1dfe7a000c52b8b7a`).

Esta migration é **inerte até autorização de produção separada**. A função existente `factory_resume_failed_product_planning_v1` mantém a recuperação por orçamento e passa a aceitar, somente para `project_kind=platform`, pedido autenticado `factory-console` e evidência tipada de planejamento vazio. Não usa `factory_retry_failed_run`.

A segurança da retomada exige OWNER #1055, projeto e run exatos, controle `running` e mesma geração, histórico de duas etapas persistido na mesma run, snapshot válido, request e manifesto sem drift, nenhum trabalho concorrente, idempotência e ACL `SECURITY INVOKER` com execução exclusiva para `service_role`. Antes de modelo pago o worker exige **novo SHA do GitHub com issue explicitamente vinculada e código inspecionado**, bloqueando replay no mesmo SHA.

**Rollout:** CI isolado PostgreSQL → merge humano → autorização separada da migration → aplicação no Supabase → reconsulta ACL e function body → comentário OWNER na issue operacional #1055:

```
/factory-resume-planning run=6d16d422-8b7b-41cf-b7ea-27f73fd49700
```

O comando enfileira somente uma etapa `planning`. Não habilita gasto fora do ledger, não invoca modelo para sondagem, não publica produção nem conclui a auditoria sem relatório real. Verificar run, relatório versionado, Preview se aplicável e gate de merge humano.
