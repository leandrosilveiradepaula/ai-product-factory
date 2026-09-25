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
8. **Producao protegida**: no MVP, deploy destrutivo ou de alto impacto exige aprovacao humana.

## Nucleo v0.1

- Project Manifest padrao.
- State machine do ciclo de produto.
- Codex Policy Engine.
- Politica de gates humanos.
- Control plane em Supabase (schema inicial).
- Prompts/papeis de Product Manager, Engineering Manager, Developer, Reviewer, Evaluator e Release Manager.
- CI da propria fabrica.
- Contratos de adapters para integracoes externas.

## Primeiro piloto

O primeiro projeto existente a ser integrado sera:

`leandrosilveiradepaula/agente-sql-langgraph`

No piloto, a fabrica devera conseguir planejar uma tarefa, alterar o projeto, executar testes e o benchmark de 63 perguntas, produzir evidencias e preparar a mudanca para aprovacao.

## Uso local

```bash
python -m ai_product_factory.cli validate config/factory.example.json
python -m ai_product_factory.cli codex-decision --complexity high --files 20 --deep-debug
python -m unittest discover -s tests -v
```

O projeto usa apenas a biblioteca padrao do Python no nucleo para manter o bootstrap simples.
