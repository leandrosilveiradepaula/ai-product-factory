# Runtime authentication boundaries

The Factory keeps OpenAI API authentication separate from Codex workspace authentication.

## OpenAI API

An API key authenticates a Platform project. API workload identity federation maps a workload to a Platform service account and is supported by the Factory through the official `OPENAI_IDENTITY_PROVIDER_ID`, `OPENAI_SERVICE_ACCOUNT_ID`, and `OPENAI_WIF_AUDIENCE` configuration. In GitHub Actions the runtime requests a short-lived GitHub OIDC assertion and exchanges it for a short-lived OpenAI access token. This improves credential security, but it does not turn ChatGPT workspace credits into API balance.

## Codex workspace automation

Codex workload identity federation maps a trusted workload to a user or service account in a managed ChatGPT workspace. This is the supported path for unattended Codex automation that should use the workspace's Codex access/allowance.

Codex WIF uses `OPENAI_FEDERATION_RULE_ID` plus an absolute `OPENAI_IDENTITY_TOKEN_FILE`. The audience is consumed by the external token-minting layer, not by Codex itself.

Codex WIF is currently beta and must be enabled for the managed workspace. The administrator configures the provider/rule in the OpenAI Admin Portal and maps restrictive GitHub OIDC claims (repository, ref/workflow) to the intended workspace principal.

The runtime deliberately does not accept a generic CHATGPT_ACCESS_TOKEN environment variable. Long-lived ChatGPT credentials are not the Factory's unattended-auth strategy.

## Factory policy

- Direct/primary API execution stays disabled when no supported API auth is available.
- Codex WIF capability is detected separately and never silently substituted for the primary API route.
- No workload identity token is stored in the repository or Control Plane.
- GitHub Actions should mint short-lived OIDC assertions with id-token: write only in the job that needs them.


## Current Primary authentication mode

As of 2026-09-28 the operational Primary path is explicitly
`FACTORY_PRIMARY_AUTH_MODE=api_key`. The user manually funded the API Platform
and one bounded billing smoke succeeded before activation. Runtime execution is
enabled only through the metered Factory workers with a US$ 4.00 total Factory
budget and US$ 0.50 per-call/run reservation.

The configured API WIF values remain present for hardening work tracked in
#250, but they are not the active runtime auth path until the no-model WIF
preflight succeeds. Explicit `api_key` mode prevents a configured-but-invalid
WIF mapping from shadowing the approved API-key path.

Legacy manual workflows and the `openai-execute` CLI command that could call a
paid model outside the Control Plane ledger were retired. Operational paid
calls must have a durable Factory `run_id`, pre-reserve cost, replace the
reservation with measured cost after success, and fail closed on unknown cost.
