# Arquitetura da AI Product Factory

## Fluxo principal

```text
Usuario
  |
  v
ChatGPT / Product Orchestrator
  |
  +--> Discovery
  +--> Product Spec
  +--> Engineering Plan
  |
  v
Task Router
  |
  +--> execucao direta --------------------------+
  |                                               |
  +--> ferramenta especializada                  |
  |                                               |
  +--> Codex (somente quando necessario)         |
  |                                               |
  +-----------------------------------------------+
                                                  v
                                      GitHub / Supabase / Vercel
                                                  |
                                                  v
                                     Review + Tests + Evals
                                                  |
                                                  v
                                           Quality Gate
                                                  |
                                                  v
                                         Verified Preview
                                      (deploy + browser/e2e)
                                                  |
                                                  v
                                         awaiting_release
                                                  |
                                                  v
                                      Usuario faz merge do PR
                                                  |
                                                  v
                                      Release observer registra
                                                  |
                                                  v
                                             Operations
```

## Camadas

### 1. Product Orchestrator
Interface principal com o usuario. Mantem contexto do objetivo, conduz discovery e decide quando existe informacao suficiente para iniciar desenvolvimento.

### 2. Product Memory
Mantem de forma persistente:
- product spec;
- arquitetura;
- ADRs/decisoes;
- restricoes;
- integracoes;
- ambientes;
- estado atual;
- backlog;
- evidencias de testes e releases.

### 3. Engineering Manager
Transforma a especificacao em epicos, tarefas, dependencias e criterios de aceite tecnicos.

### 4. Task Router
Decide a melhor forma de executar cada tarefa. Ele prefere ferramentas diretas e so escala para Codex quando o beneficio esperado justificar o custo.

### 5. Execution Layer
Executa alteracoes em codigo e servicos por adapters. O executor deve sempre produzir evidencias: commit, migration, workflow run, log, deployment ou teste.

### 6. Review/Evaluation Layer
Separa validacao tradicional de software de evals de IA. Um projeto pode exigir ambas.

### 7. Human Gate Layer
Gates sao baseados em risco. Uma tarefa de baixo risco pode atravessar discovery, planejamento, implementacao, review, CI e Preview sem interromper o usuario. Producao permanece diferente: quando o merge do PR publica `main`, o runtime para em `awaiting_release`; somente uma pessoa pode executar o merge. O worker de release apenas observa e registra um merge que ja aconteceu.

### 8. Control Plane
Supabase/Postgres registra projetos, tarefas, runs, decisoes, gates, uso de ferramentas, evals e deployments.

## Codex nao e o orquestrador

Codex e um executor especializado. A factory deve continuar operando quando Codex estiver indisponivel ou quando o usuario atingir limites de uso.

## Fronteira de release

O runtime nunca deve transformar a aprovacao tecnica de um Preview em permissao implicita para publicar em producao. CI verde, quality gate e browser/e2e sao pre-condicoes; nao substituem o gate humano de producao. O observador de release possui permissoes de leitura no PR e nao possui permissao de escrita em codigo ou de merge.
