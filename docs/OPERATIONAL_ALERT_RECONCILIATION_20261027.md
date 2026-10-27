# Atualizacao fidedigna de alertas operacionais (27/10/2026)

## Incidente confirmado

O coletor de GitHub Issues criava uma issue por codigo e nunca atualizava o texto de um alerta existente. No Control Plane real ha sete runs ainda vinculadas a tasks com status failed, mas a issue #1048 ainda dizia "1 run(s) are failed". As issues #1123 (scheduler_gap) e #1044 (scheduler_pipeline) tambem conservavam textos antigos embora a cadencia mudasse.

## Contrato corrigido

- O codigo deterministico do alerta continua tendo uma unica issue aberta. A coleta nao abre duplicatas nem posta comentarios repetidos.
- Se mudou a mensagem ou severidade, atualiza somente o cabecalho original do bot na mesma issue via GitHub Issues PATCH, usando a permissao issues:write ja existente na lane alerts.
- Operador pode adicionar notas apos o cabecalho; o texto adicional e preservado integralmente. Titulo alterado por humano ou corpo fora do modelo confiavel sao deixados intactos.
- Telemetria identica nao gera PATCH. Falha de update propaga erro ao coletor, sem fingir que a issue esta atualizada.
- A politica de encerramento de alertas permanece separada e fail-closed; um scheduler bem-sucedido isolado nao apaga aviso de gap. Dois wakes nativos consecutivos em menos de duas horas sao exigidos.
- Status historicos de task/run permanecem no Supabase. Atualizacao visual nao equivale a recovery, retry, CI, Preview, release ou merge.
- Nao reativar Service Desk standalone; atualmente parado. Nao considerar external_key identica como prova de que uma task antiga foi reparada sem vinculo de proveniencia.

## Operacao e verificacao

1. Na branch candidata, executar python -m unittest tests.test_github_alert_adapter -v e o workflow validate completo no SHA final.
2. Nao altera apps/console/**, portanto Vercel Preview N/A por path.
3. Apos merge HUMANO, acompanhar a primeira lane alerts no scheduler e verificar que os tres numeros de issue permanecem os mesmos e os textos refletem a coleta atual (sem novas issues).
4. Continuar alertando scheduler_gap e scheduler_pipeline enquanto houver gaps reais de 2h. A fonte de falha e o cron best-effort do GitHub Actions; esta PR NAO lhe atribui SLA garantido.
5. Investigar as tarefas failed segundo lineage; nao mover status nem suprimir historicos apenas para fechar #1048.
6. Rollback de codigo: git revert somente apos decisao humana e CI; a correcao nao altera schema, producao, modelo ou dados do Supabase.

Evidencias de baseline: main af8f715ce9921bc3c30acc4d576d3e49eefde4f2; scheduler #40587276260; issues #1048, #1123 e #1044. Este reparo restaura a fidelidade da observabilidade, mas nao certifica o dominio 2 nem altera product_ready.
