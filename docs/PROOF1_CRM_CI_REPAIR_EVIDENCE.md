# Prova 1 — recuperar CI nativa do CRM sem adivinhar código

## Incidente verificado em 23/10/2026

A Factory gerou autonomamente [CRM PR #193](https://github.com/leandrosilveiradepaula/crm-infodive/pull/193), Change Set `bd46da70-447e-4776-9dec-2ee38f139be8`, SHA `0f5f2aa781ea49c76f71a4a963b2c4cfd9acb082`, base não produtiva `preview/hardening-release-candidate`. O workflow GitHub `CRM validation` #40004128807 concluiu `failure` na etapa `New lint errors` do job `validate`; os três jobs transacionais passaram. O log da CI contém quatro linhas LINT_CHANGED_ERROR no arquivo de Relatórios, uma `@typescript-eslint/no-explicit-any` e três `jsx-a11y/control-has-associated-label`.

O `ci-followup` da Factory reconduziu a falha como `native-ci/lint` em um pedido durável de reparo `51078d63-d17e-418c-b9dc-d9c0d77b27da`, com limite de três tentativas. A primeira Work Unit de reparo `d214f9fd-d240-47ab-9293-b3f04cd2c03c` terminou `blocked` e o pedido virou `failed_gate` porque seu pacote não continha as posições e regras exatas. O agente recusou produzir um patch especulativo, corretamente.

## Contrato da correção

1. Buscar a lista paginada já existente de jobs da execução **run ID, tentativa e SHA verificados**. Não aceitar URL ou código de uma issue, comentário, modelo ou log externo como identidade.
2. Somente para a etapa `native-ci/lint`, ler o log do **job ID certificado** no GitHub Actions (credencial server-side). O download tem limite de 1 MiB. Proibir redirecionamento automático do bearer do GitHub; seguir apenas URL HTTPS assinada em domínios de armazenamento conhecidos, **sem** Authorization.
3. Extrair exclusivamente linhas com marcador `LINT_CHANGED_ERROR`, caminho relativo em diretórios allowlisted, linha/coluna decimal e identificador de regra. Ignorar textos livres, mensagens de código, trechos de fonte, query params e quaisquer outros bytes. Limites: 20 erros distintos, 1.600 caracteres de resumo.
4. Se a leitura estiver indisponível, malformada, exceder limites ou não contiver marcador, devolver o resumo genérico `Verified failed GitHub Actions step (run and attempt bound)`. **Nunca** inventar diagnóstico, reclassificar infraestrutura como código ou incluir logs brutos no Control Plane/modelo.
5. Testes offline validam paths permitidos, deduplicação, limites, SHA/tentativa/job corretos no adapter, ausência de payload/segredos no resumo, recusa de host não confiável e não propagação da credencial ao storage.

## Gate de retomada da Prova 1

- Este patch **não reabre automaticamente** a Work Unit bloqueada, não altera SQL e não produz um commit de CRM. Mesmo após merge humano desta correção, o pedido histórico permanece `failed_gate` até que exista recuperação específica e segura, com identidade exata e budget/gates preservados. Não usar `factory_retry_failed_run` genericamente nem repetir Product Stage pago.
- Reexecutar somente reparo para o Change Set candidato original, após admissão validada por Control Plane; caso não exista caminho transacional seguro, registrar dependência em vez de escrever estados manualmente.
- Exigir CI exata SHA verde, especialistas, Preview real ou N/A formal e `awaiting_release` antes de considerar a Prova 1 concluída. PR #193 **não está pronta para merge**; CI vermelha e Preview não verificado.
- O runtime continua sem capacidade de merge automático. A Factory main publica produção: integrar esta alteração apenas por merge humano após CI. Nenhum crédito de modelo é gasto por estes testes.
