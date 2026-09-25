# Deployment adapters

Deployment is split into authorization and provider execution.

The coordinator verifies that the evidence belongs to the candidate commit, CI succeeded, the quality gate did not fail, and the environment/risk policy permits autonomous release.

Provider adapters implement only the final deployment operation. This keeps Vercel, Supabase, Watson Orchestrate, Docker/n8n, and future platforms outside the policy core.

No real provider is called by the contract tests. Production remains human-gated.
