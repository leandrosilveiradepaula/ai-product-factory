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
- [x] Provider-neutral Model Executor.
- [x] Budget por tarefa para modelo principal e Codex.
- [x] Pipeline Engine ponta a ponta.
- [x] Project Memory versionada.
- [x] Review/evaluation quality gates.
- [x] Provider OpenAI Responses implementado (API key validada tecnicamente; consumo bloqueado por quota/billing separado).
- [x] OpenAI API WIF implementado e configurado em OpenAI Platform + GitHub (`openai-api`); preflight sem modelo aguarda cota do Actions, e billing API permanece gate separado.
- [ ] Provider real do Codex/ChatGPT entitlement (Factory pronta; WIF beta confirmado ausente no Admin Portal do workspace Infodive e aguardando habilitacao/regra oficial da OpenAI, issue #240).

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
- [ ] Validar CI/factory-acceptance no GitHub Actions quando a conta voltar a aceitar consumo (2.000/2.000 minutos incluidos consumidos; jobs atuais falham antes do primeiro step).
- [x] Validar build do Console por Preview exato Vercel do candidato `10f593d7d169d30fe5048eac9d98a94b8be1e151` (deployment `dpl_CNFAo32v4DHzjCzgmx1xZUsKFkwX`, `READY`).
- [ ] Reexecutar browser/Playwright evidence quando GitHub Actions voltar; o release de 27/09/2026 foi uma excecao explicitamente autorizada pelo operador humano, sem afirmar que esse check passou.

## Gate atual

A Factory core esta funcionalmente implementada. O acceptance gate executavel e a matriz em `docs/FACTORY_ACCEPTANCE.md` definem o criterio objetivo de completude interna. O piloto Agente SQL nao faz parte do fechamento atual e esta explicitamente adiado.

O provider OpenAI Responses esta implementado. A OPENAI_API_KEY chegou corretamente ao runtime, mas a conta de API respondeu HTTP 429 por quota/billing separado.

Para evitar custo adicional antes de necessario, o caminho prioritario continua sendo validar o mecanismo oficial de Workload Identity do workspace para Codex. O runtime aceita API key para o modelo principal e as variaveis oficiais de WIF para Codex; tokens ChatGPT nao oficiais sao deliberadamente rejeitados.

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
