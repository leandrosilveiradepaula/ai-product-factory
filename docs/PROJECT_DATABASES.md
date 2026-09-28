# Project database capability

The Factory treats an application database as a project-scoped integration, not as a global Factory credential.

## Existing Supabase project

1. Discover and persist the Supabase project ref from repository evidence or operator input.
2. Register only non-secret metadata in `factory_project_databases`.
3. Use either:
   - a scoped Supabase Personal Access Token limited to the project/organization; or
   - a Supabase OAuth integration for projects owned outside the Factory operator's organization.
4. Prefer read-only Database permission for reconciliation/audit work.
5. Verify identity with `GET /v1/projects/{ref}`.
6. Inspect schema/state with the Management API read-only SQL endpoint.
7. Upgrade to read-write only when an approved implementation actually needs database changes.

The credential value is never stored in the Control Plane. `credential_ref` is only an opaque pointer to the protected runtime secret/credential provider.

Classic account-wide PATs are not the default because their blast radius includes current and future projects.

## New project

The Factory may prepare a Supabase provision request during planning, including project name, organization, region policy and desired compute. It must not create the project automatically.

Creating a Supabase project is an external infrastructure/cost action. The runtime must stop at a human gate before calling `POST /v1/projects`. After approval:

1. generate a unique strong database password in the trusted runtime;
2. create the project with the Management API;
3. wait for required services to become `ACTIVE_HEALTHY`;
4. obtain modern publishable/secret API keys when supported;
5. persist only the project ref and non-secret readiness evidence in the Control Plane;
6. put credentials only in protected server-side secret storage;
7. use a development branch/environment for schema work where available;
8. run security advisors before production release.

Production data loss, destructive migrations, access expansion and production release remain human gates independent of project creation approval.

## CRM pilot

Repository evidence identifies the CRM Supabase project ref as `mpmhmjepmmpxbsmekldf`. The currently connected Supabase identity cannot access it. Registering the ref does not grant access.

The correct next state is `pending_access` until a project-scoped credential or OAuth grant is supplied. The first verification credential should be read-only because the current CRM task is read-only.
