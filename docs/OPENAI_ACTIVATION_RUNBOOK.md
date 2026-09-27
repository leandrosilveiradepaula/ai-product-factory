# OpenAI Activation Runbook

Last reconciled: 2026-09-27.

This runbook deliberately separates **Codex workspace authentication** from **OpenAI API Platform authentication and billing**.

They are different products, identities, control planes, and billing domains.

---

## Track A — Codex workload identity

### Purpose

Allow the selective Factory Codex worker to execute through the managed ChatGPT workspace without storing a long-lived ChatGPT credential or API key.

### External prerequisite

Codex workload identity federation is beta and must be enabled for the managed ChatGPT workspace by OpenAI.

Do not proceed with invented federation values.

### Factory-side GitHub contract

The Codex job runs in GitHub Environment:

`openai-codex`

Expected GitHub OIDC subject:

`repo:leandrosilveiradepaula/ai-product-factory:environment:openai-codex`

Other deterministic claims to require:

- `repository = leandrosilveiradepaula/ai-product-factory`
- `ref = refs/heads/main`
- `environment = openai-codex`

GitHub OIDC issuer:

`https://token.actions.githubusercontent.com`

The audience is administrator-owned. Configure the real value in OpenAI and then copy the same exact value to GitHub variable `OPENAI_WIF_AUDIENCE`.

### OpenAI Admin Portal procedure

After WIF beta is enabled:

1. Open **Workload identity** in the OpenAI Admin Portal.
2. Select **Connect workload**.
3. Create or reuse a GitHub Actions OIDC provider.
4. Configure the GitHub issuer.
5. Configure the administrator-selected accepted audience.
6. Select **Codex** and the managed Infodive workspace.
7. Restrict the rule to the exact Factory subject/claims above.
8. Map the rule to an existing ChatGPT principal or dedicated service account.
9. Keep access scopes minimal.
10. Create the rule and download its configuration.

Required Factory values after creation:

- `OPENAI_FEDERATION_RULE_ID=idpm_...`
- `OPENAI_WIF_AUDIENCE=<real configured audience>`

The runtime writes the GitHub OIDC token to the protected path already configured as `OPENAI_IDENTITY_TOKEN_FILE`.

### Activation order

1. Configure `OPENAI_FEDERATION_RULE_ID`.
2. Configure `OPENAI_WIF_AUDIENCE`.
3. Leave `FACTORY_CODEX_ENABLED=false`.
4. Run the manual **Codex WIF preflight** after GitHub Actions quota is available.
5. Confirm `codex login status` succeeds under WIF.
6. Run one bounded non-production Codex smoke.
7. Confirm the durable `factory_codex_usage` ledger increments only for the real invocation.
8. Only then set `FACTORY_CODEX_ENABLED=true`.

Do not use an unofficial ChatGPT token as a fallback.

---

## Track B — OpenAI API Platform

### Purpose

Allow Primary/Direct execution to call the OpenAI Responses API.

This is independent of the ChatGPT Business workspace and its credits.

### Authentication options

The Factory supports:

1. OpenAI API key; or
2. OpenAI API Workload Identity Federation.

WIF is preferred when configured. Partial WIF configuration fails closed and cannot silently fall back to an API key.

### Factory-side GitHub contract

Primary jobs run in GitHub Environment:

`openai-api`

Expected GitHub OIDC subject:

`repo:leandrosilveiradepaula/ai-product-factory:environment:openai-api`

Recommended exact mapping checks:

- `repository = leandrosilveiradepaula/ai-product-factory`
- `ref = refs/heads/main`
- `environment = openai-api`

GitHub OIDC issuer:

`https://token.actions.githubusercontent.com`

The audience is administrator-owned. The OpenAI provider and GitHub variable must use the same exact value.

### OpenAI Platform procedure for API WIF

1. Open **Organization Settings > Security > Workload Identity Provider**.
2. Create a GitHub Actions provider.
3. Set issuer to GitHub's OIDC issuer.
4. Set the chosen audience.
5. Use GitHub OIDC discovery; do not upload a custom JWKS for GitHub.
6. Create or select a service account in the target API Platform project.
7. Create one service-account mapping for the provider/service-account pair.
8. Restrict the mapping to the exact Factory repository, main ref and `openai-api` environment.
9. Grant only the API permissions the Factory requires.

Record:

- `OPENAI_IDENTITY_PROVIDER_ID=idp_...`
- `OPENAI_SERVICE_ACCOUNT_ID=svc_acct_...`
- `OPENAI_WIF_AUDIENCE=<real configured audience>`

At runtime the Factory requests a GitHub OIDC token, exchanges it at:

`https://auth.openai.com/oauth/token`

and sends the resulting short-lived bearer token to the Responses API.

### Billing is a separate gate

API WIF does **not** grant free API usage and does not reuse ChatGPT Business workspace credits.

Current known state:

- connected Platform target: organization `Personal`, project `Default project`;
- a previous API-key request reached the API but returned HTTP 429/quota;
- the available connector does not expose live API billing balance.

Before enabling Primary execution, an API organization owner must verify API billing/quota directly in the API Platform billing settings.

Do not add balance automatically.

### Primary activation order

1. Confirm either API key or complete API WIF is configured.
2. Confirm API Platform billing/quota permits the bounded smoke.
3. Confirm `FACTORY_MODEL_BUDGET_USD` has an explicit approved value.
4. Confirm `FACTORY_MODEL_RESERVE_USD` is set.
5. Keep `FACTORY_PRIMARY_MODEL_ENABLED=false`.
6. Run exactly one bounded smoke after GitHub Actions quota is available.
7. Verify the Control Plane usage/cost ledger.
8. Only then set `FACTORY_PRIMARY_MODEL_ENABLED=true`.

---

## Current external blockers

### Codex

- WIF beta enablement/federation rule is still not confirmed.
- No support response with the rule or enablement confirmation has been found.
- The user has confirmed the Infodive ChatGPT workspace currently has credits.

### API Platform

- Billing/quota state cannot be read through the connected Platform tool.
- A prior request returned quota/billing-related HTTP 429.
- No additional paid request is justified until billing/quota is explicitly verified.

### Shared infrastructure

- GitHub Actions daily quota is currently exhausted/limited, so preflights cannot be treated as executed until a runner is actually allocated.
