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

## Design system

The operational Console has a centralized presentation layer:

- `app/theme.css` is the single source for typography, palette, semantic status colors, radii, spacing and shared visual effects;
- `app/globals.css` implements layout/component classes by consuming those tokens rather than owning the theme;
- `app/ui.tsx` contains reusable primitives for page headers, metrics, status pills, section headers, empty states and shared actions.

Global visual changes should start in `theme.css`. For example, changing `--font-sans` changes the Console typography without editing individual screens. Status meaning remains semantic: success, warning, danger and accent are mapped centrally.

Business actions remain outside the visual primitives. UI components render the control; authorization and state transitions continue through the server-side Control Plane functions.

## Production release branch

Production is intentionally decoupled from ordinary `main` pushes to protect the Vercel deployment budget.

- Console feature branches use `console/**` and remain eligible for Vercel Preview.
- Vercel Git deployment is disabled for `main`.
- The Vercel project Production Branch is `console-production`.
- After a human merges a PR to `main`, `.github/workflows/console-production-release.yml` advances `console-production` only when that merge changed `apps/console/**`.
- The workflow verifies the exact `main` SHA is associated with a merged PR and refuses branch rewinds.
- `console-production` is generated release state; do not push to it manually.

This keeps production human-gated at the PR merge while preventing backend-only Factory merges from creating Vercel deployment records.
