# Factory — retorno por eventos externos CI/Preview (candidato não ativado)

Decisão de 29/10/2026. Fonte de verdade: `AGENTS.md`, `docs/FINALIZATION_EXECUTION_CONTRACT.md`, `docs/EVENT_DRIVEN_AUTONOMY.md`. Esta implementação NÃO muda Start, Pause/Stop, gasto de LLM, Preview, gate humano de merge nem release. Não conclui as seis provas de certificação.

## Objetivo e limites

O endpoint Node server-only `POST /api/integrations/github-app/webhook` recebe notificações assinadas de uma GitHub App **já registrada**. Eventos de outro repo nunca viram `workflow_run` da Factory automaticamente. O receptor **não executa** trabalhos: somente solicita o wake do runner `autonomous-runner.yml`, cuja probe autoritativa/claims/budget/gates decidem qualquer evolução. O cron existente permanece fallback até evidência real de continuidade CRM → Factory.

A rota permanece **OFF** com `FACTORY_GITHUB_WEBHOOK_ENABLED` ausente ou diferente de `true`: HTTP 503 `disabled`, sem ler corpo, segredos ou banco. A PR não instala segredo, não muda assinaturas da GitHub App, não executa migration de produção nem fornece acesso novo.

## Pipeline de segurança

1. Exigir flag habilitada, RPC server-side `factory_get_github_app_credentials` e `webhook_secret` existente no Vault, app `registered`, URL do Control Plane *exata* e headers server-side. Chaves `sb_secret_*` entram em `apikey`, não JWT Bearer. Nunca enviar segredo a browser/artefato/CI.
2. Ler **no máximo 192 KiB** do corpo, validar HMAC `X-Hub-Signature-256` sobre bytes originais com comparação constant-time; exigir JSON, GUID `X-GitHub-Delivery`, evento/action estritamente permitidos. Rejeitar falsas instalações/app IDs, repositório inválido, SHA incorreto e pull request não mergeada.
3. SQL `factory_claim_external_webhook_wake_v1` (migration candidata): verifica `project.is_active`, `control.state=running`, `execution_generation`, instalação registrada, modo `github_app`, status `ready`, ID numérico do repo, SHA exato, status elegível do run, e PR quando fornecida; ambiguidade = `ignored`. Lê somente fatos que o Control Plane controla. Nunca cria Start/Run/Task.
4. Reserva `delivery_id` como PK sob lock transacional; redelivery concorrente ou repetida retorna `duplicate`; `pending/claimed/retryable` usa lease e limite de três tentativas. Não grava evento de cron nativo falso.
5. Só **depois do COMMIT** solicita `requestIntakeWorkerWake()`; 204 do GitHub significa *wake requested*, não CI, Preview ou release concluídos. RPC de ACK preserva resultado `requested`, `retryable` ou `suppressed`; pausa/stop/generation stale suprimem o ACK. Falhas de wake geram HTTP 503 `wake_pending` e podem ser redeliveradas; o cron continuará reconciliação quando existir trabalho elegível. Não há auto-redelivery por código nem fila com execução paga.
6. `pull_request.closed && merged` apenas acorda o **release observer**; ele próprio prova merge humano exato, sem auto-merge.

Tipos admitidos por etapa: `workflow_run.completed` e `check_run.completed` para runs `ci_pending`; `deployment_status.created` com `state=success/failure/error` para `preview_ready`; `pull_request.closed` com `merged=true` para `awaiting_release`. Variações fora desse contrato são ignoradas/rejeitadas, não abrem outras APIs públicas.

## CI e evidências

- `node --no-warnings --experimental-strip-types --test apps/console/tests/github-webhook-security.test.mjs`: teste dinâmico de assinatura, tampering, spoof, oversized, eventos, PR e GUID.
- `python -m unittest tests.test_github_external_webhook_contract -v`: verificação de ordem de autenticação e invariantes.
- `.github/workflows/github-external-webhook-postgres.yml`: executa SQL exato em PostgreSQL 16 descartável: RLS + ACL, fake repo/install/commit, duplicidade, redelivery, lease, pause e epoch; sem credencial/modelo/produção.
- `apps/console/**` mudou: Preview Factory **necessário por path**, não declarar N/A. Verificar apenas um candidato pronto em branch de Preview com SHA servido correto.

## Gates HUMANOS antes de ativar

1. Review e merge humano da PR. A migration SQL permanece como arquivo; **aplicar somente com autorização expressa** após verificar histórico, ACL e rollback.
2. Autorizar registrar e guardar um webhook secret oficial no Supabase Vault pela configuração administrativa da GitHub App, sem reproduzir segredo neste chat. A GitHub App atual foi inventariada com `vault_webhook_secret_id IS NULL` em 29/10. Configurar URL do endpoint e assinar/assinar eventos mínimos na instalação relevante; conferir instalação permitida no repo CRM. Esta é mudança de credencial/acesso sensível e não é implícita no merge.
3. Verificar que existe uma via de wake efetivamente funcional *para o repo Factory* (`FACTORY_GITHUB_WORKFLOW_DISPATCH_TOKEN` restrito no servidor ou GitHub App instalada e permitida no repo Factory). Sem isso o retorno é fail-closed/503 e cron segue fallback.
4. Ativar `FACTORY_GITHUB_WEBHOOK_ENABLED=true` **somente** no servidor Console e após confirmação dos controles anteriores. Publicar em produção só mediante gate humano. Testar GitHub delivery real com caso CI legitimamente pendente no CRM, SHA/PR/geração exatos; prova de `wake_requested` ≠ execução. Verificar receipt, workflow/etapa subsequente e métricas `enqueued → claimed`.
5. Redelivery com mesmo GUID deve ser `duplicate`; webhook forjado/assinado com chave errada, repositório fora da allowlist, `paused/stopped` e `epoch` anterior nunca devem acordar execução. Não recriar Start nem rodar modelo apenas para testar.

## Rollback e limitações

Emergência: desabilitar flag, desinscrever webhook na App, preservar outbox/auditoria e cron legado. Reversão de schema segue plano SQL separado após avaliação humana (nunca `DROP` automático). Se ACK falhar após POST aceito, uma redelivery posterior pode emitir wake adicional, mas **nunca reproduz claims/mutações** graças às leases e gates do runner; sinalizar como limite operacional. A migration não tem consumidor de retry autônomo periódico: a entrega é repetida manualmente pelo GitHub ou o scheduler existente reconcilia trabalho legítimo. Não afirmar exatamente-once de HTTP nem autonomia E2E antes da prova real.