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
- runtime events `schedule`/`workflow_dispatch`, plus `push` only for the dedicated preflight workflow.

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

The dedicated preflight workflow performs a read-only `factory_projects`
query and never calls a model. The cross-repo Preview browser workflow is manual-only; it uses the broker to resolve a repository-scoped GitHub App token, reads the exact target candidate's Vercel checks/statuses, delegates browser execution to the trusted Factory verifier, and persists a new historical `factory_project_state_snapshots` record. It does not pass the GitHub token to the browser and does not write to the target repository.

## GitHub App installation token broker

The trusted autonomous runner may call `POST /github-app/token` with only an exact `owner/repo`.
The broker reuses the already-verified project access record and only proceeds when
`auth_mode=github_app`, `status=ready`, and both installation/repository IDs are present.
It reads the App private key from Vault through the privileged RPC, signs the short-lived
App JWT inside the Edge Function, and asks GitHub for an installation token restricted to
that exact repository ID and the reviewed permission set. The private key and App JWT are
never returned to GitHub Actions. Token minting is accepted only from exact trusted `main` workflow identities: the autonomous runner for its approved runtime events, the CRM cross-repo preflight, and the manual cross-repo Preview browser workflow. The general OIDC preflight workflow cannot mint GitHub installation tokens. The broker also re-reads the repository with the minted token and confirms the exact repository ID/full name before returning it. The response contains only the short-lived installation
token plus non-secret expiry/ID metadata, and no token is persisted by the Factory.

