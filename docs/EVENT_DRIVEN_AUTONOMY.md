# AI Product Factory — continuidade orientada a eventos

**Decisão de 29/10/2026, baseada em `main=fe75bd3a4641433c38db4659ccbd725c04a3ad2c`.**
Status: **correção candidata, ainda não integrada/ativada**. Nenhuma prova de
produção nem autorização paga decorre desta decisão. Issue operacional #1143.

## Responsabilidades e fonte de verdade

- **Humano (Console/OWNER)** autoriza Start, Resume, Stop e produção. Um
  cadastro não inicia trabalho. Somente um projeto `running`, geração correta
  e task legitimamente criada é elegível; pausas e gates humanos não podem ser
  contornados por nenhum wake.
- **Supabase/Postgres** mantém estado, tasks/runs, outbox, leases, ledger,
  gates, control version/generation e auditoria. A gravação transacional
  antecede qualquer wake.
- **Python** é o decisor de claims/rotas. Nenhum callback, `schedule`,
  `repository_dispatch` ou `workflow_dispatch` ganha autoridade de trabalho,
  gasto de modelo, Preview ou merge por seu tipo de evento.
- **GitHub Actions** executa etapas elegíveis. A conclusão entre jobs do
  mesmo runner é encadeada por `needs`, com um probe pós-Product Stage.
- **Watchdog externo opcional** lê a fila real e só pede wake limitado quando
  não há duas execuções nativas recentes e não ocorreu outro wake há 30 min.
  Não cria Start nem retoma projeto pausado; nunca identifica um 204 como PASS.

## Achado: flags manuais suprimiam a própria continuação

No caminho Console -> `workflow_dispatch`, `intake-worker-wake.ts` enviava
`run_direct=false` e `run_preview=false`, mesmo após gravar a intenção de
wake no Control Plane. O `autonomous-runner.yml` exigia `inputs.run_direct`
para Direct e `inputs.run_preview` para Preview; o evento aceito podia assim
não avançar a fila que o probe identificara. O caminho GitHub App envia
`repository_dispatch` e não apresenta esse mesmo filtro de flags. Não foi
confirmada a preferência de credenciais em produção.

O ajuste proposto permite que `workflow_dispatch` com `schedule-probe`
verificado processe **somente** Direct/Codex da matriz de claims, Preview
após um probe real e specialists realmente elegíveis. Inputs manuais
continuam disponíveis mas são dicas, não autoridade: as claims, flags de
modelo, budgets, epochs e gates permanecem inalterados. Jobs de auditoria
read-only continuam isolados pelo `schedule-probe` e não geram trabalho.

## Reconciler fora da rota de pagamento

O watchdog da #1145 observava somente o estado de `schedule`, e podia
solicitar workflow quando não existia fila executável. Com a proposta atual:

1. Validar repositório numérico exato, workflow e ordenação de runs; exigir
   evidência de dois probes nativos consecutivos para suprimir recovery.
2. Se faltar cron, verificar `workflow_dispatch` **e** `repository_dispatch`
   recentes; suprimir duplicação dentro de 30 minutos.
3. Ler o `SupabaseScheduleProbe` existente em modo **sem telemetria**,
   reutilizando sinais autoritativos SQL e a política de Preview (incluindo
   bloqueios de quota), sem gerar `schedule_probe.native_observed` falso.
4. Rejeitar snapshot contraditório, truncado, com fila desconhecida ou
   indisponibilidade de autenticação. Só `work_detected` de classes executáveis
   (não somente `github_access_work`) permite `would_dispatch`/dispatch.
5. O executável permanece **OFF**: exige flag, CLI `--execute`, GitHub Actions
   scoped token e credencial Supabase privilegiada explícita; não há instalação
   na VPS ou ampliação de acesso automática. A confirmação HTTP 204 **não**
   equivale a workflow executado.

A verificação é de fila **elegível** + ausência de wakes recentes, não uma
prova temporal exata do envelhecimento da tarefa. Não declare SLA de retomada
até medir `enqueued_at → worker_claimed_at` em um trabalho real.

## Ponto deliberadamente pendente — callbacks entre repositórios

Os eventos de conclusão de CI/Preview em outro repositório não são, por si,
`workflow_run` no repositório Factory. Esta correção não inventa webhook de
terceiro, não amplia permissões cross-repo e **não comprova** continuação
instantânea nesse handoff. Uma implementação posterior, somente com
capacidade e autorização suficientes, deve aceitar eventos confiáveis,
identificar `repository/project/run/PR/SHA/epoch`, deduplicar pelo outbox e
acordar workers autorizados. Até lá, o cron atual permanece fallback.

## Gates de saída antes de reduzir o cron

- Testes negativos locais e CI `test` + `factory-acceptance` no SHA exato;
  Preview da Factory N/A apenas se `apps/console/**` não mudar.
- Provar `Start/Resume → run claim`, `Product → Direct/CI`,
  `CI/specialists → Preview`, `human merge → release observer` com eventos
  autênticos e refs exatas em jornada já autorizada (CRM), sem criar Start
  artificial, nem reabrir runs históricos.
- Simular perda de wake e snapshot ilegível; confirmar ausência de escrita,
  chamada paga, replay após Pause/Stop, duplicação ou merge automático.
- Qualquer credencial adicional na VPS ou exposição privilegiada do Control
  Plane é **gate sensível humano separado**. Nenhuma contratação, migration,
  ativação de modelo, publicação de produção ou auto-merge é autorizada aqui.
- Auditor global #713 mantém `product_ready=false` até seis domínios
  certificados independentemente. A issue #1143 só fecha com evidência
  **nativa** do cron, nunca com evento externo fabricado.