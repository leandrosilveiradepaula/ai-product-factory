# Factory Console

The Console is a server-rendered control surface for AI Product Factory.

## Required environment

- `SUPABASE_URL`
- `SUPABASE_PUBLISHABLE_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`

The publishable key is used only to authenticate the operator with Supabase Auth. The service role remains server-side and is used only after the authenticated user is confirmed in `factory_console_operators`.

## Operator bootstrap

1. Create the user in Supabase Auth.
2. Insert that user's UUID into `public.factory_console_operators` with role `operator` or `admin`.
3. Configure the three environment variables above.
4. Sign in through `/login`.

There is intentionally no public sign-up flow.

## Human gates

Pending gates are created when routing determines that human authority is required. Authorized Console operators can approve or reject them from `/decisions`. Resolution is persisted in the Control Plane and written to the audit log.

Do not expose the Console publicly without the auth environment configured.
