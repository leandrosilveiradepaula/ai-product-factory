# AI Product Factory — six-domain certification evidence matrix
> **Ordem de execução após o merge #1117:** seguir o [Contrato de finalização](FINALIZATION_EXECUTION_CONTRACT.md). Esta matriz **não** autoriza uma nova rodada de PRs para cada célula; primeiro reutilizar provas atuais por SHA, fechar o Preview real do greenfield e testar somente lacunas bloqueantes. No observador de 26/10/2026 [#40382212270](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/40382212270), `product_ready=false` e seis domínios permanecem sem atestado independente no SHA `50c9814cf03aa00799b87619665eaa6df20c3d8f`.


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

## 26/10/2026 — Product Experience: false-positive success badge fix (candidate)

StatusPill previously used substring matching, incorrectly reporting green success for inactive, unhealthy and not_ready states. The proposed Console change explicitly enumerates success and failure/uncertain states, prevents caller tone override from masking failures, adds accessible labels for custom captions, and exercises actual transpiled TSX in unprivileged CI. This closes one reproducible UX defect only. It does **not** certify all mobile/a11y/keyboard/loading/error surfaces or establish full-product readiness. An exact-SHA Vercel Preview and browser receipt remain required before human production merge.

## 26/10/2026 — Console dependency critical security update (candidate)

During the first Console CI of the status-semantics candidate, production npm audit blocked `next@15.5.27` with a critical advisory. The Next.js maintainers' [October 14, 2026 security update](https://nextjs.org/blog/nextjs-security-update-october-14-2026) identifies patched Maintenance LTS `next@15.5.28` for two critical RCE issues and a high-severity Server Action DoS. The candidate updates the exact Next dependency and npm-generated lock graph (including @next compilers), retains the live `npm audit` gate without exceptions, and adds an offline version-floor regression. Version metadata came from an unprivileged GitHub Actions `npm install --package-lock-only --ignore-scripts`, not estimated hashes. The temporary metadata-extraction CI step is removed. Only a fully green final CI, typecheck, build and exact-SHA Preview/browser may authorize a future human merge; no production release is automatic.

## 26/10/2026 — Post-merge Console authenticated evidence incident

Factory #1109 post-merge main `d463a602...` passed native CI and deployed
Vercel production READY. Authenticated screenshot workflow #40327176953
was canceled by the GitHub 12-minute limit before provisioning any user:
`ubuntu-latest` used Ubuntu 26.04 and apt package mirror downloads for
Playwright `--with-deps` stalled. An earlier passing actual authenticated
run #39467414056 used Ubuntu 24.04 and the same pinned Playwright version.
A candidate pins the browser runner's OS, verifies its distribution, and
smoke-launches pinned Chromium offline **before** temporary operator creation.
This does **not** count as product-experience PASS. A new explicitly authorized
authenticated workflow run is needed after the human merge of the fix.

## 26/10/2026 — UX controlled migration feedback and audit integrity

Protected browser #40330808460 independently passed the exercised navigation/mobile/operator RBAC of the live Console; it did not perform the gate migration interaction. The Console candidate now correlates new migration-success audit records to the exact gate_id and independently verifies run, commit, name and exact SQL source integrity before success banners. Offline tests exercise the real compiled TSX and server reader with delayed completion, invalid audit, network failure and URL tampering. This narrows #692, but no production migration E2E or six-domain global product_ready assertion is claimed.

## 26/10/2026 — Authenticated accessibility evidence extension (candidate)

Protected production run #40336494210 verified Console navigation,
mobile/RBAC, artifact encryption and temporary-operator cleanup on the
published #1112 SHA. It did not verify every page's control naming and
keyboard focus sequence. A candidate extends the existing 14-page visual
capture to fail closed on unlabelled visible controls, missing image alt,
invalid landmarks/headings, duplicate IDs, positive tab-order overrides and
skip-link inaccessibility with real Tab/Enter. Numeric-only evidence is
unit-validated in unprivileged CI. This is actual browser-executable
verification after a separately authorized protected workflow dispatch;
it is not a new domain PASS or a whole-product readiness attestation.
