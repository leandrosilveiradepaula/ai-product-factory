# Modelo de Autonomia

## Objetivo

Interromper o usuario somente quando a decisao for realmente dele.

## Classes de acao

### A0 - Totalmente autonoma
Leitura, analise, documentacao, planejamento, testes, review, criacao de branch, commits de trabalho, preview e operacoes reversiveis de baixo risco.

### A1 - Autonoma com evidencia
Mudancas de codigo e banco em ambiente DEV, migrations aditivas, configuracoes reversiveis e publicacao de preview.

### A2 - Gate humano
Deploy em producao no MVP, migracao destrutiva, ampliacao sensivel de permissoes, servico pago, alteracao material do escopo ou decisao de produto sem resposta inferivel.

## Regra de bloqueio

Se uma etapa estiver bloqueada por uma dependencia externa, a factory deve continuar outras tarefas independentes. Nao deve parar o projeto inteiro somente porque um executor ou ambiente esta temporariamente indisponivel.
