# Factory Console

The Console is a server-rendered control surface for AI Product Factory.

## Required environment

- `SUPABASE_URL`
- `SUPABASE_PUBLISHABLE_KEY`
- `SUPABASE_SECRET_KEY` (preferred server-side key)
- `SUPABASE_SERVICE_ROLE_KEY` (legacy fallback only)
- `FACTORY_BOOTSTRAP_ADMIN_EMAIL` for the one-time first-admin allowlist

The publishable key authenticates the operator. Privileged Supabase access remains server-side; the Console prefers `SUPABASE_SECRET_KEY` and accepts the legacy service-role key only as fallback, after identity/role checks.

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

Pending gates are created when routing determines that human authority is required. Authorized Console operators can approve or reject them from `/gates`. The legacy `/decisions` route redirects there. Resolution is persisted in the Control Plane and written to the audit log.

Do not expose the Console publicly without the auth environment configured.

## Operational surfaces

The Console exposes real Control Plane data through server-rendered routes:

- `/` — Factory Overview
- `/projects` and `/projects/[key]` — portfolio and project operations
- `/projects/new` — New Work intake
- `/runs` and `/runs/[id]` — run history and evidence detail
- `/queue` — executable Work Queue
- `/gates` — Human Gates
- `/evals` — evaluation evidence
- `/deployments` — deployment/preview/release evidence
- `/usage` — Models & Usage ledger
- `/audit` — audit trail
- `/configuration` — non-secret project configuration
- `/admin/operators` — operator administration

Secrets, provider credentials, and GitHub tokens must never be rendered into these routes.
