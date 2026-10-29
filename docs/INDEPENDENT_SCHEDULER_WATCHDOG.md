# Recuperação condicional da Factory — watchdog externo (desativado)

**Estado: código candidato, sem instalação na VPS e SEM autorização de ativação.**

Em 29/10/2026, o `schedule` nativo do workflow Factory parou de iniciar
novos runs após 10:26 UTC. O fallback OIDC programado também depende do
scheduler do GitHub e, portanto, não é independente. A issue #1143 permanece
aberta até duas evidências **nativas** válidas de recuperação.

## Mudança arquitetural após revisão da #1145

A implementação anterior podia pedir um wake apenas porque o cron estava
irregular, mesmo sem tarefas. Isso não é autonomia produtiva. O watchdog agora
só pode emitir um `workflow_dispatch` se **todas** as condições passarem:

1. GitHub REST confirma ID exato do repositório `1387883686`, nome
   `leandrosilveiradepaula/ai-product-factory`, branch `main`, workflow
   `.github/workflows/autonomous-runner.yml` ativo e runs ordenados com
   proveniência. Dois probes nativos recentes, efetivamente concluídos,
   descartam recuperação por via alternativa.
2. Nenhum `workflow_dispatch` **nem** `repository_dispatch` do mesmo workflow
   foi criado nos últimos 30 minutos. Um cron ainda em andamento e recente
   também suspende nova tentativa.
3. Uma leitura nova do **Control Plane correto**, usando o `SupabaseScheduleProbe`
   já existente e com `record_telemetry=False`, confirma fila autorizada.
   A classificação consulta os sinais SQL `factory_scheduler_queue_signals`,
   as condições de portfolio, especialistas, CI e Preview, além dos bloqueios
   por quota. O watchdog NÃO cria `schedule_probe.native_observed`.
4. Snapshot incompleto/truncado, fila ociosa, apenas access preflight, erro de
   autenticação, segredo ausente, mismatch de projeto, resposta contraditória,
   relógio incoerente ou corrida de API nunca autorizam dispatch.
5. Somente `--execute` **mais** `FACTORY_EXTERNAL_SCHEDULER_ENABLED=true`
   solicitam a execução. O HTTP 204 significa apenas aceite do GitHub; o
   resultado do workflow deve ser observado por separado.

A decisão é apenas sobre **acordar** o runner existente; a Factory continua a
validar estado `running`, epoch, budget/ledger, origem do trabalho, leases,
quality gate, Preview e gate humano de produção antes de qualquer efeito.
Mesmo um evento duplicado não pode recriar Start ou aplicar merge. Não há
SLA garantido, nem prova de que a task está envelhecida por um intervalo
exato; as medições de `enqueued_at → worker_started_at` são critério de rollout.

## Verificação offline

A partir da raiz do repositório:

```bash
PYTHONPATH=src python -m unittest tests/test_independent_scheduler_watchdog.py -v
PYTHONPATH=src python -m unittest tests/test_schedule_probe_readonly_contract.py -v
```

O primeiro comando usa apenas fixtures locais, sem GitHub real, chamadas pagas,
modelos ou dados de produção. O segundo prova que o leitor usado externamente
não escreve telemetria nem simula o cron nativo. O modo padrão do runner
continua gerando seus recibos de probe normalmente.

## Pré-ativação (somente operador autorizado)

**Não execute o antigo instalador da VPS gerado antes deste redesenho.**
Ele foi concebido para o watchdog v1 e não prova elegibilidade de trabalho.

O host autorizado deve usar **um único** timer externo à infraestrutura de
GitHub Actions e checkout fixado a um SHA aprovado. A ativação precisa de
aprovação independente para adicionar duas credenciais server-side:

- `FACTORY_EXTERNAL_GITHUB_TOKEN`: fine-grained, acesso **somente** à Factory,
  permissão mínima de Actions leitura/escrita para consultar histórico e
  despachar o próprio workflow.
- `FACTORY_EXTERNAL_CONTROL_PLANE_URL`:
  exatamente `https://fjplmxfcshhbmzgvyqlm.supabase.co`.
- `FACTORY_EXTERNAL_CONTROL_PLANE_KEY`: chave com acesso apenas server-side
  às leituras do Control Plane. **A RPC existente é service-role-only; hoje
  não há papel read-only independente já demonstrado para este uso.** Não
  instale um `sb_secret_*` (privilegiado) na VPS sem decidir explicitamente
  se esse aumento de superfície de ataque é aceitável. Nunca inclua essa
  chave em Git, chat, browser, cron command line, imagem Docker ou logs.

As credenciais devem estar em arquivo de ambiente protegido (`0600`), fora
 do diretório da aplicação, lido apenas por usuário de serviço segregado.
Se faltar qualquer informação, o resultado será `blocked` e exit status 2.
Com a autorização concedida, primeiro executar sem `--execute` para imprimir
`would_dispatch` ou `skipped`, sem efeitos. Somente depois aprovar timer
`systemd` com `--execute`, fazer um disparo limitado de fila legítima, validar
jobs e Control Plane e manter alerta se houver bloqueio repetido.

Não comprar VPS/serviço, não criar secrets, não habilitar Supabase RPC pública,
não usar chamadas pagas só para smoke, não aumentar budget e nunca permitir
merge automático. Até completar eventos de CI/Preview entre repositórios, o
cron atual da Factory permanece fallback best-effort. O plano de saída está em
[`EVENT_DRIVEN_AUTONOMY.md`](EVENT_DRIVEN_AUTONOMY.md).

## Release e Preview

Os arquivos deste bloco são Python, workflow, testes e documentação. O Console
Vercel não foi modificado; a política de paths da Factory determina Preview
N/A. CI completa e merge de produção da Factory exigem revisão humana.
`product_ready=false` até auditoria global independente dos seis domínios.