# AI Product Factory — six-domain certification evidence matrix

As of 26 October 2026, the Factory is **not globally product-ready**.
This inventory distinguishes a verified fact from an outstanding criterion;
it is not a substitute for the exact-SHA durable `product_readiness`
evaluation or a new workflow/paid test. Source of truth:
[`#713`](https://github.com/leandrosilveiradepaula/ai-product-factory/issues/713).

| Domain | Existing independent evidence | What remains unverified | Safe next action / gate |
| --- | --- | --- | --- |
| Security | #1104 fixes authenticated Console origin; #1105 production RPC uses service-role-only `SECURITY INVOKER`; negative CI tests | Cross-surface authorization, tenant boundaries, secret exposure and full SHA-exact security assessment | Execute offline/adversarial verification; authenticated operator provisioning requires explicit access authorization |
| Observability / Operations | Real candidate repin reconciliation `updated` at 2026-10-26T00:26:07Z with generation 13/version 12; recovery exercises from Prova 3 | Incident alerting, recovery and rollback coverage on current Factory SHA; credible failure visibility | Confirm scheduler/health/alerts and rollback in read-only evidence; no fake deployments |
| Test Strategy | CRM #197 native CI + Playwright on nonproduction integration; Factory #1105 `validate` and PG16 CI passed on candidate | All required critical Factory journeys, current-SHA authenticated coverage and negative contracts | Run bounded offline CI and targeted read-only E2E; exact-SHA receipt required |
| Product Experience | Source-level Console feedback and navigation tests exist; issue #692 remains open | Independently observed mobile/a11y/keyboard/loading/error/success across all critical surfaces | Offline static tests first; production temporary operator requires separate explicit permission |
| Documentation | `AGENTS.md`, `PROJECT_PLAN.md`, `docs/STATUS.md`, `docs/OPERATIONS.md` and runbooks exist; this block reconciles prior #1105 status | Independent current-SHA architecture/setup/incident/release/rollback review | Verify contracts and runbooks with realistic recovery scenarios |
| Functional Completeness | Prova 2 independently certified nonproduction in #40211815474; Prova 3 resilience scenarios passed | Generalizable greenfield end-to-end, selective Codex capacity and full product-level coverage; no production release attested | Use a legitimate authorized target; no synthetic throwaway project, no unsolicited paid calls |

## Non-negotiable certification rules

- Prior **Prova 1** completion is recorded in project history.
  **Prova 2** PASS is explicitly limited to nonproduction Preview integration.
  **Prova 3** PASS applies to exercised resilience scenarios, not every possible failure.
- `product_ready=true` requires a linked current-SHA durable independent
  assessment with all six required domains and verified coverage; tests,
  a green scheduler, Vercel status or documentation cannot set this flag.
- No automatic merge to production, public RLS, unapproved production
  migrations, paid model probes, 63-question SQL benchmark or replay of
  the completed CRM Change Set.
- Preview for this code-only Factory change is **N/A** by existing
  `apps/console/**` policy; no deployment should be manufactured.

## 26/10/2026 — Audited provider signal versus effective deployment

The official Vercel API returned `CANCELED` (ignored-build-step) for
`dpl_9sXYWPdP5Lbxobt7uiGh8rCqJA8k` at the #1107 merge SHA,
while GitHub commit status said `Vercel: success`. The commit contained
no Console files. This is a proven signal mismatch, not a Console
deployment failure or a domain PASS. The global observer now requires
exact first-parent changed paths to label `not_applicable`, and for actual
Console changes it reports GitHub success only as **unverified provider
signal**, never verified READY. Independent UX, deployment and operations
evidence remain pending. Global `product_ready=false`.
