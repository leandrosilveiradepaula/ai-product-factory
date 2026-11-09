# MEMORY.md — continuidade operacional da AI Product Factory

**Decisão vigente: 09/11/2026. Escopo único: concluir a certificação real da Factory nos 19 critérios, sem novos produtos ou expansão funcional para elevar a contagem.** Este arquivo é memória de continuidade para agentes e novos chats. Ele **não** substitui o código, o Control Plane, os critérios do certificador ou o contrato de finalização.

## Leia antes de executar qualquer tarefa

1. [AGENTS.md](AGENTS.md) e [Plano vinculante dos 19 critérios](docs/PLANO_CERTIFICACAO_19_CRITERIOS.md).
2. [Contrato de finalização](docs/FINALIZATION_EXECUTION_CONTRACT.md), [PROJECT_PLAN.md](PROJECT_PLAN.md), [STATUS](docs/STATUS.md), [OPERATIONS](docs/OPERATIONS.md), [AUTH readiness](docs/AUTH_ACTIVATION_READINESS.md) e [matriz](docs/FINAL_CERTIFICATION_MATRIX_20261026.md).
3. Reconciliar fontes **atuais**, nesta ordem: GitHub `main`, última CI/QA no SHA, último certificado **persistido** de `public.factory_product_readiness_certifications` no Supabase `fjplmxfcshhbmzgvyqlm`, evidência de filas/runs/gates, e Vercel apenas quando Preview/Console for aplicável.

**Não use os números deste arquivo como estado atual sem essa reconciliação.** Nunca declarar `passed` a partir de uma PR mergeada, CI verde ou manifesto parcial.

## Onde estamos — snapshot histórico datado

- PR [#1313](https://github.com/leandrosilveiradepaula/ai-product-factory/pull/1313) mergeada em `main=c5f1f36e5312e7c7d664a6b41d95d5cb06041316` em 09/11/2026. `validate` de push [#42666745860](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/42666745860) aprovado; certificação independente [#42666843470](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/42666843470) **ainda em andamento** na consulta de criação deste plano. Consultar novamente, não presumir conclusão.
- Último certificado **durável comprovado naquela consulta**, para o SHA anterior `41f1f9716c2cc127d9630e69167b1b71043494e8`: **9 passed, 3 partial, 7 missing**, `product_ready=false`; ID `d1991fd4-423a-4bc5-bbb8-2dab0bb529d8`. É histórico, **não certifica a main posterior**.
- PR [#1314](https://github.com/leandrosilveiradepaula/ai-product-factory/pull/1314): plano/continuidade documental. O merge de produção é gate humano; não antecipar ou considerar merge como certificado.

## Execução obrigatória: quatro blocos, nenhum desvio

| Bloco | Critérios a comprovar | Política de prova |
| --- | --- | --- |
| **B1 — Inventário** | `functional_completeness/requirements_inventory` | Verificar atestado independente da #1313 no SHA do merge e recibo **persistido**. Inventário não comprova jornadas. |
| **B2 — Segurança/runtime** | `functional_completeness/mock_noop_demo_inventory`; `security/authn_authz`, `data_access_boundaries` | Testes efetivos e negativos em entrypoints, Auth/RBAC, isolamento, RLS e broker; simulações jamais acionam execução real. |
| **B3 — Console** | `product_experience/surface_inventory`, `responsive`, `accessibility`, `states` | Playwright real autenticado, desktop/mobile, teclado/foco, estados críticos, erros, espera, acesso negado; Preview exato quando requerido. Captura histórica é `partial`, não PASS. |
| **B4 — E2E/jornada** | `functional_completeness/critical_journeys`; `test_strategy/critical_e2e` | Jornada legítima existente CRM e, para o requisito cumulativo greenfield, apenas alvo real/autorizado; Start → especificação → PR/CI/Preview → `awaiting_release` → **merge humano** → release observado → operação. |

Metas **10/13/17/19** são apenas cenários condicionais. Provas que já são válidas e executadas devem ser **reutilizadas**, não repetidas por rotina. Se houver regressão, investigar primeiro.

## Restrições que não podem ser esquecidas

- **Não sair do Bloco 1** e não transformar a solicitação "prossiga" em novo escopo. CRM é somente piloto de prova de autonomia, não foco de desenvolvimento separado. Service Desk standalone foi aposentado; não o reativar nem criar projeto descartável/Start sintético.
- Preferir **blocos substanciais**, correção da causa raiz e testes com evidência real, não PRs cosméticas. Se não há defeito/prova nova, não mudar código para forçar 19/19.
- No runtime, **sem auto-merge**. CI + quality + Preview não autorizam produção; parar em `awaiting_release`; release observer só reconcilia merge humano.
- Não aplicar migrations de produção, relaxar RLS, expandir acesso sensível, destruir dados, comprar saldo/créditos ou habilitar `FACTORY_PRIMARY_MODEL_ENABLED` sem autorização real. Não rodar benchmark de 63 perguntas do Agente SQL nem chamadas pagas apenas para testar.
- `FACTORY_GITHUB_TOKEN` explícito para outro repositório; credenciais jamais no Console/browser. Codex só executor seletivo, Python é orquestrador principal.
- Preview N/A **somente** se houver política explícita e evidência durável. Preview é fail-closed por padrão. Não inventar deployment.

## Como reportar e retomar

Ao responder ao proprietário ou iniciar novo chat: apresentar **SHA**, certificado **persistido no mesmo SHA** (ou dizer que não há), contagem **passed / partial / missing**, bloco/critério em execução, link de prova/CI e **apenas uma ação humana** quando houver gate real. Se a tarefa for segura, **executá-la**, sem pedir repetidamente permissão para prosseguir.

**Regra de saída:** somente afirmar 19/19 quando as 19 células e os seis domínios estiverem `passed` e `product_ready=true` estiver comprovado por certificação atual, independente e durável no Control Plane. Caso contrário: `not_ready` com motivo explícito.

**Nota de nomenclatura:** este `MEMORY.md` descreve a continuidade **da Factory**. [docs/PROJECT_MEMORY.md](docs/PROJECT_MEMORY.md) descreve a memória versionada de **cada produto gerenciado** pela Factory (arquivos `.factory/`); não confundir as duas coisas.
