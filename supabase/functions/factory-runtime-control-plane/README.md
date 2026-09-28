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
- exact workflow `.github/workflows/autonomous-runner.yml`;
- events `schedule` and `workflow_dispatch`.

Only GET/POST/PATCH calls to `/rest/v1/factory_*` and
`/rest/v1/rpc/factory_*` are proxied. Auth/admin/storage endpoints and
non-Factory tables are rejected.

The Supabase secret/service-role key remains only inside the managed Edge
Function environment. It is never returned to GitHub Actions.
