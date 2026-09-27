# Authentication activation readiness

The Factory treats OpenAI API authentication and Codex workspace authentication as independent gates. Neither gate is inferred from the presence of a secret alone.

## Primary model

Ready only when all of these are true:

- either `OPENAI_API_KEY` is configured, or API workload identity is configured with `OPENAI_IDENTITY_PROVIDER_ID`, `OPENAI_SERVICE_ACCOUNT_ID`, `OPENAI_WIF_AUDIENCE`, and a runtime capable of minting the external OIDC token;
- API billing/quota is known to permit the intended workload. API WIF changes credential security, not billing/quota.
- a bounded smoke test has succeeded after quota/billing readiness is confirmed.
- `FACTORY_PRIMARY_MODEL_ENABLED=true` is explicitly set.

Current known state: the existing key reached the API but returned HTTP 429/quota. The connected Platform account exposes a Personal organization with a Default project, but no available connector exposes live billing/credit balance. Keep `FACTORY_PRIMARY_MODEL_ENABLED` unset/false. Do not repeat paid calls merely to poll readiness.

ChatGPT Business workspace credits are a separate balance and do not fund the API Platform. An OpenAI email dated 2026-09-04 reported the Infodive ChatGPT workspace out of credits at that time. The user has since confirmed that the workspace currently has credits. This historical email is not evidence of the current workspace balance and is not evidence of API Platform balance.

## Codex workspace WIF

Ready only when all of these are true:

- the managed OpenAI/ChatGPT workspace has an approved Workload Identity rule/provider.
- `OPENAI_FEDERATION_RULE_ID` contains the real administrator-provided rule id.
- the federation rule accepts the real audience used by the external OIDC provider;
- the GitHub Actions token-minting layer knows that audience (the Factory uses `OPENAI_WIF_AUDIENCE` for this purpose);
- GitHub Actions can mint the OIDC token into `OPENAI_IDENTITY_TOKEN_FILE`.
- the manual `Codex WIF preflight` workflow reaches a successful `codex login status`.
- `FACTORY_GITHUB_TOKEN` is configured with the minimum target-repository permissions needed by the delivery loop before cross-repository Codex execution.
- only after the preflight is preserved as evidence, `FACTORY_CODEX_ENABLED=true` is set.

Do not invent the federation rule id or audience. Codex itself receives only `OPENAI_FEDERATION_RULE_ID` and `OPENAI_IDENTITY_TOKEN_FILE`; `OPENAI_WIF_AUDIENCE` belongs to the token-issuance layer.

Current commercial/admin state: Codex WIF is still beta and requires workspace enablement by OpenAI Support. No support response with a federation rule or enablement confirmation has been found. Separately, the Infodive ChatGPT Business workspace had a historical out-of-credits notice on 2026-09-04, but the user has confirmed the workspace currently has credits. Do not infer current credit state from that historical email. The preflight is intentionally manual and does not execute a Codex task. The runtime and Actions worker remain fail-closed when any required value is absent; missing WIF must not be worked around with an API key or an unofficial ChatGPT token.

## Activation order

1. Configure the external administrative values.
2. Run the relevant preflight once.
3. Preserve the workflow evidence.
4. Only then enable the corresponding execution adapter.
5. Scheduled Direct remains disabled until Primary readiness is proven.

Production deployment remains independently human-gated.

## Verified Preview

The standard GitHub Actions path is ready when:

- the project has an explicit Preview applicability/configuration policy in `manifest.preview`;
- a Preview is actually required for the PR's changed files;
- the repository has the official Vercel↔GitHub integration and project mode is `github`;
- the workflow can read GitHub checks with its native `GITHUB_TOKEN`;
- the manual Preview job can install its pinned Playwright/Chromium runtime;
- Playwright returns structured success evidence for the exact discovered Preview URL.

The manual job supplies `FACTORY_VERCEL_PREVIEW_ENABLED=true`, `FACTORY_BROWSER_EVIDENCE_ENABLED=true`, and the built-in browser command. It does not require an external browser service or `VERCEL_TOKEN` in `mode: github`.

For `mode: api` or non-GitHub execution environments, Vercel/browser credentials and commands remain explicit external configuration. Preview execution remains manual-only and no Preview adapter can target production.

## Operational GitHub alerts

Ready only when all of these are true:

- `FACTORY_GITHUB_ALERTS_ENABLED=true`;
- `GITHUB_TOKEN` is available to the job;
- `FACTORY_ALERTS_GITHUB_REPOSITORY` identifies the alert destination.

Alert publication remains opt-in and deduplicated by deterministic alert code.


## GitHub OIDC claim contract

The Factory uses dedicated GitHub Environments so OpenAI workload identity can be restricted without trusting every workflow in the repository.

### API Platform workload identity

Jobs that may call the Primary model run in GitHub Environment `openai-api`.

Expected GitHub OIDC subject:

`repo:leandrosilveiradepaula/ai-product-factory:environment:openai-api`

Recommended exact mapping checks in the OpenAI API Workload Identity Provider:

- `repository = leandrosilveiradepaula/ai-product-factory`
- `ref = refs/heads/main`
- `environment = openai-api`

The provider audience must be the exact administrator-configured audience. The Factory does not invent or hardcode it.

### Codex workload identity

The selective Codex worker runs in GitHub Environment `openai-codex`.

Expected GitHub OIDC subject:

`repo:leandrosilveiradepaula/ai-product-factory:environment:openai-codex`

Recommended Codex federation-rule checks:

- exact external subject above, or equivalent exact claim checks;
- `repository = leandrosilveiradepaula/ai-product-factory`;
- `ref = refs/heads/main`;
- `environment = openai-codex`;
- the real accepted audience configured in the OpenAI Admin Portal.

This leaves the audience as an administrator-owned value while making all other GitHub claims deterministic in code.
