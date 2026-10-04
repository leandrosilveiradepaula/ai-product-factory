# Plano do Projeto - AI Product Factory

## Visao

Construir uma fabrica de desenvolvimento na qual o usuario descreve o produto, responde ao discovery inicial e, a partir dai, a fabrica conduz o desenvolvimento quase autonomamente ate um ambiente validavel.

## Resultado esperado

O usuario deve conseguir iniciar com algo como:

> Quero um sistema que faca X.

A fabrica conduz discovery, especificacao, planejamento, implementacao, review, testes/evals, preview e release, interrompendo apenas em decisoes humanas reais ou gates de risco.

## Fases

### F0 - Fundacao
- [x] Arquitetura inicial.
- [x] Project Manifest.
- [x] State machine.
- [x] Codex Policy Engine.
- [x] Human Gate Policy.
- [x] Prompts dos papeis.
- [x] CI da propria factory.

### F1 - Control Plane
- [x] Repositorio `ai-product-factory`.
- [x] Supabase dedicado.
- [x] Schema seguro + RLS/server-side boundary.
- [x] Persistencia de projects/tasks/runs/decisions.
- [x] Ledger de ferramentas e Codex.
- [x] Adapter Supabase server-side.
- [x] Registro real de execucoes no control plane.

### F2 - GitHub Autonomous Loop
- [x] Adapter GitHub REST server-side.
- [x] Criar/ler issues.
- [x] Criar branch.
- [x] Persistir plano tecnico.
- [x] Criar commits atomicos e PR.
- [x] Ler CI.
- [x] CI failure evidence.
- [x] Bounded auto-repair.
- [x] Verified Preview para em `awaiting_release`; merge de producao e exclusivamente humano.
- [x] Release follow-up observa o merge humano, registra evidencia e fecha a issue depois da acao humana.

### F3 - Runtime de Desenvolvimento
- [x] Direct Executor para mudancas pequenas/medias.
- [x] Roteador Direct vs Codex.
- [x] Worker Codex fail-closed: claim atomico, checkout isolado, limites de saida, ledger de invocacao e job OIDC/WIF inerte sem readiness.
- [x] Fallback temporario de Codex manual: handoff duravel em GitHub Issue, PR identificado por marcador de run e retomada automatica em CI sem armazenar credencial humana.
- [x] Provider-neutral Model Executor.
- [x] Budget por tarefa para modelo principal e Codex.
- [x] Pipeline Engine ponta a ponta.
- [x] Project Memory versionada.
- [x] Review/evaluation quality gates.
- [x] Provider OpenAI Responses implementado e ativado via API key com billing real comprovado, budget total de US$ 4.00, reserva de US$ 0.50 e ledger fail-closed por custo.
- [x] OpenAI API WIF implementado no runtime e GitHub (`openai-api`); GitHub OIDC real foi validado. O exchange OpenAI continua bloqueado por mapping administrativo incompatível com o subject imutavel (`invalid_grant`, issue #250), mas agora e hardening de autenticacao externo e nao bloqueia o caminho operacional API key.
- [ ] Provider real do Codex/ChatGPT entitlement (Factory suporta WIF preferencial e fallback oficial `CODEX_ACCESS_TOKEN`; falta criar/configurar a credencial e validar preflight antes de habilitar o worker. WIF beta continua issue #240).

### F4 - Testes, Evals e Preview
- [x] CI deterministico por projeto via manifest.
- [x] Contrato de evals obrigatorios/opcionais.
- [x] Evidence bundle.
- [x] Preview adapter Vercel com configuracao por projeto e fail-closed.
- [x] Browser/E2E command adapter com evidencia estruturada e URL exata.
- [x] Verified Preview runtime com evidencia duravel e fronteira `awaiting_release`.
- [x] Release observer por plataforma GitHub, sem capacidade de merge automatico.

### F5 - Piloto Agente SQL Financeiro — adiado por decisao do usuario
- [x] Onboarding de `agente-sql-langgraph`.
- [x] Importar comando real de regressao: `python scripts/check_all.py`.
- [x] Importar CI real: `Offline validation`.
- [x] Preservar n8n como caminho oficial.
- [x] Preservar LangGraph como offline shadow.
- [x] Registrar projeto no control plane.
- [x] Escolher proxima linha semantica de planned_filters: suporte generico offline a bindings multi-valor (`IN`) concluido no piloto, sem ativacao semantica.
- [ ] Benchmark de 63 perguntas permanece postergado por decisao registrada no projeto.
- [ ] Primeira tarefa funcional nova executada integralmente pela factory.

### F6 - Greenfield Test
- [x] Validar lifecycle greenfield offline sem chamadas externas.
- [x] Validar que fluxo low-risk pode chegar autonomamente ate Preview; producao permanece sempre sob gate humano.
- [x] Validar greenfield offline com 0 chamadas de Codex/modelo.
- [x] Revisar gates e ampliar autonomia ate o limite seguro: non-prod low-risk autonomo; apenas riscos definidos e producao exigem humano.

### F7 - Factory Finalization
- [x] Definir matriz formal de aceitacao da Factory.
- [x] Criar acceptance gate executavel cobrindo lifecycle, roteamento, Preview, release, operacao, custos e invariantes de seguranca.
- [x] Adicionar check dedicado `factory-acceptance` ao CI da propria Factory.
- [x] Reconciliar migration do worker Codex entre Git e Supabase de producao.
- [x] Separar completude interna de ativacao administrativa de providers externos.
- [x] Validar Control Plane real por smoke transacional com rollback.
- [x] Implementar redesign operacional do Console com dados reais do Control Plane.
- [x] Centralizar design tokens, tipografia, cores semanticas e primitivas reutilizaveis do Console.
- [x] Validar CI/factory-acceptance no GitHub Actions: janela publica temporaria habilitou runners hospedados; `validate` run #1041 passou e o rerun exato do candidato do Console tambem passou.
- [x] Validar build do Console por Preview exato Vercel do candidato `10f593d7d169d30fe5048eac9d98a94b8be1e151` (deployment `dpl_CNFAo32v4DHzjCzgmx1xZUsKFkwX`, `READY`).
- [x] Validar browser/Playwright evidence em Preview exato protegido: GitHub OIDC Trusted Source foi configurado na Vercel e o candidato final pt-BR do PR #269 (`505c712864950d94638c874d8e267531fb544d62`, deployment `dpl_J9kneq8tf9bouJ3StBPyh4UNd7GX`) passou `page_load`, `http_status`, `body_visible`, `expected_text` e `console_clean` no run `36376673624`. O corpo observado confirmou a navegacao principal em portugues. O candidato historico `10f593...` permanece apenas como divida arquivistica; nao e a evidencia do release atual.


### F8 - Orquestracao multiagente adaptativa
- [x] Agent Registry configuravel com perfis, capabilities, ferramentas, budgets e concorrencia.
- [x] Scheduler com assignments atomicos, scope locks e fan-out de workers especializados.
- [x] Execution Team Plan deterministico derivado do engineering plan e do Agent Registry, sem chamada adicional de modelo.
- [x] Selecao explicavel do menor conjunto de especialistas, workers planejados, ondas, exclusoes e blockers.
- [x] Persistencia versionada do Execution Team Plan e audit trail no Control Plane.
- [x] Visualizacao da equipe planejada nos detalhes do projeto.
- [x] Lanes independentes read-only para Security Review, QA/Evals e Operations, com SHA exato, lease/retry bounded, findings estruturados e gate antes do Preview.
- [x] Change Set com work units isoladas por onda, source SHA imutavel, integration branch, conflito de arquivos fail-closed e um unico PR candidato de release.
- [x] Telemetria planned-vs-actual, critical path, rework, conflitos e eficiencia paralela, com replay/provenance e base para comparacao shadow.
- [x] Concurrency adaptativa v1 baseada em trabalho executavel, quota, custo conhecido, repair rate, first-pass yield e latencia de CI, com decisoes auditaveis.
- [x] Corpus offline de evals do Team Planner cobrindo 10 classes de trabalho e penalizando overstaffing, under-staffing e papeis indevidos.

## Gate atual

Em 2026-09-29 o release cumulativo multiagente/Console foi concluido com autorizacao humana explicita: PR #400 mergeado em `a07c9d96e8d1f64861e928c5c361f5b93f8c6d05` e PR #407 mergeado em `54f3ed0445ffda2c8d0974d0d5b5741065294108`. O deployment de producao do #407 `dpl_EskSGj2T7Z6xjtN8KLNV2yAeeX19` esta READY; `/api/health` respondeu HTTP 200 com `54f3ed0445ff`; validate, factory-acceptance, npm ci, typecheck e build pos-merge ficaram verdes; a Vercel nao registrou runtime errors na janela de observacao. A issue visual #309 foi encerrada. O hardening #402 permanece externo/pendente ate a publicacao real do Next.js 15.5.27.

A Factory core esta funcionalmente implementada. O fluxo de Preview protegido esta verificado com Trusted Source GitHub Actions OIDC. O PR #269 foi liberado por autorizacao humana explicita em 2026-09-28 e mergeado em `98d81dee46c7ffc7ae4ae0662712fadcda3258b3`; o deployment de producao `dpl_KEEZQTBxLTcVJCzF42skk4V8kUAf` chegou a `READY`, `GET /api/health` retornou HTTP 200 com o commit correto, a interface pt-BR foi observada em producao e a Vercel nao reportou erros de runtime na janela de verificacao. As migrations de anexos privados, reconciliacao e Current State Snapshot foram aplicadas e verificadas no Supabase de producao. O acceptance gate executavel e a matriz em `docs/FACTORY_ACCEPTANCE.md` definem o criterio objetivo de completude interna. O piloto Agente SQL nao faz parte do fechamento atual e esta explicitamente adiado.

O provider OpenAI Responses esta implementado e ativo. Em 2026-09-28, apos o usuario adicionar US$ 5 de credito ao OpenAI API Platform, o caminho `OPENAI_API_KEY` passou em um smoke bounded real: GPT-5.6 Luna, `reasoning=none`, 35 tokens de entrada, 9 de saida, 44 totais, resposta exata `FACTORY_SMOKE_OK` e custo estimado de US$ 0.0000178, abaixo do teto de US$ 0.01. A evidencia foi persistida no Control Plane. O Primary foi entao ativado explicitamente via API key com budget Factory de US$ 4.00 e reserva de US$ 0.50 por chamada/run, deixando US$ 1.00 do saldo comprado fora do budget como margem. Cada chamada faz pre-reserva duravel, substitui pela medicao real em sucesso e transforma custo nao mensuravel em evento desconhecido que bloqueia novas chamadas.

A estrategia operacional e: ferramentas deterministicas primeiro, API/Direct como caminho principal e Codex apenas quando a complexidade justificar. Billing/quota, budget e ledger do Primary estao ativos com API key explicita; o mapping WIF (#250) permanece um hardening de autenticacao externo independente. A autenticacao autonoma do Codex (#240) nao bloqueia o fluxo: enquanto WIF/access token nao estiverem disponiveis, tarefas Codex podem usar handoff manual e a Factory retoma a partir do PR. Tokens ChatGPT nao oficiais continuam rejeitados.

## Metricas do projeto

- percentual de tarefas concluidas sem intervencao humana;
- percentual de tarefas que realmente usaram Codex;
- taxa de sucesso de CI na primeira tentativa;
- numero de regressoes detectadas antes do merge;
- tempo entre requisito aprovado e preview;
- custo por run / por tarefa quando mensuravel;
- quantidade de gates humanos realmente necessarios.


## Validacoes adicionais

- Auth resolver: mecanismos oficiais apenas; API key para o modelo principal e WIF oficial para Codex, sem expor valores secretos.
- Usage observability: provider/model/tokens/custo conhecido ou explicitamente desconhecido.
- Greenfield offline: lifecycle completo low-risk validado com 0 chamadas externas; producao para corretamente em human gate.


## Auditoria pos-ativacao - 2026-09-28

- [x] Reconciliar 19 migrations Git x Supabase producao.
- [x] Confirmar Control Plane sem runs abertos/falhos ou gates pendentes.
- [x] Versionar o broker OIDC de evidencia visual e proteger seus claims no acceptance.
- [x] Remover atalhos legados de chamada paga fora do ledger/budget.
- [x] Corrigir documentacao que ainda sugeria merge automatico apos CI.
- [x] Preservar API key como auth Primary explicita enquanto WIF #250 permanece hardening externo.
- [x] Fechar #309 apos Preview exato, comparacao visual autenticada contra `Esteira.zip`, release #407 e observacao pos-release sem runtime errors.
- [ ] Habilitar Leaked Password Protection por acao administrativa.
- [ ] Resolver API WIF #250 quando o mapping administrativo puder ser corrigido.
- [ ] Resolver Codex auth #240 quando houver credencial oficial/enablement.
- [ ] Retornar repositorio a private depois de encerrada a necessidade da janela publica.


### F9 - Project Intelligence
- [x] Project Brain v1 deterministico e versionado: tarefas, scopes, capabilities, componentes e fontes/evidencias com provenance.
- [x] Impact Engine v1: blast radius por task_key/grafo, confidence/unknowns explicitos e evidencia duravel antes do builder.
- [x] Requirement Traceability e Definition of Done compilavel (#376).
- [x] Context Packets/sandboxes/repair loops (#377).
- [x] Policy-as-Code/Release Intelligence/rollback (#378).
- [x] Incident Mode/Portfolio Scheduler (#379).
- [x] Replay/Shadow/provenance completo/self-improvement controlado (#380).
- [x] Architecture Guardian v1 com scanners determinísticos, lineage factual e API/dependency surfaces (#381).


### F10 - Operacao, aprendizagem e rastreabilidade
- [x] Test collection guard: nenhum teste `test_*` pode ficar invisivel ao `unittest discover`; 30 checks historicamente ocultos foram reconciliados e a suite real ultrapassa 465 testes.
- [x] Console de Orquestracao em PT-BR para portfolio, incidentes, repairs, release readiness, Replay/Shadow e propostas de melhoria.
- [x] Execution Router v2 baseado em impacto, unknowns, first-pass historico e custo comparativo, sem chamada extra de modelo.
- [x] Proveniencia duravel de run e provenance pointers seguros nos commits/work units.
- [x] Preview final por promocao de candidato exato: branches de implementacao nao geram Preview; somente `preview/**` pode construir o candidato final.
- [x] Validar o candidato cumulativo em Preview exato + browser evidence autenticada: PR #407 head `54b275fbafd7e035fdce983fb2bc976af8b08f64`, Preview `dpl_GB3pzQtX3QHS9Fw5Y9zd7AeRS3zH`, authenticated evidence run `36610828751`.
- [x] Release cumulativo autorizado pelo usuario e mergeado em `54f3ed0445ffda2c8d0974d0d5b5741065294108`; producao `dpl_EskSGj2T7Z6xjtN8KLNV2yAeeX19` READY, health HTTP 200 no commit correto, CI pos-merge verde e zero runtime errors na janela de observacao.


## Atualizacao operacional - 2026-09-30

- PR #423 foi mergeado humanamente em `406fe0023266152aab1cc3d2c45a610ba1e2595b`; Vercel producao esta READY e o health reporta o commit correto.
- OAuth Supabase do CRM e o preflight cross-repo read-only foram concluidos e verificados.
- O repositorio voltou temporariamente a public porque a conta GitHub Free esgotou 2.000/2.000 minutos de Actions para repositorios privados; o usuario decidiu migrar para GitHub Pro no proximo ciclo e entao retornar a private.
- Apos o retorno temporario a public, `validate`/factory-acceptance e CRM cross-repo preflight voltaram a passar, confirmando que o bloqueio era de capacidade/feature da conta e nao regressao da Factory.
- #427 passa a ser prioridade operacional: reduzir runners ociosos do autonomous runner por meio de probe deterministico read-only e server-side skip de jobs sem trabalho.
- Depois do Pro/private, revalidar GitHub Actions, environments, Control Plane OIDC, CRM cross-repo e Vercel.
- O primeiro trabalho funcional novo executado integralmente pela Factory continua como proxima prova end-to-end de produto; o benchmark de 63 perguntas do Agente SQL continua explicitamente postergado.


## Atualizacao operacional - pos-dogfood 2026-09-30

- [x] Dogfood real end-to-end #430 concluido: Direct grounded no repositorio real, Structured Outputs, Change Set multi-wave, CI, specialists, Preview N/A, `awaiting_release`, merge humano e release observer.
- [x] Criacao de PR same-repo via GitHub Actions validada com `GITHUB_TOKEN` nativo; probe PR #465 fechado sem merge; auto-merge continua desabilitado.
- [x] Retry nativo auditavel #443 concluido: RPC fail-closed + CLI `runtime --mode retry`, migration aplicada e historico do source run preservado.
- [x] Alertas operacionais corrigidos para contar apenas falhas acionaveis; runs falhos historicos continuam preservados para auditoria.
- [x] Schedule-probe com telemetria duravel `work_detected/work_classes` sem novo schema e sem alterar semantica de dispatch.
- [ ] Codex WIF #240 continua externo: o suporte confirmou o desenho, mas ainda nao confirmou habilitacao do recurso no workspace Infodive nem forneceu federation rule/audience reais.
- [ ] OpenAI API WIF #250 continua hardening externo; Primary permanece em API key enquanto o preflight WIF nao estiver verde.
- [ ] Next.js #402 continua aguardando publicacao real de 15.5.27 no npm; nao usar beta/canary.
- [ ] Repositorio privado/Actions #426 continua gate administrativo externo; nao comprar plano automaticamente.


## Atualizacao operacional - 2026-10-01

- [x] Sequencia de UX operacional consolidada ate o PR #514 e guarda-chuva #483 encerrada com evidencia de CI, producao, health e ausencia de erros de runtime.
- [x] `main` reconciliada em `582322059cf564a454c8e7c9cdfda262bbe2459a`, sem PRs abertos no checkpoint.
- [x] GitHub Actions confirmado saudavel no estado publico atual: `validate` e `Console validation` verdes no commit atual.
- [x] Control Plane reconciliado: 3 projetos ativos, 0 runs abertos, 0 falhas acionaveis, 0 gates pendentes, 0 invocacoes Codex e custo conhecido acumulado de US$ 0.3478338.
- [x] Console producao confirmado no deployment `dpl_59HGsseu5UdcXFZip4dPFW7VeMgc`, `READY`, health HTTP 200 no commit atual e zero runtime errors na janela verificada.
- [ ] #426 passa a representar somente o gate administrativo de retorno a private/GitHub Pro e sua revalidacao; nao e falha ativa de Actions enquanto o repositorio estiver public.
- [ ] #240, #250 e #474 continuam dependencias externas/administrativas e nao devem ser contornadas com valores inventados, ampliacao de acesso ou enfraquecimento de gates.
- [ ] Leaked Password Protection do Supabase continua hardening administrativo externo; os avisos RLS sem policy publica permanecem intencionais.
- [x] Production merge continua exclusivamente humano; runtime sem auto-merge e `allow_auto_merge=false`.

## Atualizacao operacional - 2026-10-02 GitHub App e Preview

- [x] GitHub App oficial da Factory registrada via Manifest flow, com PEM/client secret armazenados somente no Supabase Vault.
- [x] Registro da App aparece como acao humana real no Console; nenhum repositorio recebe acesso silenciosamente.
- [x] Preview promotion automatico corrigido e validado: novo ref e semeado no parent e avancado ao SHA exato para disparar uma unica promocao observavel pela integracao GitHub/Vercel.
- [x] PR #595 preparado para centralizar em `/gates` a instalacao/verificacao da App por projeto; candidato exato esta com CI, Preview e browser evidence verdes e aguarda exclusivamente merge humano de producao.
- [x] Fase 3 do runtime preparada no PR #599: token de instalacao efemero e restrito ao repository_id verificado, sem persistencia de PEM/token e sem fallback silencioso quando um projeto ja migrou para `github_app`.
- [ ] Instalar e verificar a GitHub App no CRM Infodive por consentimento humano explicito.
- [ ] Depois da verificacao real do CRM, liberar a Fase 3 do runtime e comprovar um ciclo cross-repo sem `FACTORY_GITHUB_TOKEN`.
- [ ] Avaliar separadamente a instalacao no Agente SQL; nao ampliar acesso junto com o CRM.

## Atualizacao operacional - 2026-10-04
- [x] Fluxo de continuidade de projetos consolidado no Console: pedido duravel, anexos privados, contexto do ultimo pedido, download autenticado e historico bounded baseado em auditoria.
- [x] CRM Infodive reconciliado em `operations`, sem PRs/issues abertos no checkpoint e com Vercel verde no `main` `23b4992727adb768a7a5b513cd0a181ea5d1e2d5`.
- [x] Factory reconciliada em `main` `c1e003ad8a6f7cf0192c6ec65e95d31ec9c651fe` apos merge humano do PR #633; release de producao deve ser verificado separadamente antes de ser declarado concluido.
- [x] Control Plane no checkpoint: zero tarefas abertas, zero runs abertos e zero gates pendentes para Factory e CRM.
- [ ] #240 Codex WIF continua externo e depende de enablement/federation values oficiais.
- [ ] #250 OpenAI API WIF continua hardening externo; nao substituir o caminho operacional selecionado sem preflight verde.
- [x] #426 encerrada: repositorio esta private e GitHub-hosted Actions voltaram a executar com CI verde, sem compra automatica nem reducao de isolamento.
- [ ] #474 continua hardening administrativo da protecao de `main`; runtime permanece sem auto-merge.
- [ ] Leaked Password Protection do Supabase continua hardening administrativo externo; RLS fail-closed sem policies publicas permanece intencional.
- [ ] Benchmark de 63 perguntas do Agente SQL continua postergado.

