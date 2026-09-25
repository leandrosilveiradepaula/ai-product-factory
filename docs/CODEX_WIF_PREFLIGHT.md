# Codex workload identity: GitHub Actions preflight

This repository includes a manual preflight workflow for Codex workload identity federation.

Required repository variables:

- `OPENAI_FEDERATION_RULE_ID`: the non-secret federation rule id downloaded/configured from the OpenAI Admin Portal.
- `OPENAI_WIF_AUDIENCE`: the exact GitHub OIDC audience accepted by the Codex workload identity provider/rule.

The workflow requests a fresh GitHub OIDC token using `id-token: write`, writes it to a protected absolute file, sets `OPENAI_IDENTITY_TOKEN_FILE`, installs the current Codex CLI, and runs `codex login status`.

The identity token is never committed, uploaded as an artifact, or printed. The scheduled Factory runner remains disconnected from Codex until this preflight succeeds and the routing policy explicitly selects Codex.
