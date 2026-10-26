# Contrato de finalização da AI Product Factory — Infodive

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

## 3. Sequência de encerramento — seguir nesta ordem

**Passo A — Tirar o bloqueio real do greenfield do caminho.** Reconciliar que o Service Desk será **módulo do CRM Infodive**, não construir produto/infraestrutura paralelos por inércia. Escolher um Preview funcional *legítimo*, alinhado ao produto integrado e com permissão de acesso. Provisionamento de backend, Auth, segredos e eventual ampliação de acesso exigem decisão humana apropriada, **não** cópia automática de credenciais do CRM ou novas compras. Enquanto o ambiente estiver bloqueado, continuar apenas provas independentes possíveis, sem criar outra PR sobre o mesmo 503 sem defeito novo e comprovado.

**Passo B — Fechar uma linhagem F6 real.** Após configurar um backend autorizado e verificar a origem:
- para o run histórico `52998a8f-b478-46b3-9529-08bea72034f3` / Change Set `60dd6b73-3e98-4da0-bc36-4be6d7562f45`, só usar o procedimento de [recuperação](PREVIEW_BACKEND_RECOVERY.md) já versionado, com preflight fresco, PR/SHA/epoch/CI exatos e limites da RPC, **sem** replay de Product Stage;
- executar um **novo browser E2E** no candidato real, registrar resultado, repetir só a etapa necessária em caso de falha, até `awaiting_release`;
- merge que publicar produção só por humano; release observer registra o merge real e acompanha estado de operação. Se o alvo de teste não representar produção, documentar o escopo e **não** fabricar uma release para fechar caixa.

**Passo C — Certificação dos seis domínios.** Com as evidências anteriores e um inventário de cobertura por SHA, testar somente lacunas remanescentes: Auth/RBAC/tenant/secrets; observabilidade/incidente/recovery/rollback; jornadas negativas e qualidade; mobile/teclado/acessibilidade/feedback de ações longas (acompanhar [#692](https://github.com/leandrosilveiradepaula/ai-product-factory/issues/692)); runbooks de setup/incidente/release/rollback; completude funcional greenfield/existing e capacidade seletiva Codex **quando** a autenticação oficial for autorizada. Não usar WIF como único critério de prontidão nem alegar Codex E2E sem prova.

**Passo D — Encerrar, não expandir.** Atualizar evidência independente por domínio no SHA atual, reconciliar [#713](https://github.com/leandrosilveiradepaula/ai-product-factory/issues/713) e [#266](https://github.com/leandrosilveiradepaula/ai-product-factory/issues/266), atualizar `docs/STATUS.md`/`docs/OPERATIONS.md` e publicar declaração final transparente de produto `ready` ou de **dependências externas explicitamente pendentes**. Não chamar de 100% pronta uma Factory que só passou nas partes testadas.

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
