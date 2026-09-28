# Authentication activation readiness

The Factory treats OpenAI API authentication and Codex workspace authentication as independent gates. Neither gate is inferred from the presence of a secret alone.

## Primary model

Ready only when all of these are true:

- either `OPENAI_API_KEY` is configured, or API workload identity is configured with `OPENAI_IDENTITY_PROVIDER_ID`, `OPENAI_SERVICE_ACCOUNT_ID`, `OPENAI_WIF_AUDIENCE`, and a runtime capable of minting the external OIDC token;
- API billing/quota is known to permit the intended workload. API WIF changes credential security, not billing/quota.
- a bounded smoke test has succeeded after quota/billing readiness is confirmed.
- `FACTORY_PRIMARY_MODEL_ENABLED=true` is explicitly set.

Current known state:
- API workload identity is configured in OpenAI Platform and GitHub for the Factory:
  - provider `github-actions-ai-product-factory`
  - provider ID `idp_cc3f1adbaa5185a08932c2e9`
  - project `Default project`
  - service account `ai-product-factory-primary`
  - service account ID `user-964d27e5d9d6b216dd475e06`
  - audience `https://api.openai.com/v1`
  - GitHub Environment `openai-api`
  - exact mapping checks for issuer, audience, repository, `refs/heads/main`, and `openai-api`
  - restricted model request access for `/v1/responses`
- the API WIF no-model preflight now runs during the temporary public Actions window. The real GitHub OIDC token is issued successfully, but OpenAI currently rejects the exchange with `HTTP 401 / invalid_grant` because the configured service-account mapping does not match the token attributes. The actual immutable GitHub subject is `repo:leandrosilveiradepaula@256917842/ai-product-factory@1387883686:environment:openai-api`; the OpenAI Platform mapping must be reconciled to these real claims before WIF is treated as ready;
- the user manually added US$ 5 of API Platform credit on 2026-09-28;
- bounded billing smoke run `36413373572` succeeded through `OPENAI_API_KEY` using GPT-5.6 Luna with `reasoning=none`, 32 max output tokens, exact output `FACTORY_SMOKE_OK`, 35 input tokens, 9 output tokens, and estimated cost US$ 0.0000178 under a US$ 0.01 ceiling; the evidence is persisted in the Control Plane;
- the existing `OPENAI_API_KEY` is retained temporarily while WIF #250 remains unresolved; `FACTORY_PRIMARY_MODEL_ENABLED` stays false until the user explicitly approves the operating budget and per-run reservation.

Keep `FACTORY_PRIMARY_MODEL_ENABLED` unset/false. Do not repeat paid calls merely to poll readiness and do not add credits automatically.

ChatGPT Business workspace credits are a separate balance and do not fund the API Platform. An OpenAI email dated 2026-09-04 reported the Infodive ChatGPT workspace out of credits at that time. The user has since confirmed that the workspace currently has credits. This historical email is not evidence of the current workspace balance and is not evidence of API Platform balance.

## Codex workspace authentication

The Factory supports two official Codex authentication paths:

1. Workload Identity Federation (preferred when available);
2. `CODEX_ACCESS_TOKEN` stored as a protected secret for trusted non-interactive automation.

Ready only when one complete official path is configured and the corresponding preflight succeeds.

- the managed OpenAI/ChatGPT workspace has an approved Workload Identity rule/provider.
- `OPENAI_FEDERATION_RULE_ID` contains the real administrator-provided rule id.
- the federation rule accepts the real audience used by the external OIDC provider;
- the GitHub Actions token-minting layer knows that audience (the Factory uses `OPENAI_WIF_AUDIENCE` for this purpose);
- GitHub Actions can mint the OIDC token into `OPENAI_IDENTITY_TOKEN_FILE`.
- the manual Codex auth preflight reaches a successful `codex login status`.
- `FACTORY_GITHUB_TOKEN` is configured with the minimum target-repository permissions needed by the delivery loop before cross-repository Codex execution.
- only after the preflight is preserved as evidence, `FACTORY_CODEX_ENABLED=true` is set.

Do not invent the federation rule id or audience. Codex itself receives only `OPENAI_FEDERATION_RULE_ID` and `OPENAI_IDENTITY_TOKEN_FILE`; `OPENAI_WIF_AUDIENCE` belongs to the token-issuance layer. If WIF is entirely absent, an official `CODEX_ACCESS_TOKEN` may be used instead. Any partial WIF configuration fails closed and must never fall back to the token.

Current commercial/admin state: Codex WIF is still beta and requires workspace enablement by OpenAI Support. On 2026-09-27 the Infodive workspace Admin Portal was inspected directly; the documented `Workload identity` section is absent in both available admin surfaces, confirming that the workspace has not yet received the Codex WIF beta/admin capability. No support response with a federation rule or enablement confirmation has been found. Issue #240 tracks this external blocker. Separately, the Infodive ChatGPT Business workspace had a historical out-of-credits notice on 2026-09-04, but the user has confirmed the workspace currently has credits. Do not infer current credit state from that historical email. The preflight is intentionally manual and does not execute a Codex task. The runtime and Actions worker remain fail-closed when any required value is absent; missing WIF must not be worked around with an API key, browser cookie, scraped session, or unofficial ChatGPT token. The official `CODEX_ACCESS_TOKEN` is the only supported stored-token fallback.

## Manual Codex path while unattended auth is blocked

The Factory does not need Codex WIF or a stored Codex access token for occasional operator-assisted Codex work.

When automatic Codex auth is unavailable:
- routing may still classify a task as Codex when complexity justifies it;
- the Factory prepares a durable GitHub handoff and waits in `awaiting_codex_manual`;
- the operator starts Codex using the existing managed ChatGPT Business login;
- the resulting PR carries the Factory run marker;
- the Factory adopts that PR and resumes from CI.

This is intentionally different from storing a human credential in GitHub. No ChatGPT login material enters the Factory. Automatic WIF/access-token support remains a future convenience, not a prerequisite for the core Factory to operate through API/Direct.

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

The Factory uses dedicated GitHub Environments so OpenAI workload identity can be restricted without trusting every workflow in the repository. GitHub repositories created under the current immutable OIDC subject scheme include stable owner and repository numeric IDs in `sub`; the Factory validates that real format rather than assuming the legacy owner/repository-only subject.

### API Platform workload identity

Jobs that may call the Primary model run in GitHub Environment `openai-api`.

Expected GitHub OIDC subject:

`repo:leandrosilveiradepaula@256917842/ai-product-factory@1387883686:environment:openai-api`

Recommended exact mapping checks in the OpenAI API Workload Identity Provider:

- `repository = leandrosilveiradepaula/ai-product-factory`
- `ref = refs/heads/main`
- `environment = openai-api`

The provider audience must be the exact administrator-configured audience. The Factory does not invent or hardcode it.

### Codex workload identity

The selective Codex worker runs in GitHub Environment `openai-codex`.

Expected GitHub OIDC subject:

`repo:leandrosilveiradepaula@256917842/ai-product-factory@1387883686:environment:openai-codex`

Recommended Codex federation-rule checks:

- exact external subject above, or equivalent exact claim checks;
- `repository = leandrosilveiradepaula/ai-product-factory`;
- `ref = refs/heads/main`;
- `environment = openai-codex`;
- the real accepted audience configured in the OpenAI Admin Portal.

This leaves the audience as an administrator-owned value while making all other GitHub claims deterministic in code.


### Codex GitHub Actions hardening

The Codex WIF preflight and worker run in GitHub Environment `openai-codex`. Before Codex sees the identity-token file, the trusted host code decodes the GitHub OIDC JWT locally and fails closed unless all expected claims match:

- `iss = https://token.actions.githubusercontent.com`
- `aud = <administrator-configured Codex audience>`
- `sub = repo:leandrosilveiradepaula@256917842/ai-product-factory@1387883686:environment:openai-codex`
- `repository = leandrosilveiradepaula/ai-product-factory`
- `ref = refs/heads/main`
- `environment = openai-codex`

The raw token is never logged. The token directory/file are created with restrictive permissions and the worker replaces the token atomically. A trusted host refresher renews GitHub OIDC every 240 seconds while a Codex implementation process is running so Codex can re-read a current source token if it needs a later exchange.

OpenAI also recommends a managed Codex requirement that denies model-controlled reads of the entire identity-token directory via `permissions.filesystem.deny_read`. This is a workspace/admin policy requirement and must be enabled as part of Codex rollout once managed WIF is available; file mode alone is not treated as sufficient protection.
