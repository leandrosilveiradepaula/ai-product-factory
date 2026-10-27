# AI Product Factory

Fabrica autonoma de produtos de software e agentes de IA.

## Objetivo

Transformar uma necessidade de produto em software funcional com minima intervencao humana:

`Ideia -> Discovery -> Product Spec -> Plano -> Backlog -> Roteamento -> Implementacao -> Review -> Testes/Evals -> Preview verificado (ou N/A explicito) -> Gate humano de merge -> Release -> Operacao`

O núcleo Python determinístico é o orquestrador do runtime; Supabase é o Control Plane, GitHub é a fonte de verdade de código/PR/CI e Vercel fornece Console/Preview quando aplicável. ChatGPT é uma interface de colaboração, não o motor de agendamento. Codex é executor seletivo, nunca orquestrador.

## Principios

1. **Autonomia por padrao** dentro de limites previamente definidos.
2. **Determinístico primeiro**: ferramentas diretas e workers Python antes de agentes pagos, com evidência durável.
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
- GitHub Autonomous Loop para issue, branch, commit, PR, CI e repair; apos Preview verificado, o fluxo para em `awaiting_release` e o merge de producao e humano.
- Contratos de adapters para integracoes externas.

## Piloto prioritário de certificação

A prova operacional de autonomia da Factory usa o projeto existente real
`leandrosilveiradepaula/crm-infodive`. O Service Desk é módulo desse CRM,
não um greenfield independente: não reativar o antigo projeto ou a sua PR
para fabricar a prova F6. Uma prova greenfield futura precisa de um produto
legítimo, distinto e especificamente autorizado.

O `leandrosilveiradepaula/agente-sql-langgraph` também foi integrado
historicamente à Factory, mas não é o piloto prioritário desta certificação.
Seu benchmark de 63 perguntas continua adiado e nunca é executado
implicitamente.

A [matriz de certificação](docs/FINAL_CERTIFICATION_MATRIX_20261026.md)
e o [contrato de finalização](docs/FINALIZATION_EXECUTION_CONTRACT.md)
registram o escopo e os gates atuais.

## Uso local verificado (sem credenciais)

Requisitos: Python 3.11+; execute na raiz do checkout. O pacote usa layout `src/`,
portanto é necessário definir `PYTHONPATH=src` ou instalar o pacote antes de
usar `python -m ai_product_factory.cli`. Os comandos abaixo são
determinísticos e não acessam Supabase, GitHub, Vercel ou modelos pagos.

Linux/macOS (bash):
```bash
export PYTHONPATH=src
python -m ai_product_factory.cli validate config/factory.example.json
python -m ai_product_factory.cli codex-decision --complexity high --files 20 --deep-debug
python scripts/check_test_collection.py
python -m unittest discover -s tests -v
```

Windows (PowerShell):
```powershell
$env:PYTHONPATH = "src"
python -m ai_product_factory.cli validate config/factory.example.json
python -m ai_product_factory.cli codex-decision --complexity high --files 20 --deep-debug
python scripts/check_test_collection.py
python -m unittest discover -s tests -v
```

Essas verificações locais comprovam apenas código, manifest e contratos.
Testes PostgreSQL isolados e E2E autenticado possuem workflows próprios.
CI verde não cria `product_ready=true`. Não iniciar projeto, recuperação
de run, migration, deploy ou merge de produção para verificar este README.

## Estado atual

Veja [docs/STATUS.md](docs/STATUS.md) para o estado operacional e [docs/OPERATIONS.md](docs/OPERATIONS.md) para o runbook dos workers, gates e procedimentos.
