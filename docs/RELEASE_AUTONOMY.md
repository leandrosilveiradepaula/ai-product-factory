# Release, incidentes e rollback — procedimento vigente em 27/10/2026

Este documento é um contrato de verificação, não autorização de publicação, migration ou rollback. Consultar [Contrato de finalização](FINALIZATION_EXECUTION_CONTRACT.md) e [Operations](OPERATIONS.md).

## Preflight e gate de produção

1. Validar Start e linhagem projeto/task/run/Change Set, branch, PR, candidate SHA e controles de projeto ativo; nunca retomar um run aposentado ou de projeto stopped.
2. Exigir último CI nativo `pull_request` bem-sucedido no SHA final, review, especialistas e quality gate. Se o caminho exigir Preview, verificar deployment do projeto exato READY e browser E2E no commit candidato. Sem `apps/console/**`, Preview N/A somente por política explícita e recibo durável; status de Vercel `CANCELED` não equivale a READY.
3. Confirmar custos reais, orçamento/ledger, acesso e migrations; desconhecido ou inconsistente bloqueia. `awaiting_release` não autoriza merge.
4. O operador humano revisa e faz merge de produção. O runtime nunca faz auto-merge; o release observer **somente observa** o PR merged, merge SHA e operação real, mantendo auditoria durável.
5. Após merge humano, verificar health, filas, incidentes, custo, releases e alertas; uma avaliação do produto inteiro requer atestado independente dos seis domínios no SHA correto.

## Rollback de código: decisão humana separada

1. Guardar incident ID, sintomas, projeto, deploy, PR, SHA de merge e evidência de impacto; investigar se é regressão, falha de quota ou Preview antes de agir.
2. Planejar um PR de reversão/revert revisável; nunca reescrever main, forçar ref, apagar auditoria, contornar gates ou fazer rollback de produção implicitamente.
3. Rodar CI, quality e Preview/browser aplicáveis no **novo SHA de reversão**. Solicitar decisão humana para o merge da reversão e confirmar que o release foi observado e o serviço recuperou health.
4. Preservar histórico de falhas; alertas só encerram depois que sua condição real desaparece. Não inferir reversão executada da existência de um plano.

## Migrations, efeitos em dados e acesso

- Aplicar ou reverter SQL em produção exige autorização humana independente, revisão da migration exata, backup e plano de restauração. Merge de código não é aprovação de SQL.
- Preservar RLS fail-closed, funções service-role-only, sem secrets no navegador. Não executar `supabase db push` indiscriminado nem descartar dados para fabricar teste.
- Confirmar versões instaladas e grants após qualquer operação real aprovada; sem prova, bloquear. Reversão de schema e de código são operações diferentes.

## Limite da evidência

- QA PostgreSQL isolada prova rollback **transacional**, não rollback produtivo de aplicação ou de schema.
- Relatórios existentes com `rollback.verified=true` e `rollback.required=false` indicam política/viabilidade, **não** execução de rollback em produção.
- O registro mínimo inclui identidade de projeto/run/PR, candidate SHA, CI, política Preview, E2E, decisão humana, merge SHA, release observer, incidente e resultado observado.
- Sem incidente real e aprovação, manter a lacuna explicitamente pendente; nunca executar rollback experimental em produção. `product_ready=false` até auditoria durável completa.
