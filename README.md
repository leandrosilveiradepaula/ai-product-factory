# AI Product Factory

Fabrica autonoma de produtos de software e agentes de IA.

## Objetivo

Transformar uma necessidade de produto em software funcional com minima intervencao humana:

`Ideia -> Discovery -> Product Spec -> Plano -> Implementacao -> Review -> Testes/Evals -> Preview -> Gate Humano -> Release -> Operacao`

O ChatGPT atua como orquestrador principal e usa diretamente as ferramentas disponiveis (GitHub, Supabase, Vercel e outras). Codex e um recurso especializado e seletivo, acionado apenas quando a tarefa realmente se beneficia dele.

## Principios

1. **Autonomia por padrao** dentro de limites previamente definidos.
2. **ChatGPT primeiro**: executar diretamente sempre que as ferramentas disponiveis forem suficientes.
3. **Codex seletivo**: evitar uso para planejamento, documentacao, operacoes simples e alteracoes pequenas.
4. **Memoria persistente do projeto**: requisitos, decisoes, arquitetura, estado e evidencias ficam versionados/auditados.
5. **Gates humanos por risco**, nao por etapa burocratica.
6. **GitHub como fonte de verdade** do codigo, issues, PRs e CI.
7. **Evidencia antes de release**: testes, evals, preview e resultados precisam ser rastreaveis.
8. **Producao protegida**: a politica atual exige aprovacao humana para release em producao e para mudancas destrutivas ou de alto impacto.

## Plataforma

- Project Manifest padrao.
- State machine do ciclo de produto.
- Codex Policy Engine.
- Politica de gates humanos.
- Control Plane persistente em Supabase, com auditoria, runs, tarefas, gates, uso de ferramentas e deployments.
- Prompts/papeis de Product Manager, Engineering Manager, Developer, Reviewer, Evaluator e Release Manager.
- Factory Console autenticado para projetos, backlog, runs e human gates.
- Runtime duravel com fila, worker, roteamento Direct/Codex e runner autonomo limitado.
- GitHub Autonomous Loop para issue, branch, commit, PR, CI, repair e merge.
- Contratos de adapters para integracoes externas.

## Primeiro piloto

O primeiro projeto existente integrado e:

`leandrosilveiradepaula/agente-sql-langgraph`

O piloto ja esta onboardado na Factory. O benchmark de 63 perguntas permanece deliberadamente adiado; a Factory nao deve executa-lo ate que essa validacao seja reaberta como tarefa especifica.

## Uso local

```bash
python -m ai_product_factory.cli validate config/factory.example.json
python -m ai_product_factory.cli codex-decision --complexity high --files 20 --deep-debug
python -m unittest discover -s tests -v
```

O projeto usa apenas a biblioteca padrao do Python no nucleo para manter o bootstrap simples.

## Estado atual

Veja [docs/STATUS.md](docs/STATUS.md) para o estado operacional, gates externos e proximos blocos.
