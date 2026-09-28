# OpenAI Activation Runbook

Last reconciled: 2026-09-28.

This runbook deliberately separates **Codex workspace authentication** from **OpenAI API Platform authentication and billing**.

They are different products, identities, control planes, and billing domains.

---

## Track A — Codex workspace authentication

### Purpose

Allow the selective Factory Codex worker to execute through the managed ChatGPT workspace with an official non-interactive credential. WIF remains the preferred path because it avoids a stored long-lived OpenAI credential; while the beta is unavailable, the Factory may use an official `CODEX_ACCESS_TOKEN` stored only as a GitHub Environment secret.

### Authentication choices

Preferred: Codex workload identity federation, which is beta and must be enabled for the managed ChatGPT workspace by OpenAI.

Fallback: official `CODEX_ACCESS_TOKEN` for trusted non-interactive automation. Store it only as an encrypted secret in GitHub Environment `openai-codex`. Do not persist browser cookies, scraped ChatGPT sessions, or unofficial tokens.

Do not proceed with invented federation values.

### Factory-side GitHub contract

The Codex job runs in GitHub Environment:

`openai-codex`

Expected GitHub OIDC subject:

`repo:leandrosilveiradepaula@256917842/ai-product-factory@1387883686:environment:openai-codex`

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
4. Ensure the managed Codex security requirements deny model-controlled reads of the identity-token directory with `permissions.filesystem.deny_read`.
5. Run the manual **Codex WIF preflight** after GitHub Actions quota is available. The preflight first validates the GitHub OIDC claims locally and refuses a repository/ref/environment mismatch.
6. Confirm `codex login status` succeeds under WIF.
7. Run one bounded non-production Codex smoke.
8. Confirm the durable `factory_codex_usage` ledger increments only for the real invocation.
9. Only then set `FACTORY_CODEX_ENABLED=true`.

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

`repo:leandrosilveiradepaula@256917842/ai-product-factory@1387883686:environment:openai-api`

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

- the user manually added US$ 5 of API Platform credit on 2026-09-28;
- bounded billing smoke run `36413373572` succeeded with exact output `FACTORY_SMOKE_OK`, 44 total tokens and estimated cost US$ 0.0000178;
- Primary is explicitly active through `FACTORY_PRIMARY_AUTH_MODE=api_key`;
- the Factory budget is US$ 4.00 with a US$ 0.50 per-call/run reservation, leaving US$ 1.00 of the original funding outside the Factory budget;
- the durable ledger pre-reserves cost before provider use and unknown paid cost blocks later paid execution;
- API WIF #250 is now authentication hardening, not a blocker for the approved API-key path.

Do not add balance or enable auto-reload automatically.

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

- Primary API billing/quota has been proven by one bounded paid smoke and the API-key path is active.
- API WIF token exchange remains blocked by the service-account mapping mismatch tracked in #250.
- Do not repeat paid smoke calls merely to probe WIF readiness; the WIF preflight is explicitly no-model.

### Shared infrastructure

- GitHub Actions runners are currently available during the temporary public-repository window. The API WIF no-model preflight has executed for real; the current blocker is the OpenAI service-account mapping mismatch, not runner capacity.


### Codex runtime token lifecycle

For GitHub Actions, the trusted host obtains the GitHub OIDC JWT and writes it outside the repository checkout. The worker validates the token's exact issuer, audience, subject, repository, branch and environment before writing it. The file is replaced atomically with mode `0600` inside a mode `0700` directory.

During an active Codex worker run, the host refreshes the GitHub OIDC token every 240 seconds. The Codex process receives only the federation-rule ID, absolute identity-token file path and optional audit context. GitHub credentials and OpenAI API keys remain excluded from the Codex subprocess environment.

Codex CLI remains pinned to `0.157.0`, which is newer than the documented WIF minimum `0.148.0`.


## Current API WIF deployment state

Configured on 2026-09-27.

OpenAI Platform:
- provider: `github-actions-ai-product-factory`
- provider ID: `idp_cc3f1adbaa5185a08932c2e9`
- issuer: `https://token.actions.githubusercontent.com`
- audience: `https://api.openai.com/v1`
- project: `Default project`
- service account: `ai-product-factory-primary`
- service account ID: `user-964d27e5d9d6b216dd475e06`
- permissions: Restricted; Model capabilities Request with Responses `/v1/responses` Write
- intended mapping: exact `iss`, `aud`, immutable `sub`, `repository`, `ref=refs/heads/main`, and `environment=openai-api`; the current mapping is not yet accepted by OpenAI and must be corrected against the observed token

GitHub:
- Environment `openai-api` exists;
- environment variables `OPENAI_IDENTITY_PROVIDER_ID`, `OPENAI_SERVICE_ACCOUNT_ID`, and `OPENAI_WIF_AUDIENCE` are configured;
- Environment `openai-codex` also exists but intentionally has no Codex WIF values yet.

Activation status:
- GitHub OIDC issuance: verified working;
- token exchange: currently blocked by `HTTP 401 / invalid_grant` with message `The provided service_account_id mapping does not match token attributes.`;
- actual immutable GitHub subject observed: `repo:leandrosilveiradepaula@256917842/ai-product-factory@1387883686:environment:openai-api`;
- administrator action required: reconcile the OpenAI Platform service-account mapping to the actual token attributes, then rerun the no-model preflight;
- billing/model execution: operational through the approved API-key path after the successful bounded smoke;
- `FACTORY_PRIMARY_MODEL_ENABLED=true` is active only in the budgeted/metered runtime;
- `FACTORY_PRIMARY_AUTH_MODE=api_key` is explicit while #250 remains unresolved;
- `OPENAI_API_KEY`: retain as the current approved runtime credential until WIF preflight succeeds, then review migration/removal.


### Temporary access-token path

Until Codex WIF is enabled for the Infodive workspace, the Factory may use the official Codex access-token path.

1. Create an official Codex access token from the workspace access-token administration surface.
2. Give it the shortest practical expiration and only the Codex access required for this automation.
3. Store the value once as GitHub Environment secret `CODEX_ACCESS_TOKEN` under `openai-codex`.
4. Leave all WIF variables unset in that environment. Partial WIF blocks token fallback by design.
5. Keep `FACTORY_CODEX_ENABLED=false`.
6. Run the manual **Codex auth preflight**. It installs the pinned CLI and runs only `codex login status`; no Codex task/model execution is requested.
7. Preserve successful workflow evidence.
8. Run one bounded non-production Codex task and verify the durable invocation ledger.
9. Only then enable `FACTORY_CODEX_ENABLED=true`.

Credential precedence is WIF > official access token. Access-token creation/revocation is a human credential action and is never automated by the Factory.


## Retired paid shortcuts

The historical `openai-runtime.yml`, `openai-runtime-execute.yml` and
one-shot billing-smoke workflow were retired after activation. The
`ai-product-factory openai-execute` CLI shortcut was also removed because it
could call the provider without the durable Control Plane cost ledger.

Use the normal Factory product/direct workers for paid operational execution.
Use `openai-api-wif-preflight.yml` for WIF readiness because it performs no
model call.
