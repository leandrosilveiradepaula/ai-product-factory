# Bloco 1 — entrega integrada e critérios de fechamento (10/11/2026)

Matriz operacional de execução, não certificação. O [plano vinculante](PLANO_CERTIFICACAO_19_CRITERIOS.md) e o certificador independente prevalecem. Nenhum PASS é acrescentado manualmente.

## Baseline reconciliado

- main: 84f6b97d4f2f902ee119a6787cb9800f3fd109d1; merge humano da PR #1327.
- Certificado independente persistido: 10 PASS, 4 PARTIAL, 5 MISSING, product_ready=false.
- PostgreSQL QA da #1327 11/11, validate push passou.
- Aprovados: security/secrets_dependencies; observability_operations/health, traceability, recovery_alerting; test_strategy/unit_integration, regression_gates; documentation/setup_configuration, operations, release_rollback; functional_completeness/requirements_inventory.
- Parciais: product_experience/surface_inventory, responsive, accessibility; functional_completeness/mock_noop_demo_inventory.
- Ausentes: security/authn_authz, data_access_boundaries; product_experience/states; test_strategy/critical_e2e; functional_completeness/critical_journeys.

## Entrega integrada, sem expandir funcionalidade

| Grupo | Prova executável segura | Evidência externa ainda exigida |
| --- | --- | --- |
| Preservação dos 10 PASS | Comparar os 19 critérios persistidos no SHA exato com o certificado anterior; falhar se qualquer PASS cair, mesmo quando o total cresce. Não altera certificado nem promove estado. | Novo certificado persistido no merge SHA real |
| B2 — Runtime/Auth | Reusar negativas efetivamente executadas de Product, Direct, Codex, Release e Console API. Preservar modelos/custos fechados e gate humano. | JWT real, fronteiras entre tenants, ingressos HTTP/broker e isolamento comprovados por avaliador independente com autorização de acesso |
| B3 — Console | Captura autenticada exige 14 telas mobile correspondentes às 14 desktop, acessibilidade, overflow, navegação por teclado, projeto real e ausência de mutação. Contratos adversariais em CI. | Executar browser no deployment/commit correto, avaliar artefato criptografado e matriz completa de loading/error/empty/denied e RBAC |
| B4 — CRM existente | Testemunho read-only do Control Plane, Start OWNER legítimo e estado da jornada. Nunca concede PASS sintético. | Jornada CRM bb14e150-2c7e-423b-8e5d-e211dab6225c está preview_verified e não possui production_release_sha. Exige merge humano legítimo e release observado |
| B4 — Greenfield | Inventário read-only exclui explicitamente o Service Desk aposentado, independentemente do valor histórico is_active. | Produto greenfield genuíno, escopo e Start humanos, implementação, CI, Preview, merge humano e operação comprovados |

Não reabrir histórico terminal do CRM nem iniciar Start sintético. Não usar o Service Desk como greenfield. Não comprar créditos, criar operadores privilegiados, relaxar RLS, chamar modelo pago, fazer merge automático, aplicar migration ou fingir Preview.

## Critério de aceite da revisão única

1. Uma PR integrada para todas as provas seguras, sem mudança na aplicação Console servida ou migrations e sem release automático.
2. Antes de qualquer merge humano: CI completa, QA PostgreSQL isolado e verificações independentes. PR verde não conta como product_ready.
3. Após merge humano: validate push no SHA exato e certificador pós-CI, com relatório persistido e artefatos factory-block1-criterion-delta.json e factory-block1-real-journey-witness.json.
4. Qualquer PASS antigo perdido reprova a auditoria: identificar nominalmente o critério e corrigir a causa, sem compensação pela contagem de outros critérios.
5. 19/19 depende também das provas externas reais de Auth/RBAC e UX, jornada existente CRM até operação e uma jornada greenfield genuína autorizada.

Estas provas não flexibilizam o certificador. Objetivo: avanço legítimo e verificável, não estabilidade apenas aparente do contador.
