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
- [x] Merge automatico quando nao houver gate humano.
- [x] Fechar issue apos merge.

### F3 - Runtime de Desenvolvimento
- [x] Direct Executor para mudancas pequenas/medias.
- [x] Roteador Direct vs Codex.
- [x] Provider-neutral Model Executor.
- [x] Budget por tarefa para modelo principal e Codex.
- [x] Pipeline Engine ponta a ponta.
- [x] Project Memory versionada.
- [x] Review/evaluation quality gates.
- [ ] Provider real do modelo principal.
- [ ] Provider real do Codex.

### F4 - Testes, Evals e Preview
- [x] CI deterministico por projeto via manifest.
- [x] Contrato de evals obrigatorios/opcionais.
- [x] Evidence bundle.
- [ ] Preview adapter por projeto quando aplicavel.
- [ ] Browser/E2E adapter quando aplicavel.
- [ ] Release deployment adapter por plataforma.

### F5 - Piloto Agente SQL Financeiro
- [x] Onboarding de `agente-sql-langgraph`.
- [x] Importar comando real de regressao: `python scripts/check_all.py`.
- [x] Importar CI real: `Offline validation`.
- [x] Preservar n8n como caminho oficial.
- [x] Preservar LangGraph como offline shadow.
- [x] Registrar projeto no control plane.
- [ ] Escolher proxima linha semantica de planned_filters.
- [ ] Benchmark de 63 perguntas permanece postergado por decisao registrada no projeto.
- [ ] Primeira tarefa funcional nova executada integralmente pela factory.

### F6 - Greenfield Test
- [ ] Criar um produto pequeno do zero somente via factory.
- [ ] Medir intervencoes humanas.
- [ ] Medir tarefas diretas vs. Codex.
- [ ] Revisar gates e ampliar autonomia.

## Gate atual

O nucleo deterministico do MVP esta operacional. Para transformar a Factory em um runtime independente da sessao do ChatGPT, falta configurar um provider real de modelo principal e, opcionalmente, um provider Codex.

Essa decisao pode introduzir credenciais e custo de API, portanto permanece como gate humano.

## Metricas do projeto

- percentual de tarefas concluidas sem intervencao humana;
- percentual de tarefas que realmente usaram Codex;
- taxa de sucesso de CI na primeira tentativa;
- numero de regressoes detectadas antes do merge;
- tempo entre requisito aprovado e preview;
- custo por run / por tarefa quando mensuravel;
- quantidade de gates humanos realmente necessarios.
