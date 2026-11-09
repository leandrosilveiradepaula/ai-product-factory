# Bloco 1 — Plano vinculante de certificação dos 19 critérios da AI Product Factory

**Decisão do proprietário: 09/11/2026. Prioridade única: concluir a certificação da própria Factory; não expandir funcionalidades ou iniciar produtos paralelos para inflar a contagem.**

Este plano complementa [AGENTS.md](../AGENTS.md), [contrato de finalização](FINALIZATION_EXECUTION_CONTRACT.md), [matriz de seis domínios](FINAL_CERTIFICATION_MATRIX_20261026.md) e [issue #713](https://github.com/leandrosilveiradepaula/ai-product-factory/issues/713). Deve ser lido **antes de criar issues, branches, PRs, Starts ou novos workflows**. O código e as evidências atuais prevalecem sobre qualquer snapshot deste documento.

## 1. Objetivo e definição de conclusão

Certificar, em prova independente **executada, durável e vinculada ao SHA atual**, os 19 critérios dos seis domínios: Security (3), Observability/Operations (3), Test Strategy (3), Product Experience (4), Documentation (3) e Functional Completeness (3).

**Conclusão:** 19/19 critérios com `passed`, todos os seis domínios aprovados e `product_ready=true` **calculado e persistido pelo certificador no Control Plane**, após revalidar fontes. `validate` verde, workflow `SUCCESS`, um manifesto local, evidência `partial` ou texto deste plano **não** representam essa conclusão.

A autonomia completa inclui ainda o contrato cumulativo de jornadas reais [existente e greenfield](FINALIZATION_EXECUTION_CONTRACT.md): Start legítimo, descoberta/especificação/plano/backlog, roteamento, implementação, review, testes/evals, Preview realmente verificado quando aplicável, `awaiting_release`, **merge humano**, release observado e operação. A prova greenfield não pode ser inventada para fechar lacunas; quando inexistente, deve ficar explicitamente pendente como dependência real.

## 2. Baseline e atualização obrigatória

- Em 09/11/2026, a última certificação **durável consultada** era do SHA `41f1f9716c2cc127d9630e69167b1b71043494e8`: **9 passed / 3 partial / 7 missing**, `product_ready=false`, certificado `d1991fd4-423a-4bc5-bbb8-2dab0bb529d8`.
- A PR [#1313](https://github.com/leandrosilveiradepaula/ai-product-factory/pull/1313) foi mergeada humanamente em `c5f1f36e5312e7c7d664a6b41d95d5cb06041316`. O `validate` de push [#42666745860](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/42666745860) passou; o certificador pós-CI [#42666843470](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/42666843470) estava **em andamento** na última verificação. **Não contabilizar** um décimo PASS antes do recibo persistido.
- Antes de **cada bloco**, buscar em tempo real: `main` SHA e último `validate` push + checks, `factory_product_readiness_certifications` no Supabase `fjplmxfcshhbmzgvyqlm` (estado, SHA, 19 células, motivos e prova), runs de scheduler/Control Plane, e Vercel/Console **somente** quando houver caminho que o requeira. Não presumir que os números acima ainda sejam atuais.
- Comparar sempre o certificado **do SHA efetivo** com o anterior; se um PASS regredir, investigar antes de avançar. O recibo do job pós-CI deve estar **persistido**, não somente coletado.

## 3. Quatro blocos executáveis (na ordem)

Os blocos são **agrupamentos de prova**, não autorização para ampliar o produto. Quando um critério já estiver `passed` e sua evidência permanecer válida, **não reexecutá-lo** desnecessariamente. Só passar ao bloco seguinte após registrar resultado e bloqueios do anterior; trabalhos independentes podem ser agrupados em uma PR maior.

| Bloco | Critérios não aprovados no baseline | Verificação de aceite, sem atalhos | Meta condicional |
| --- | --- | --- | --- |
| **B1 — Inventário vinculante** | `functional_completeness/requirements_inventory` (`missing`) | Confirmar que #1313 produziu atestado independente no SHA **do merge**: 19 critérios ligados ao ciclo real, arquivos e testes comparados byte a byte à árvore Git, CI push exata, gaps explicitados, dupla verificação e persistência. Um inventário completo **não** aprova implementação ou jornadas. | 10/19 |
| **B2 — Segurança + runtime** | `functional_completeness/mock_noop_demo_inventory` (`missing`); `security/authn_authz` e `security/data_access_boundaries` (`missing`) | Provar, em testes negativos e execução isolada, fronteiras de **todos** os entrypoints relevantes (não só import closure da CLI), que `mock/noop/demo/dry_run` não autoriza execução, gastos ou release reais. Exercitar Auth/RBAC e isolamento entre operadores/tenants, acesso negado, RLS e broker/REST/RPC privilegiados sem abrir políticas ou expor segredos. Provas reais de escopo e SHA, não mera inspeção estática. | 13/19 |
| **B3 — Console integral** | `product_experience/surface_inventory`, `responsive`, `accessibility` (`partial`); `states` (`missing`) | Matriz completa de telas e fluxos por papel, Playwright autenticado no host/commit corretos, mobile e desktop, teclado/foco/semântica/acessibilidade, erros, carregamento, vazio, acesso negado, pausa/retomada e feedback de gates. Captura antiga (#42439592059) é evidência **parcial** e não atesta UX completa, RBAC ou E2E. Exigir Preview real para `apps/console/**`; Preview N/A só com política explícita e recibo durável. | 17/19 |
| **B4 — Jornada crítica real + E2E** | `functional_completeness/critical_journeys` e `test_strategy/critical_e2e` (`missing`) | Usar CRM Infodive como piloto existente **somente** em Start/trabalho legítimo, sem reabrir runs/Change Sets terminais. Vincular issue/Start, especificação, task/run/Change Set, branch/PR, últimos CI/checks, qualidade, Preview/browser no SHA, `awaiting_release`, merge humano, release observado, health/alertas/operação. Cobrir falhas/recovery representativos. Prova greenfield real fica pendente de alvo genuíno e autorização própria, nunca projeto fictício. | 19/19 |

**Metas 10/13/17/19 são cenários condicionais**, não status, prazos ou promessas de aprovação. Não converter `partial` em `passed` por decisão editorial ou pelo desejo de chegar a 19.

## 4. Protocolo de execução por bloco

1. **Reconciliar** `AGENTS.md`, `PROJECT_PLAN.md`, `docs/STATUS.md`, `docs/OPERATIONS.md`, `docs/AUTH_ACTIVATION_READINESS.md`, este plano, GitHub Actions, Control Plane e Vercel quando aplicável. Tratar as seções de 26/10 como histórico, não como estado atual.
2. **Escolher a primeira célula ainda não comprovada** dentro do bloco corrente. Escrever critério de aceite observável, fonte independente, SHA e teste negativo. Investigar falha reproduzível antes de tocar no runtime.
3. **Executar trabalho substancial** sem pedir "prossiga" para cada microtarefa: issue/branch → implementação de prova ou correção estritamente necessária → testes → PR → CI, QA PostgreSQL e verificações pertinentes. Preferir uma entrega integrada por bloco, não várias PRs cosméticas.
4. **Não fazer merge de produção** nem autorizar migration, compra, ampliação de acesso ou bypass de gates. Somente parar na dependência humana real; indicar **uma ação exata** e o link.
5. **Após merge humano**, observar push `validate` no merge SHA, certificador pós-CI, segundo verificador, resultado persistido e 19 células no Supabase. Se timeout/erro, corrigir a causa e não declarar PASS. Se falhar, continuar diagnóstico e regressões do **mesmo** bloco.
6. **Atualizar o status** do bloco com SHA, link de CI/recibo, estados por célula e bloqueio real. Iniciar o próximo bloco autonomamente quando possível, sem recontar todo o histórico da Factory.

## 5. Proibições e limites que impedem desvios

- **Não expandir escopo** para CRM/Service Desk, Agente Financeiro, um produto TCO ou outro projeto, exceto quando uma **jornada real autorizada** for necessária como prova da Factory. Não ressuscitar o Service Desk independente (`stopped`), criar piloto descartável ou Start sintético.
- Não criar PRs só para elevar a contagem, suavizar certificador, mudar `missing` para `partial` sem evidência, desabilitar quality gates, mascarar falhas, declarar que um status verde comprova release/UX/segurança, nem inventar Preview.
- CI verde + qualidade + Preview verificado **nunca** autorizam merge em produção. Runtime sem auto-merge; release observer somente registra merge humano já ocorrido.
- Não habilitar `FACTORY_PRIMARY_MODEL_ENABLED`, comprar créditos/saldo, executar chamadas pagas de teste, benchmark SQL de 63 perguntas ou modelo/Codex sem justificativa de custo. Ordem: ferramenta determinística → executor direto → agente econômico → Codex seletivo.
- Não expor token no browser, relaxar RLS, ampliar ACL, aplicar migration produtiva, destruir dados ou fazer rollback irreversível sem gate explícito. `FACTORY_GITHUB_TOKEN` é obrigatório para cross-repo.
- Não repetir resultados históricos comprovados nem insistir em workaround não validado; usar recibos anteriores apenas dentro do **escopo e validade** que suas fontes permitem.

## 6. Modelo obrigatório de comunicação e continuidade

Cada atualização ao proprietário deve responder sucintamente:

1. **Estado real:** `main` SHA, certificado persistido do mesmo SHA? `n passed / n partial / n missing`; `product_ready`.
2. **Bloco e células:** qual critério exato está sendo fechado e o teste/prova executado.
3. **Resultado verificável:** links de issue/PR/workflow/recibo, conclusão de CI **e**, quando disponível, de avaliação independente.
4. **Bloqueio e próxima ação:** o que já pode ser executado autonomamente; pedir intervenção humana **apenas** por gate real, com instrução única e clara.

**Instrução para iniciar novos chats/agentes:** abrir este documento; consultar as fontes de verdade atuais; retomar **o primeiro critério ainda não certificado** no bloco correspondente; executar tudo que é seguro sem perguntas repetitivas. Se o usuário disser "prossiga", isso significa **continuar o plano**, não escolher outro projeto. Se houver bloqueio real, registrar o motivo verificável; não substituir a prova por narrativa.

**Saída final:** certificado durável 19/19 no SHA atual, cobertura integral dos seis domínios, controle de custo e de segurança preservados, jornadas reais demonstradas dentro dos gates e documentação operacional reconciliada. Se um requisito externo permanecer pendente, reportar `not_ready` e qual requisito é, sem inventar um PASS.
