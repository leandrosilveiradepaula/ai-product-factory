# Supabase Runtime

The factory control plane is persisted in a dedicated Supabase project.

## Security model

- runtime access is server-side only;
- use `SUPABASE_SECRET_KEY`, never a publishable key;
- never commit the secret key;
- never expose the secret key to browser code;
- public client roles (`anon` and `authenticated`) have no grants on the control-plane tables;
- RLS remains enabled as defense in depth.

## Environment

```text
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SECRET_KEY=<server-side secret>
```

## Adapter

`SupabaseControlPlaneStore` implements the same contract as the in-memory store. This keeps orchestration logic independent from the persistence backend.

For tests, inject a fake transport. Production runtime uses PostgREST through the standard library HTTP client.
