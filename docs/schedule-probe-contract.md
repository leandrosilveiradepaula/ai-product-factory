# Schedule-probe contract discovery

## Scope

This document records the existing schedule-probe boundary that a telemetry implementation must preserve. It is a discovery artifact only; it does not add a table, write telemetry, alter probe behavior, or introduce an administrative UI.

## Probe implementation and invocation

| Concern | Authoritative location | Finding |
| --- | --- | --- |
| Scheduled invocation | `.github/workflows/schedule-probe.yml` | The workflow is the external scheduler and invokes the Supabase Edge Function on its configured schedule. |
| Probe implementation | `supabase/functions/schedule-probe/index.ts` | The Edge Function performs the work lookup and produces the probe result. |
| Authoritative work decision | `supabase/functions/schedule-probe/index.ts` | The boolean produced after the function's work lookup is the authoritative `work_detected` decision point. Telemetry must be derived at this point, rather than inferred from the workflow status, HTTP status, or a caller response. |

The workflow is an invocation mechanism only. A successful workflow or HTTP invocation does **not** mean work was detected; only the result of the lookup in the Edge Function does.

## Current normalized work classes

The current probe contract is boolean-only. It exposes an authoritative work/no-work decision but does not expose a normalized work-class discriminator.

| Outcome | Source value at the decision point | Normalized `work_detected` | Normalized `work_classes` |
| --- | --- | ---: | --- |
| Work found | The probe's computed work boolean is `true` | `true` | `[]` |
| No work found | The probe's computed work boolean is `false` | `false` | `[]` |
| Lookup, authentication, database, or unexpected execution failure | No authoritative boolean is available | Unknown; do not coerce to `false` | Not available; do not emit a successful observation |

Consequently, there are currently **no available normalized work-class source values** to persist. A future producer may populate `work_classes` only after it introduces an explicit, reviewed mapping at the authoritative decision point. It must not derive class names from raw records, request payloads, error text, or workflow metadata.

An error is not a no-work result. For a success-only telemetry table, the safe treatment is to write no observation when the decision cannot be made and rely on the existing function/workflow error path for failure reporting. If error observations are later required, they need a separately reviewed status/error contract rather than overloading `work_detected`.

## Supabase integration conventions

| Concern | Existing convention/location | Telemetry implication |
| --- | --- | --- |
| Migrations | `supabase/migrations/` | Add any telemetry schema as a timestamped SQL migration in this directory; do not perform runtime DDL from the Edge Function. |
| Edge Function runtime | `supabase/functions/schedule-probe/index.ts` | Keep writes in the Edge Function after the authoritative decision, using the same runtime and client-construction pattern as the probe. |
| Supabase client | `supabase/functions/schedule-probe/index.ts` | Reuse the function's server-side Supabase client pattern. Do not use a browser/anon client for telemetry writes. |
| Workflow secret injection | `.github/workflows/schedule-probe.yml` | The workflow supplies connection/invocation configuration through GitHub Actions secrets. Names and values must not be copied into telemetry, logs, migrations, or documentation. |
| Function secret injection | Supabase Edge Function environment used by `supabase/functions/schedule-probe/index.ts` | Continue to obtain privileged connection configuration from the function environment; never accept it from a request body or persist it. |
| Database access controls | SQL in `supabase/migrations/` | A telemetry table must follow the repository's existing ownership, grants, RLS, and policy conventions. Inserts should be limited to the server-side probe identity; untrusted clients must not be able to insert or modify observations. |

Before implementing the writer, inspect the most recent migrations in `supabase/migrations/` and mirror their precise SQL conventions for schema qualification, ownership, grants, RLS enablement, and policies rather than introducing a parallel access-control style.

## Minimal telemetry contract

A successful, sanitized probe observation needs only the following fields:

| Field | Type/shape | Meaning |
| --- | --- | --- |
| `observed_at` | timezone-aware timestamp | Time at which the probe made its authoritative work decision. Prefer a database default or a server-generated UTC value. |
| `work_detected` | boolean | The authoritative decision from `supabase/functions/schedule-probe/index.ts`. |
| `work_classes` | array of normalized strings | Normalized classes associated with the decision. This is an empty array under the current boolean-only contract. |

### Explicit exclusions

The telemetry record must not contain:

- secrets, credentials, authorization material, or environment values;
- raw request or response bodies;
- raw database rows or work-item payloads;
- exception messages, stack traces, headers, URLs containing credentials, or workflow environment dumps;
- user-provided content or identifiers unless a separate privacy and access-control review adds a justified field.

The writer should execute only after a successful authoritative decision. Its failure should be handled deliberately so that telemetry availability does not turn a no-work decision into a work decision or expose internal failure details to the caller.

## Administrative query path

No compatible existing administrative query path is identified by the schedule-probe invocation or implementation paths above. In particular, the scheduled workflow and Edge Function are execution paths, not an operator-facing query surface.

Do not assume or add an administrative UI as part of telemetry storage. A later administrative-query task should first identify an existing authenticated admin API or dashboard pattern and apply its authorization model; if none exists, that work requires an explicit product and security decision.
