# Greenfield GitHub repository onboarding (fail-closed)

The Service Desk project's model-backed Discovery/Specification/Planning completed and its four product decisions were approved. The Control Plane project `infodive-service-desk` has a real 13-task engineering plan but `repository=NULL`; the implementation executor cannot safely write issues, commits or PRs without a verified target repository.

## Operator flow

The Console project detail offers three explicit steps for active greenfield projects with no repository:
1. Create `leandrosilveiradepaula/<project-key>` as a **private** GitHub repository with an initial README on `main` (human, GitHub UI). The Factory GitHub App cannot create personal repositories using its existing installation permissions.
2. Add that exact repository to the existing **Infodive AI Product Factory** GitHub App installation (human GitHub permission grant, not implied by a Factory click).
3. Press **Verificar e vincular repositório** in the Console (authenticated Factory admin + same-origin POST). The server uses only a short-lived repo-scoped App installation token. It rejects public, missing, empty, archived, disabled or wrong-owner repositories; verifies the exact main ref and write capabilities; rejects reuse by a different Factory project (even when that project is inactive); and binds the project once via a conditional project update. The existing `factory_record_project_github_access` privileged RPC persists observed capabilities and audit evidence.

App installation and repository binding are separate operations. A binding is never treated as sufficient without a subsequent successful project capability verification. Failures preserve an unverified/blocked status; token/private key are never exposed to the browser or run code.

## Production, cost and acceptance gates

This change modifies `apps/console/**` and must receive exact-SHA Vercel Preview READY and browser evidence before human production merge. The consolidated candidate includes the budget-blocker visibility fix from PR #857 and repository onboarding. One exact-SHA Preview plus browser evidence validates both UI changes after the provider's rate-limit clears. An ignored build or a completed deployment on another SHA is not evidence for this candidate. Do not bypass preview by merging unverified Console code.

No paid models or API credits are used. The Factory's total model budget US$4.00 and reservation US$0.50 remain unchanged. Service Desk's corrected run `d5f1ea54` stays at `created` until separate cost readiness, and no repo-setup click may trigger or duplicate it. No automatic merge is added.

This endpoint is narrowly scoped to the existing personal owner `leandrosilveiradepaula` and a repository slug equal to the greenfield project's immutable key. Other owners, aliases and existing-project remapping require separate, explicitly reviewed requirements; do not silently widen access.

## Slow-link operator feedback (15/10/2026)

The Service Desk was linked and its GitHub App capabilities recorded as `ready` with audit evidence at 22:11:21 UTC, but the operator reported a noticeable wait after pressing the verification button. The original handler deliberately performs a pre-write installation/repository check and then an authoritative post-link capability check; it includes multiple remote GitHub API reads. No end-to-end request-duration measurement is available, so the exact bottleneck is not established.

The post-link verification now performs only independent read-only GitHub capability probes in parallel (with a second parallel pair after reading the exact default-branch SHA). Missing capabilities, GitHub failures, token scope checks, audit RPC, admin authorization and conditional repository update remain unchanged and fail closed. The browser retains native HTML POST/303 navigation and displays an immediate progress label, screen-reader status and a same-page duplicate-click guard; server-side idempotency remains mandatory when JS is unavailable. No automatic retry, paid API, deployment, policy widening or model execution is introduced. Changes to the Console require SHA-exact Preview and human release merge before production claims.
