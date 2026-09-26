# Authentication activation readiness

The Factory treats OpenAI API authentication and Codex workspace authentication as independent gates. Neither gate is inferred from the presence of a secret alone.

## Primary model

Ready only when all of these are true:

- `OPENAI_API_KEY` is configured in the execution environment.
- API billing/quota is known to permit the intended workload.
- a bounded smoke test has succeeded after quota/billing readiness is confirmed.
- `FACTORY_PRIMARY_MODEL_ENABLED=true` is explicitly set.

Current known state: the existing key reached the API but returned HTTP 429/quota. Keep `FACTORY_PRIMARY_MODEL_ENABLED` unset/false. Do not repeat paid calls merely to poll readiness.

## Codex workspace WIF

Ready only when all of these are true:

- the managed OpenAI/ChatGPT workspace has an approved Workload Identity rule/provider.
- `OPENAI_FEDERATION_RULE_ID` contains the real administrator-provided rule id.
- `OPENAI_WIF_AUDIENCE` contains the real accepted audience.
- GitHub Actions can mint the OIDC token into `OPENAI_IDENTITY_TOKEN_FILE`.
- the manual `Codex WIF preflight` workflow reaches a successful `codex login status`.

Do not invent the federation rule id or audience. The preflight is intentionally manual and does not execute a Codex task.

## Activation order

1. Configure the external administrative values.
2. Run the relevant preflight once.
3. Preserve the workflow evidence.
4. Only then enable the corresponding execution adapter.
5. Scheduled Direct remains disabled until Primary readiness is proven.

Production deployment remains independently human-gated.

## Verified Preview

Ready only when all of these are true:

- the project has a Vercel preview configuration (`manifest.preview`) or an explicit non-secret environment fallback;
- `VERCEL_TOKEN` is configured in the execution environment;
- `FACTORY_VERCEL_PREVIEW_ENABLED=true`;
- `FACTORY_BROWSER_EVIDENCE_COMMAND_JSON` contains a reviewed argv-style command;
- `FACTORY_BROWSER_EVIDENCE_ENABLED=true`;
- the browser/e2e command returns structured success evidence for the exact Preview URL.

Preview execution is manual-only until this gate is intentionally activated. The adapter cannot target production.

## Operational GitHub alerts

Ready only when all of these are true:

- `FACTORY_GITHUB_ALERTS_ENABLED=true`;
- `GITHUB_TOKEN` is available to the job;
- `FACTORY_ALERTS_GITHUB_REPOSITORY` identifies the alert destination.

Alert publication remains opt-in and deduplicated by deterministic alert code.
