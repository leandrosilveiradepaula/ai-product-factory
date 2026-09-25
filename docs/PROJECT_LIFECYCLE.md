# Ciclo de Vida de um Produto

1. `discovery` - necessidade ainda esta sendo esclarecida.
2. `specification` - requisitos e criterios de aceite sao consolidados.
3. `planning` - arquitetura, epicos, tarefas e dependencias.
4. `implementation` - execucao de codigo/configuracao.
5. `review` - revisao tecnica e de seguranca.
6. `validation` - testes tradicionais e evals.
7. `preview` - ambiente validavel pelo usuario/sistema.
8. `human_gate` - usado somente quando a politica exigir.
9. `release` - merge/deploy/versionamento.
10. `operations` - observabilidade, incidentes e melhoria continua.

Falhas em review/validation normalmente retornam para `implementation`, sem envolver o usuario.
