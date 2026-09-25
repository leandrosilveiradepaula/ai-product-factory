# Runtime authentication boundaries

The Factory keeps OpenAI API authentication separate from Codex workspace authentication.

## OpenAI API

An API key authenticates a Platform project. API workload identity federation maps a workload to a Platform service account. This improves credential security, but it does not turn ChatGPT workspace credits into API balance.

## Codex workspace automation

Codex workload identity federation maps a trusted workload to a user or service account in a managed ChatGPT workspace. This is the supported path for unattended Codex automation that should use the workspace's Codex access/allowance.

Codex WIF is currently beta and must be enabled for the managed workspace. The administrator configures the provider/rule in the OpenAI Admin Portal and maps restrictive GitHub OIDC claims (repository, ref/workflow) to the intended workspace principal.

The runtime deliberately does not accept a generic CHATGPT_ACCESS_TOKEN environment variable. Long-lived ChatGPT credentials are not the Factory's unattended-auth strategy.

## Factory policy

- Direct/primary API execution stays disabled when no supported API auth is available.
- Codex WIF capability is detected separately and never silently substituted for the primary API route.
- No workload identity token is stored in the repository or Control Plane.
- GitHub Actions should mint short-lived OIDC assertions with id-token: write only in the job that needs them.
