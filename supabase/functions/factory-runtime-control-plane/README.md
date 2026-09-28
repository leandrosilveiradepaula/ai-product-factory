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
- exact workflow `.github/workflows/autonomous-runner.yml` or the dedicated `.github/workflows/control-plane-oidc-preflight.yml`;
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
query and never calls a model.
