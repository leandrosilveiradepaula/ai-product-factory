# Codex workload identity: GitHub Actions preflight

This repository includes a manual preflight workflow for Codex workload identity federation.

Required repository variables:

- `OPENAI_FEDERATION_RULE_ID`: the non-secret federation rule id downloaded/configured from the OpenAI Admin Portal.
- `OPENAI_WIF_AUDIENCE`: the exact GitHub OIDC audience accepted by the Codex workload identity provider/rule.

The workflow requests a fresh GitHub OIDC token using `id-token: write`, writes it to a protected absolute file, sets `OPENAI_IDENTITY_TOKEN_FILE`, installs the current Codex CLI, and runs `codex login status`.

The identity token is never committed, uploaded as an artifact, or printed. The scheduled Factory runner remains disconnected from Codex until this preflight succeeds and the routing policy explicitly selects Codex.


## Immutable GitHub subject

For this repository, GitHub issues the immutable subject format that includes stable owner and repository IDs:

`repo:leandrosilveiradepaula@256917842/ai-product-factory@1387883686:environment:openai-codex`

The trusted host validates `GITHUB_REPOSITORY_OWNER_ID` and `GITHUB_REPOSITORY_ID` against that subject before writing the identity token. Do not configure the Codex federation rule with the legacy subject form that omits these IDs.
