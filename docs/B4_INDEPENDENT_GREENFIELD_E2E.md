# B4 — E2E da Factory, sem banco do piloto

O objetivo é certificar a orquestração **da Factory**, não usar a certificação como justificativa para contratar um Supabase para o Dark Channel Studio. O projeto greenfield foi iniciado por operador real; suas exigências de produção continuam pendentes.

O verificador `independent_b4_greenfield_e2e.py` pode promover somente `test_strategy/critical_e2e`. Ele reconsulta fontes privilegiadas e independentes: projeto criado pelo Console, decisão humana, Change Set multiwave, run raiz, SHA/PR originais, avaliações de CI e quality gate, três especialistas, falha real de navegador seguida de recuperação auditada, avaliação real `browser_e2e` com cinco checks e snapshot visual independente. Reconsulta GitHub da Factory para verificar que o workflow Playwright, job e etapa de navegador terminaram com **SUCCESS** no commit ancestral comprovado do certificado. Nenhuma fonte pode vir de JSON fornecido pelo usuário.

**Proibições:** nunca interpretar somente deploy READY, página estática, PASS de teste unitário ou testemunho parcial como produto concluído; não usar a PR #4 para atestar a árvore da PR #2; não criar banco, migrar dados, comprar crédito, lançar produção, emitir merge automático ou alterar estados do Control Plane. Toda falha ou incongruência impede um PASS.

O recibo informa explicitamente `critical_journeys_certified=false`, `greenfield_product_ready_inferred=false`, `production_merge_observed=false`, `production_release_authorized=false`, `writes=0`, `paid_calls=0`. A segunda lacuna, `functional_completeness/critical_journeys`, continua exigindo jornada até gate humano, merge humano, release observado e operação. Em particular, o run original do Studio continua `release_policy_blocked` por `migration_validation` e `rollback_analysis`; este verificador não contorna o DoD.

O workflow pós-CI produz o manifesto de fontes e, imediatamente antes da persistência, reexecuta o mesmo verificador. Se a prova sumir, mudar ou falhar, não há aprovação. Testes negativos cobrem falsificação e deriva de SHA, ausência de fonte, falta de gate humano, recuperação, especialistas e navegador real. O contador correto só pode vir do certificado persistido na `main`.

## Fonte independente para o 19º critério, sem PASS antecipado

A mesma PR inclui `verify_b4_critical_journeys`. Ela só gera uma segunda `VerifiedCriterionEvidence` quando a testemunha E2E acima **continua válida**, o auditor CRM V2 independente atesta a jornada existente e o Control Plane comprova simultaneamente:

1. O run do greenfield está `merged` e a release report está `released` com SHA original do PR, SHA de merge e `released_by=observed_manual_merge`.
2. O Change Set está `completed`, vinculando o run ao SHA e ao recibo `release.observed=true`.
3. Um audit event `release.human_merge_observed` mantém o SHA exato do merge humano, distinto da candidata original.
4. A Factory observou a operação em `factory_project_state_snapshots` (run ligado, `observed_stage=operations`, `source_status.release=merged`, `evidence={type:human_release,merge_sha:...}`) e no manifesto atualizado do projeto.

Se faltar **qualquer** dessas provas, `functional_completeness/critical_journeys` permanece missing. O verificador não executa merge, deploy, migration, criação de Supabase ou inferência de PASS. A revalidação acontece uma vez na coleta e outra no certificador, antes da escrita durável. A linhagem do PR de origem continua explícita mesmo quando o run passa a referenciar o SHA de merge, evitando perder o E2E comprovado.
