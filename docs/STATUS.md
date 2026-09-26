# Current status

Last reconciled: 2026-09-26.

## Operational foundation

The Factory now has a persistent Supabase Control Plane for projects, product specs, tasks, runs, decisions, human gates, evaluations, deployments, tool usage, Codex usage, and audit events.

The Factory Console reads live Control Plane state for projects, project backlog, runs, and gates. Console access is protected with Supabase Auth plus an RLS-protected operator allowlist. Privileged Control Plane operations use the service role only after operator authorization.

Human gates are durable. Routing can create a pending gate, and authorized operators can approve or reject it. Approval returns the task/run to the executable queue; rejection cancels it and records the decision/audit event.

## Autonomous runtime

Implemented runtime chain:

Idea / intake -> Discovery -> Specification -> Planning -> executable backlog -> routing -> claim -> GitHub Issue -> implementation producer -> branch -> commit -> PR -> CI -> merge/evidence.

The runtime includes:
- durable queue/claim operations;
- Direct vs Codex routing policy;
- model budgets and usage observability;
- structured product-stage execution;
- structured Direct implementation production;
- bounded CI auto-repair;
- durable GitHub delivery state and CI evaluation/audit evidence;
- preview deployment contracts plus fail-closed browser/e2e evidence and durable evaluation recording;
- deterministic cost ceilings before paid model providers;
- lease recovery, dead-letter visibility and operational incident health;
- provider-independent operational alert policy with cost relevance filtering so non-billable GitHub/Supabase events do not create false unknown-cost incidents;
- optional GitHub Issues alert adapter with deterministic per-code deduplication;
- explicit `runtime --mode alerts`, fail-closed unless GitHub alerting is intentionally enabled and configured;
- optional fail-closed Vercel preview adapter with explicit team/project/token configuration and no production target;
- side-effect-free readiness reporting for Vercel preview and GitHub Issues alerts; both remain disabled until explicit enable flags and complete configuration are present;
- modern Supabase server credentials (`SUPABASE_SECRET_KEY`) across the Console, Python runtime adapters, and GitHub Actions, with legacy service-role fallback;
- an hourly bounded autonomous runner for supported work;
- a bounded CI follow-up worker that resumes `ci_pending` Direct runs without model calls and moves green CI to `preview_ready`.

Scheduled Direct implementation remains disabled until a supported primary-model authentication path is operational. Manual Direct mode is wired but fail-closed before claim when auth is unavailable. CI follow-up is independent of model authentication and may run hourly.

## Console deployment

The Factory Console is deployed on Vercel at `https://ai-product-factory-console.vercel.app` and connected to the live Supabase Control Plane.

Verified production state:
- Supabase Auth login is operational;
- the bootstrap administrator exists as an active `admin` operator;
- server-side Supabase access prefers `SUPABASE_SECRET_KEY` with legacy service-role fallback only;
- the production health probe `GET /api/health` is public, returns HTTP 200, and exposes only service status plus a truncated deployment commit;
- production health was verified on Console commit `59e0352306128dd7a5beb6dd63ec112f864a0204`; later non-Console merges are intentionally ignored by Vercel.

## Authentication / model gate

OpenAI API authentication and Codex workspace authentication are intentionally separate.

The existing API key reached the OpenAI API but returned HTTP 429/quota, so the Factory does not use it for unattended paid work.

Codex Workload Identity Federation support has been prepared for GitHub OIDC. A manual preflight workflow exists. The managed ChatGPT workspace currently does not expose the Workload Identity configuration in the Admin Portal; an Enterprise support request has been opened to enable or provide access to Codex WIF before the preflight can be exercised.

Codex invocations performed by the Factory so far: 0.

## First pilot

Repository: `leandrosilveiradepaula/agente-sql-langgraph`.

The project is onboarded and tracked by the Factory. Existing semantic/product constraints remain authoritative. The 63-question benchmark is postponed and must not be started implicitly by the Factory.

## Production boundary

Production release currently requires a human gate. Destructive data changes, sensitive access expansion, paid-service creation, and material product requirement changes also require human authority regardless of environment.

## Next engineering blocks

1. Configure the external managed-workspace values required by `docs/AUTH_ACTIVATION_READINESS.md` and validate Codex WIF preflight.
2. Validate Primary model quota/billing once administratively ready; keep `FACTORY_PRIMARY_MODEL_ENABLED` false until then.
3. Supply runtime credentials/configuration for Vercel Preview and GitHub Issues alerts only when those adapters are intentionally activated; readiness is reported without side effects.
4. Connect the ready Vercel adapter to the verified preview flow only after its enable flag is explicitly set; do not promote to production automatically.
5. Decide whether to schedule `runtime --mode alerts`; the executable alert path exists but remains unscheduled and disabled by default.
