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
- provider-independent operational alert policy;
- an hourly bounded autonomous runner for supported work.

Scheduled Direct implementation remains disabled until a supported primary-model authentication path is operational. Manual Direct mode is wired but fail-closed before claim when auth is unavailable.

## Authentication / model gate

OpenAI API authentication and Codex workspace authentication are intentionally separate.

The existing API key reached the OpenAI API but returned HTTP 429/quota, so the Factory does not use it for unattended paid work.

Codex Workload Identity Federation support has been prepared for GitHub OIDC. A manual preflight workflow exists, but the managed ChatGPT workspace still needs the Codex WIF rule/provider configuration before it can be exercised.

Codex invocations performed by the Factory so far: 0.

## First pilot

Repository: `leandrosilveiradepaula/agente-sql-langgraph`.

The project is onboarded and tracked by the Factory. Existing semantic/product constraints remain authoritative. The 63-question benchmark is postponed and must not be started implicitly by the Factory.

## Production boundary

Production release currently requires a human gate. Destructive data changes, sensitive access expansion, paid-service creation, and material product requirement changes also require human authority regardless of environment.

## Next engineering blocks

1. Configure the external managed-workspace values required by `docs/AUTH_ACTIVATION_READINESS.md` and validate Codex WIF preflight.
2. Validate Primary model quota/billing once administratively ready; keep `FACTORY_PRIMARY_MODEL_ENABLED` false until then.
3. Enable execution adapters only after their independent readiness gates pass.
4. Attach a real preview deployment/browser adapter only when its external provider is selected and authorized; the verified preview orchestration and evidence boundary are implemented.
5. Attach an external notification adapter (for example Slack/email) only when a notification destination is explicitly selected; alert generation is implemented without external side effects.
