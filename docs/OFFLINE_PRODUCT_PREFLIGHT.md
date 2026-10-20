# Product Stage offline preflight — no model, no run replay

Use this to **find structural blockers for one already persisted run before paying
for semantic Discovery/Specification/Planning**. This mode is strictly read-only.
It does not start a project, claim a queued task, reset a failed task, run the
primary model or authorize a purchase.

## Trusted GitHub Actions

In **Factory autonomous runner** > Run workflow (branch **main**):

- `run_offline_preflight`: true
- `project_key`: the existing key, e.g. `ai-product-factory`
- `offline_run_id`: an **already recorded** Product Stage run UUID
- `run_journey_audit`: false; all other manual worker toggles: false

The normal scheduler job is SKIPPED for this invocation, so every worker that
depends on it is also SKIPPED. A separate job uses the **existing trusted OIDC
workflow identity**; no additional token or service is provisioned. It reads
the exact project, task, run, control, durable snapshot and GitHub evidence,
then emits a sanitized JSON artifact kept seven days.

Source preflight `verified` only establishes that structural read-only
inputs currently exist. `historical_terminal` means the original run still
failed/completed/cancelled; it is **not retried**, even when current source now
passes. `recorded_pending` only means the run identity and generation match;
the scheduler, provider budget, paid-model output, PR, CI, Preview, human release
and global readiness remain **unverified**. Do not infer E2E success.

## Incident / sample (20/10/2026)

The real run `16b12d17-9cb0-4578-a0e2-0d601f36b856` belongs to
`ai-product-factory` and failed in Product Stage before model invocation.
After #988, a newly isolated offline test should confirm the **current source**
can be inspected for `platform`. The terminal run is never reopened
automatically. Its failure remains audit history.

The original request references issue #987 without code paths. For `platform`
only, the new source reader resolves that issue in the **same repository** and
extracts bounded path hints (file names only). It reads the files at a pinned
Git SHA; neither the mutable issue body nor its instructions are treated as
authorized code changes. Existing imported projects retain their strict
open-Preview-PR candidate policy. No fallback to unrelated projects or floating
branches.

This offline phase is free of paid **model** calls. GitHub/Vercel/Supabase
infrastructure has separate provider quotas, which are still respected. Only
after a real Start/new continuation, verified source inputs and free tests
may an inherently semantic stage use the paid provider within the Control
Plane ledger ceiling. Never pay to probe quota/auth or repeat known failures.

## Execucao pelo orquestrador conectado (sem clique manual no Actions)

Quando o conector GitHub nao expuser workflow_dispatch, publicar pelo conector
um comentario **exato** na issue existente do repositorio Factory:

```text
/factory-offline-preflight ai-product-factory 16b12d17-9cb0-4578-a0e2-0d601f36b856
```

Esse comentario da conta OWNER gera um evento issue_comment (created).
Um job independente verifica OWNER, issue real (nao PR), sintaxe estrita,
project_key e UUID. A validacao ocorre antes da obtencao de token OIDC.
As permissoes GitHub desse job sao contents:read, issues:read e id-token:write.
Ele nao recebe OPENAI_API_KEY, nao invoca agentes/modelos e nao utiliza RPC de
claim, retry ou escrita no Control Plane. O comentario nao e comando Start.

Os workers continuam dependentes de schedule-probe, que so reage ao comando
exato /factory-wake, nunca /factory-offline-preflight. O outro comando
/factory-alerts continua independente. Verificar o workflow e o JSON
sanitizado no artifact (7 dias); comentario criado nao comprova sucesso.

O modo manual workflow_dispatch permanece compativel e opcional, nao e
uma etapa que deva ser delegada ao usuario quando o conector puder comentar.
