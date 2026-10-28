# Contrato de finalização da AI Product Factory — Infodive

## Atualização vinculante — 27/10/2026: Service Desk independente aposentado

**Esta decisão substitui a sequência F6 histórica nas seções 2 e 3 quando houver conflito.** O proprietário definiu que Service Desk é módulo do CRM Infodive, não produto greenfield autônomo. A PR CRM [#201](https://github.com/leandrosilveiradepaula/crm-infodive/pull/201) foi mergeada humanamente (merge SHA `5072e0ea311e27ce4b5e2382e32399deece5adf8`); o schema `service_desk` e as migrations aditivas foram aplicados **no Supabase existente do CRM**, sem substituir Auth, contas ou perfis. O projeto independente `infodive-service-desk` foi parado via controle autenticado da Factory, confirmado no Control Plane em `2026-10-27T17:59:48Z`, `state=stopped`, `version=1`, 0 tarefas ativas. CRM e Factory continuam `running`.

**Não executar a recuperação F6 antiga** do run `52998a8f-b478-46b3-9529-08bea72034f3` / Change Set `60dd6b73-3e98-4da0-bc36-4be6d7562f45`, não reativar o projeto independente, não reutilizar suas credenciais/Preview nem interpretar sua PR #10 como candidata de produção. O registro antigo permanece apenas como evidência histórica de tentativa **não certificada**. A prova de CRM existente continua limitada ao seu escopo real; o Preview de login CRM `c9aaacd28140c9f132a5d8ae2ff250afc823c75c` foi browser-verified nos runs [#40551449688](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/40551449688) e [#40551487676](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/40551487676), **não** é prova autenticada de Service Desk ou de greenfield completo.

**Novo próximo critério:** concluir primeiro as verificações independentes dos seis domínios no SHA corrente; para greenfield, exigir um **alvo legítimo novo, autorizado e diferente do Service Desk modular** antes de qualquer Start. Sem alvo legítimo, registrar F6 como pendente por requisito de prova, não simular PASS nem criar projeto descartável. Não executar modelo pago, migration, deploy ou merge para forçar o encerramento. `product_ready=false` até avaliação independente durável por SHA e cobertura.

---


**Decisão do proprietário: 26/10/2026. Fase atual: ENCERRAMENTO POR EVIDÊNCIAS, não expansão do produto.**

Este documento é a referência operacional para as próximas sessões e agentes que trabalhem na Factory. **Objetivo único:** concluir a plataforma autônoma de ponta a ponta, em vez de acumular correções e PRs sem fechar as provas. Antes de propor qualquer nova implementação, ler este contrato, `AGENTS.md`, `PROJECT_PLAN.md`, `docs/STATUS.md`, `docs/OPERATIONS.md`, `docs/AUTH_ACTIVATION_READINESS.md`, a [matriz de seis domínios](FINAL_CERTIFICATION_MATRIX_20261026.md) e o estado **ao vivo** de GitHub, Supabase e Vercel. Código, dados e evidências atuais prevalecem sobre snapshots ou memórias de conversa.

**Atenção:** este contrato orienta a execução, não certifica provas nem altera automaticamente flags, permissões, orçamento, modelos ou estados. Em caso de conflito entre snapshot abaixo e evidência atual, atualizar o snapshot e conservar os gates. Issues de referência: [#713 — auditoria global](https://github.com/leandrosilveiradepaula/ai-product-factory/issues/713), [#266 — finalização](https://github.com/leandrosilveiradepaula/ai-product-factory/issues/266), [#1068 — greenfield/Direct](https://github.com/leandrosilveiradepaula/ai-product-factory/issues/1068).

## 1. O que significa concluir

A Factory deve demonstrar em **trabalhos reais**, com proveniência íntegra:
`Ideia → Discovery → Product Spec → Plano → Backlog → Roteamento → Implementação → Review → Testes/Evals → Preview verificado → awaiting_release → merge humano → Release observado → Operação`.

Critérios **cumulativos** de saída, sem atalhos:

1. **Projeto existente e greenfield:** uma linhagem real de cada tipo, iniciada por autorização legítima, atravessa as etapas aplicáveis até o resultado final esperado. A prova antiga do CRM em branch de homologação conta **apenas como integração não produtiva**, não como release de produção. Para o greenfield F6, falta comprovar Preview funcional e as etapas posteriores. Não criar projetos sintéticos descartáveis para fabricar PASS.
2. **Código e qualidade:** issue/Start, task, run, Change Set, issue/branch/PR, CI nativa, especialistas, quality gate e SHA do candidato vinculados de forma auditável, sem trocas silenciosas de versão nem reparos artificiais.
3. **Preview e release:** Playwright/browser E2E real no alvo/commit correto quando obrigatório. `Vercel READY`, check verde ou `GET /api/session` 200/401 **não** equivalem a browser PASS. `Preview N/A` só com política explícita e evidência durável por projeto/path. Gate de produção é sempre humano; a Factory **nunca** faz auto-merge e o release observer só reconcilia merge humano realizado.
4. **Resiliência e operação:** incidentes, retries, idempotência, concorrência, budget/quota, pausa/retomada e rollback exercitados em cenários representativos, com evidência atual — sem transformar testes isolados em prova integral de operação.
5. **Seis domínios independentes:** Security; Observability/Operations; Test Strategy; Product Experience (UX, acessibilidade, mobile e feedback); Documentation; Functional Completeness. Cada domínio precisa de atestado independente e rastreável ao SHA/escopo; avaliações anteriores podem ser reutilizadas **quando ainda válidas**, sem executar provas aprovadas novamente.
6. **Fechamento formal:** relatório final com referência de SHA, evidência, escopo, limites, pendências administrativas externas e decisão humana pertinente. `product_ready=true` só se o mecanismo de avaliação durável no Control Plane o comprovar no SHA aplicável; jamais alterar o status por redação ou por CI verde.

**Nenhum percentual inventado:** até haver critérios formalmente atingidos, reportar `comprovado no escopo`, `pendente`, `bloqueado por dependência externa` ou `não aplicável por política`.

## 2. Ponto de partida verificado em 26/10/2026

| Item | Evidência atual e alcance |
| --- | --- |
| GitHub Factory | PR #1117 mergeada humanamente; `main=50c9814cf03aa00799b87619665eaa6df20c3d8f`; [validate pós-merge #40382141869](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/40382141869) **SUCCESS**; 0 PRs abertas na inspeção. |
| Auditor global | [#40382212270](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/40382212270) **SUCCESS** como observador, `product_ready=false`, `unverified_domains=6`, `writes=0`, `paid_calls=0`. **Nenhum domínio declarado certificado** por essa execução. |
| Supabase | Factory `fjplmxfcshhbmzgvyqlm` `ACTIVE_HEALTHY`; 0 gates humanos pendentes, 0 incidentes abertos, 1 operador ativo. Históricos de runs `failed` e `repair_pending` não se tornam automaticamente tarefas acionáveis. |
| Prova 1 | Conclusão de escopo anterior registrada no histórico. Não refazer por padrão. |
| Prova 2 (CRM existente) | [CRM #197](https://github.com/leandrosilveiradepaula/crm-infodive/pull/197) e auditoria [#40211815474](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/40211815474): integração Preview não produtiva validada, **sem** equivaler a release de produção. Não reativar seu Change Set concluído. |
| Prova 3 | Cenários específicos de resiliência/recuperação aprovados; a cobertura operacional integral continua a ser verificada. |
| Greenfield F6 | [Service Desk PR #10](https://github.com/leandrosilveiradepaula/infodive-service-desk/pull/10) aberta, SHA `17edf217dceb0b75bf944e8e1737a0ba92bfb2fc`, CI e deployment Vercel READY; browser E2E falhou em `503 /api/session`. Projeto Vercel específico sem env vars de backend na inspeção; **não** há Preview funcional comprovado nem `awaiting_release`. |
| Recuperação de backend | #1115–#1117 mergeadas; RPC `factory_resume_preview_backend_unavailable_v1` instalada no Supabase Factory (migration `resume_preview_backend_unavailable`, versão `20261026175603`, apenas `service_role`). Isso **não** recupera automaticamente o run histórico nem configura o backend. |
| Console Vercel | Console de produção com deployment `READY` de SHA anterior; builds de commits sem `apps/console/**` foram cancelados intencionalmente, não são falha de produção nem Preview fabricado. |
| Codex/WIF | [#240](https://github.com/leandrosilveiradepaula/ai-product-factory/issues/240) continua dependência administrativa externa da autonomia Codex. API WIF [#250](https://github.com/leandrosilveiradepaula/ai-product-factory/issues/250) é separada; não confundir mecanismos. |

Os valores acima são **fotografia datada**. Verificar novamente antes de qualquer ação; evidência no SHA da PR da documentação não certifica o produto.

## 3. Sequência de encerramento vigente (decisão de 27/10/2026)

**A. Certificar os seis domínios sem gastar ou alterar produção.** Revisar evidência atual por SHA para Security (Auth/RBAC/segredos), Observability/Operations (health/trace/recovery/alerting), Test Strategy (unit/integration/E2E crítico/regressão), Product Experience (mobile/teclado/a11y/loading/sucesso/erro), Documentation (setup/operação/release/rollback) e Functional Completeness (inventário/jornadas). CI e Preview isolados são evidência parcial. Para o procedimento operacional consultar [Release autonomy](RELEASE_AUTONOMY.md).

**B. E2E existente — CRM Infodive.** Só iniciar novo trabalho real quando um operador fizer Start e houver necessidade legítima. Preservar cadeia Start → task/run/Change Set → PR/CI/Preview → `awaiting_release` → merge humano → observação de operação. A Prova 2 anterior integra homologação, não release em produção. Não reprocessar Change Set fechado para fabricar resultado.

**C. E2E greenfield F6 — aguardar alvo novo legítimo.** O Service Desk standalone, sua PR #10, run de 503 e Change Set original são **históricos aposentados**. O antigo run não é recuperável para certificação, mesmo que um backend passe health check. Não iniciar/reiniciar o projeto parado, não criar projeto sintético, não mover credenciais do CRM para o alvo antigo. A prova F6 só pode usar outro produto real e especificamente autorizado, com seus gates. Sem alvo, manter `functional_completeness` pendente: esse domínio não é N/A.

**D. Verificar lacunas remanescentes.** Reutilizar recibos de PostgreSQL isolado, release observado e navegador no escopo correto. A interação de migration da [#692](https://github.com/leandrosilveiradepaula/ai-product-factory/issues/692) ainda exige prova controlada, no navegador, da transição `pending → sucesso verificado`, ou operação real já autorizada; não aplicar migration de teste. Rollback de código e SQL são decisões distintas: `rollback.verified=true` no relatório **não** significa rollback produtivo executado.

**E. Encerrar por evidência independente.** Consolidar run/SHA/escopo verificáveis e registrar na [#713](https://github.com/leandrosilveiradepaula/ai-product-factory/issues/713) e [#266](https://github.com/leandrosilveiradepaula/ai-product-factory/issues/266). `product_ready=true` exige avaliação durável completa no Control Plane; caso contrário indicar pendência ou dependência externa. Merge de produção permanece humano, sem auto-merge.

## 4. Regra contra deriva e fábrica de PRs

- **Próximo trabalho = próximo critério de aceite não comprovado.** Antes de criar issue/PR, registrar: *qual prova concreta está bloqueada? qual evidência já existe? qual defeito de código reproduzido impede a prova? qual teste/reexecução encerrará o problema?*
- **Não abrir PR** para diagnóstico repetido, arrumação periférica, nova abstração ou aperfeiçoamento sem relação direta com um critério de saída. Se for só dependência de ambiente/permissão, registrar e parar *essa trilha*, prosseguindo nas demais provas gratuitas. Não transformar falta de segredos em mais código.
- Corrigir código apenas diante de defeito real e demonstrável, preferindo **uma PR coesa por causa raiz**, com testes negativos e critérios de fechamento. Cinco blocos substanciais são uma preferência de agrupamento, **não** motivo para criar trabalho artificial.
- Não redescobrir nem reexecutar Provas 1/2 concluídas no escopo, Change Sets terminais, runs históricos, um novo projeto descartável, benchmark de 63 perguntas SQL, modelos pagos só para sondagem, deploys Vercel desnecessários ou refazer planejamento.
- Priorizar executor determinístico/Direct; usar agente barato/Codex somente quando o problema exigir. Codex WIF não pode ser inventado e custo pago depende de orçamento real, ledger e autorização.
- **Gates invariáveis:** produção/merge humano, migração de produção autorizada, acesso sensível e segredos, alteração material de requisito, destruição de dados, serviço pago recorrente. Nunca auto-merge no runtime, ampliar RLS pública, esconder custo desconhecido ou entregar tokens ao browser.
- Uma falha de segurança material recém-descoberta pode interromper a sequência; registrar **por que é bloqueante para um critério de aceite** e voltar à mesma prova depois da correção. O objetivo não é congelar segurança, mas evitar loops intermináveis.

## 5. Modelo obrigatório de relatório de continuidade

Em **cada** nova sessão ou depois de merge relevante, comunicar de forma curta:

| Campo | Pergunta que precisa ser respondida |
| --- | --- |
| Baseline | Qual `main`/PR/SHA e CI reais? Há Preview exigido por path e evidência Vercel? |
| Prova alvo | Qual é a **única próxima prova** ou domínio que estamos tentando fechar? |
| Já comprovado | Quais evidências reais são reutilizadas e **não** serão reexecutadas? |
| Bloqueio | Código demonstravelmente defeituoso, ambiente/credencial externa, ou gate humano? |
| Ação executada | O que foi verificado/alterado **agora**, com link para recibo? |
| Conclusão | Critério passou, continua pendente, ou está bloqueado? Qual é a próxima ação objetiva? |

**Se não houver novo defeito de código, não abrir PR. Se houver dependência humana real, pedir a autorização necessária explicitamente, sem inventar outra tarefa.** O objetivo é fechar a Factory e interromper o ciclo de PRs sem progresso verificável.
