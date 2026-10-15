# Greenfield GitHub repository onboarding (fail-closed)

The Service Desk project's model-backed Discovery/Specification/Planning completed and its four product decisions were approved. The Control Plane project `infodive-service-desk` has a real 13-task engineering plan but `repository=NULL`; the implementation executor cannot safely write issues, commits or PRs without a verified target repository.

## Operator flow

The Console project detail offers three explicit steps for active greenfield projects with no repository:
1. Create `leandrosilveiradepaula/<project-key>` as a **private** GitHub repository with an initial README on `main` (human, GitHub UI). The Factory GitHub App cannot create personal repositories using its existing installation permissions.
2. Add that exact repository to the existing **Infodive AI Product Factory** GitHub App installation (human GitHub permission grant, not implied by a Factory click).
3. Press **Verificar e vincular repositório** in the Console (authenticated Factory admin + same-origin POST). The server uses only a short-lived repo-scoped App installation token. It rejects public, missing, empty, archived, disabled or wrong-owner repositories; verifies the exact main ref and write capabilities; rejects reuse by a different Factory project; and binds the project once via a conditional project update. The existing `factory_record_project_github_access` privileged RPC persists observed capabilities and audit evidence.

App installation and repository binding are separate operations. A binding is never treated as sufficient without a subsequent successful project capability verification. Failures preserve an unverified/blocked status; token/private key are never exposed to the browser or run code.

## Production, cost and acceptance gates

This change modifies `apps/console/**` and must receive exact-SHA Vercel Preview READY and browser evidence before human production merge. The Vercel rate limit observed for PR #857 is not evidence for or against this candidate. Do not bypass preview by merging unverified Console code.

No paid models or API credits are used. The Factory's total model budget US$4.00 and reservation US$0.50 remain unchanged. Service Desk's corrected run `d5f1ea54` stays at `created` until separate cost readiness, and no repo-setup click may trigger or duplicate it. No automatic merge is added.

This endpoint is narrowly scoped to the existing personal owner `leandrosilveiradepaula` and a repository slug equal to the greenfield project's immutable key. Other owners, aliases and existing-project remapping require separate, explicitly reviewed requirements; do not silently widen access.
