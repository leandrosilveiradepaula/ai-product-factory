## Restricted Console intake `repository_dispatch` identity (candidate; not deployed)

On 2026-10-15, the operator pressed **Iniciar desenvolvimento** for Service Desk. The existing GitHub App dispatch was accepted, creating autonomous runner run `38796434797`, but `schedule-probe` exited HTTP 403 on `factory_recover_expired_runs` because `verifyGithub` rejected every `repository_dispatch` OIDC identity. This is a broker event identity mismatch, not a missing GitHub App permission; `FACTORY_PRIMARY_MODEL_ENABLED=false` remains a separate paid-model readiness gate.

Candidate policy accepts `repository_dispatch` **only** when the OIDC JWT is issued for the exact trusted Factory `autonomous-runner.yml@refs/heads/main` and actor `infodive-ai-product-factory[bot]`. All immutable repository/owner/ref, issuer/audience, workflow allowlist, and workflow's exact event type/source guards remain. The `/github-app/token` endpoint **continues to reject** `repository_dispatch`. No other dispatch events or actors are authorized for the generic proxy. No credential, public RLS policy, model activation, payment, or merge automation is introduced.

**Production sensitive-access gate:** merging this code does **not** deploy the Supabase Edge broker. An authorized operator must review the exact diff and explicitly approve Edge Function deployment (access-identity change). Then repeat a single Service Desk start request and verify `schedule-probe` succeeds, Product Stage records model-readiness evidence, and the original run remains idempotent. Do not claim semantic Discovery has started while `FACTORY_PRIMARY_MODEL_ENABLED=false`.

## Backup scheduler workflow_run OIDC gate (candidate; not deployed)

During the 2026-10-14 17:04 UTC six-hour OIDC scheduled preflight, the downstream `Factory autonomous runner` launched via `workflow_run` failed with HTTP 403 at `SupabaseSchedulerLivenessReader`: the broker's `verifyGithub` explicitly rejected the `workflow_run` event. The upstream preflight itself passed. This change narrowly permits the signed `workflow_run` event **only when** the JWT's `workflow_ref` identifies the exact trusted main-branch `autonomous-runner.yml`. The existing issuer/audience, immutable repository/owner/ref checks, GitHub OIDC claim checks and generic proxy allowlist still apply. The runner job itself independently requires an upstream successful scheduled `Control Plane OIDC preflight` on the same repository and `main`.

**Sensitive access activation gate:** code/CI alone does not activate this change in the deployed Edge broker. Review the exact source SHA, verify no other workflows/events gain the generic proxy, and explicitly authorize deployment of the updated Edge Function in production. The `/github-app/token` route still **rejects** `workflow_run`; this patch does not grant cross-repository GitHub App minting to backup events. No paid model, preview, DB migration or auto-merge is needed for regression testing. After approval and deployment, verify one real `workflow_run` backup sequence and its durable audit before claiming liveness recovered. The actual native `schedule` heartbeat warning #790 remains open until two timely native events are confirmed.

# Factory runtime Control Plane broker

This Edge Function lets the trusted `Factory autonomous runner` use the
Supabase Control Plane without storing a Supabase privileged key in GitHub.

The caller presents a short-lived GitHub Actions OIDC token with audience
`factory-runtime-control-plane`. The broker verifies the token signature and
locks access to:

- repository `leandrosilveiradepaula/ai-product-factory`;
- immutable repository ID `1387883686`;
- immutable owner ID `256917842`;
- `refs/heads/main`;
- exact trusted workflows: `.github/workflows/autonomous-runner.yml`, `.github/workflows/control-plane-oidc-preflight.yml`, and `.github/workflows/cross-repo-preview-browser-evidence.yml`;
- runtime events `schedule`/`workflow_dispatch`; OWNER-authored `issue_comment` is also accepted for explicitly allowlisted workflows, and `push` remains limited to trusted preflight/reconciliation paths.

Only GET/POST/PATCH calls to `/rest/v1/factory_*` and
`/rest/v1/rpc/factory_*` are proxied. Auth/admin/storage endpoints and
non-Factory tables are rejected.

The Supabase secret/service-role key remains only inside the managed Edge
Function environment. It is never returned to GitHub Actions.


## GitHub Actions integration

The reusable local action at `.github/actions/control-plane-oidc/action.yml`
mints the GitHub OIDC token and exports it only for the current job. It points
the existing Supabase REST adapters at this broker, so the runtime does not
need a Supabase secret in GitHub.

The dedicated preflight workflow performs a read-only `factory_projects` query and never calls a model. The cross-repo Preview browser workflow can be started either with `workflow_dispatch` or by an OWNER-only issue comment in the exact form `/factory-browser-evidence owner/repo <40-char-sha> <expected text>`. The command is parsed fail-closed with bounded one-line expected text. The workflow uses the broker to resolve a repository-scoped GitHub App token, reads the exact target candidate's Vercel checks/statuses, delegates browser execution to the trusted Factory verifier, and persists a new historical `factory_project_state_snapshots` record. It does not pass the GitHub token to the browser and does not write to the target repository.

## GitHub App installation token broker

The trusted autonomous runner may call `POST /github-app/token` with only an exact `owner/repo`.
The broker reuses the already-verified project access record and only proceeds when
`auth_mode=github_app`, `status=ready`, and both installation/repository IDs are present.
It reads the App private key from Vault through the privileged RPC, signs the short-lived
App JWT inside the Edge Function, and asks GitHub for an installation token restricted to
that exact repository ID and the reviewed permission set. The private key and App JWT are
never returned to GitHub Actions. Token minting is accepted only from exact trusted `main` workflow identities: the autonomous runner for its approved runtime events, the CRM cross-repo preflight, and the manual cross-repo Preview browser workflow. The general OIDC preflight workflow cannot mint GitHub installation tokens. The broker also re-reads the repository with the minted token and confirms the exact repository ID/full name before returning it. The response contains only the short-lived installation
token plus non-secret expiry/ID metadata, and no token is persisted by the Factory.

