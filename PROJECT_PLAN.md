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

## Gate atual

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
