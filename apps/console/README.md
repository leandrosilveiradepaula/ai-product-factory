# Factory Console

The Console is a server-rendered control surface for AI Product Factory.

## Required environment

- `SUPABASE_URL`
- `SUPABASE_PUBLISHABLE_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `FACTORY_BOOTSTRAP_ADMIN_EMAIL` for the one-time first-admin allowlist

The publishable key authenticates the operator. The service role remains server-side and is used only after identity/role checks.

## First admin bootstrap

1. Create the intended administrator in Supabase Auth.
2. Set `FACTORY_BOOTSTRAP_ADMIN_EMAIL` to that exact email.
3. Sign in through `/login`.
4. If no operator exists yet, the server-only bootstrap RPC grants that authenticated allowlisted user the `admin` role.
5. After the first admin exists, bootstrap refuses to grant another first-admin role.

There is intentionally no public sign-up flow and the Console never creates Supabase Auth users.

## Operator management

Admins can open `/admin/operators` and grant/revoke Console access only for users that already exist in Supabase Auth. Mutations use service-role-only RPCs and the database revalidates that the actor is an active admin.

## Human gates

Pending gates are created when routing determines that human authority is required. Authorized Console operators can approve or reject them from `/decisions`. Resolution is persisted in the Control Plane and written to the audit log.

Do not expose the Console publicly without the auth environment configured.
