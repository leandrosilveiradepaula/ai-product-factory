# Global product-readiness evidence after validated main CI

## Purpose and scope

An end-to-end **delivery** proves work was shipped; it does not prove all
features, mobile/accessibility, tenant boundaries or operational recovery.
The Control Plane release may legitimately say
`product_readiness={ready:false,status:not_assessed}`.

The `global-readiness-post-ci` job within the existing trusted
`.github/workflows/autonomous-runner.yml` is a strictly read-only,
model-free observer triggered by either successful `validate` on a **push to
main** or the completion (success **or failure**) of the **authenticated Console
visual evidence** workflow on that same main SHA. It is not run on PRs,
schedules, comments, dispatches, or unrelated workers. The first report after
CI can legitimately say `visual=pending`; the second observation after
browser completion reconciles the actual evidence rather than looping over
historical gaps. It uses the short-lived Control Plane OIDC credential
and same-repository GitHub read token. No Vercel deployment or Preview is
requested.

The observer reads (bounded, read-only):

- The exact current GitHub default-branch HEAD, commit/tree provenance and
  complete non-symlink file path inventory.
- The exact completed, successful **push** `validate` run and all check-runs
  bound to the same SHA. GitHub CI is evidence of executed checks, **not** a
  full-product readiness evaluation.
- The matching Control Plane project by repository identity, with no
  cross-repository token substitution.
- A durable `factory_evaluations` row with
  `eval_type=product_readiness` and `baseline_ref=<current SHA>`, whose
  associated run/task belongs to the same project. Both the durable evaluation
  status and the complete six-domain result must satisfy
  `release_intelligence._verified_product_assessment`. Existing projects
  additionally require an **independent**, same-SHA
  `existing_project_baseline` evaluation (inherited debt, repository,
  critical journeys).

If the trusted evaluation does not exist, the scan returns
`not_assessed`, `product_ready=false`, the source/CI inventory and **six
verification work proposals**, one per required product domain. These are
not implementation tasks, billable authorizations, human gates, claims, or
scheduler work. Their `start_authorized=false` and
`paid_calls_authorized=false` never change. A real authorized project
continuation may use them as *evidence gaps* only, after confirming current
requirements; it must not manufacture code tasks from missing audits.

## Interpreting a report

The artifact `factory-global-readiness-<github-run-id>` contains
`factory-global-product-readiness.json` with the immutable assessed SHA,
Control Plane project key, check evidence, inventory counts and six-domain
audit state. It is retained seven days. A non-zero observer run means sources
were missing, ambiguous or stale: `unverifiable_global_readiness_evidence`.
No HTTP errors, private source, token values or prompts appear in the output.

A full `passed` state is possible only when the independent Control Plane
evaluation on the **current HEAD** is already present, passed, complete and
linked to this project. This observer **does not write evaluations** or
generate this certification. Work remains until verified auth/RLS, security,
critical authenticated E2E, UX/mobile/a11y, runbooks, incidents/recovery,
and all functionality/domain coverage are actually attested. File paths,
a successful PR, specialist reviews on an older candidate, or a healthy
console do not substitute.

On a rapid succession of merges, an earlier observer deliberately fails
closed if main has moved. A later successful main CI triggers a fresh
observer automatically. No extra workflow dispatch, cron or model call is
required.

## Verification

Offline: `python -m unittest tests.test_global_readiness_evidence -v`.
For exact code gates use `.github/workflows/validate.yml` and
`factory-acceptance` on PR head. No `apps/console/**` changes means
Preview **N/A**; after human production merge the real
`workflow_run` plus artifact must be checked. A GitHub CI pass alone
does not prove that the OIDC live collector executed successfully.

No migration, public RLS grant, new run, model billing, or auto-merge.

## OIDC trust-boundary correction after #1002

The first post-merge observer attempted to use a new
`.github/workflows/global-product-readiness.yml` (#39460182317).
The code/CI succeeded, but the live observer was **blocked**: the
Control Plane edge broker trusts only allowlisted GitHub workflow
identities. Adding a new identity would expand privileged access and
is not justified for this purpose. The observer now runs inside the
already-trusted `autonomous-runner.yml` identity, with its own job
permissions `contents: read`, `actions: read`, `checks: read` and
`id-token: write`; it cannot write to GitHub or dispatch workers.

The existing runner listens for the *successful main push* `validate`
completion in addition to the previous Control Plane OIDC backup event.
The scheduler probe accepts a `workflow_run` only when its upstream
event is `schedule`, so a successful push validation is **not** a wake.
All worker, CI, Preview, release and paid-model lanes remain skipped.
No OIDC allowlist, Supabase RLS, broker or secret configuration is changed.

The observer now verifies the actual `validate` run jobs `test` and
`factory-acceptance` at the same SHA, separate from unrelated or
still-running check-runs. Unexpected failures produce a fixed
`reason_code` and `error_class` only, with no error messages or tokens.
A CI pass before the merge does **not** prove that the new OIDC job worked;
check the exact post-merge job and JSON receipt.

## Live post-visual reconciliation (20/10/2026)

A successful `validate` push and the `Authenticated Console visual evidence`
push run happen concurrently, so the early global receipt could not
possibly prove the later browser job. The trusted `autonomous-runner.yml`
now accepts a second **workflow_run** observation signal from the already
existing visual workflow, **without adding a scheduler wake**, service-role
credential, OIDC allowlist entry or new workflow identity. It runs only the
standalone `global-readiness-post-ci` job. The existing `schedule-probe`
accepts an upstream `workflow_run` only for `event=schedule`; all
workers remain skipped.

On visual completion (success or failure), the observer validates:
1. GitHub main HEAD at the exact visual SHA; no late historical audits.
2. The one successful `validate` push workflow for that SHA, with actual
   `test` and `factory-acceptance` jobs. The visual run is never accepted as CI.
3. The trusted `.github/workflows/authenticated-visual-evidence.yml`
   `push` run (run_attempt=1) and its `capture` job; a successful run
   must also have a nonempty unexpired encrypted artifact, owned by the
   same run, SHA and main branch. No secret, artifact body or encryption
   key is read.
4. The `Vercel` commit status at exactly the audited SHA, tagged strictly
   `provider_reported_ready`, not as independent proof of live health.

These results appear as `current_sha_operational_evidence` within the
seven-day read-only JSON receipt. Observed facts improve the specificity
of the six-domain handoff: known CI and visual/a11y testing are not
requested again as if no check had run; remaining independent security,
cross-project critical E2E, recovery/rollback and product UX coverage
still require attestation.

`product_ready` **does not become true from these signals**. An exact-SHA
durable six-domain evaluation remains mandatory, and a conflicting same-SHA
visual failure or provider failure overrides even a previously recorded pass.
No evaluation row, task, scheduler claim, model call, merge or migration is
written by this observer.

Test with `python -m unittest tests.test_global_readiness_evidence
tests.test_oidc_backup_scheduler_wake -v`. After merge, inspect **two**
distinct OIDC observer runs: the CI-completion receipt and the visual-
completion receipt. No fresh paid E2E may be created for this verification;
the next Console change naturally exercises the path.

## 21/10/2026 — Inventário CI por push (reconciliacao da PR #1013)

O runner global pode observar muitos `issue_comment`, `schedule`, `workflow_run` e runs skipped no mesmo SHA de `main`. O endpoint GitHub `head_sha` **sem filtro por evento** soma esses workflows estranhos ao CI, e o limite fechado de 100 pode impedir a observacao de `validate` e visual mesmo quando seus recibos sao validos. Nao se deve contornar o limite, nem presumir `product_ready` por um unico `validate` verde.

A selecao agora usa `head_sha=<sha>&event=push&per_page=100` e rejeita entradas que nao sejam push, nao tenham SHA exato/repo/ID, estejam incompletas ou excedam 100 verdadeiros push runs. O `validate.yml` e verificado pelo path do workflow e o run individual, e nao so pelo nome. O fluxo visual independente continua exigindo seus proprios checks, browser evidence, SHA e proveniencia. Nao altera jobs, gatilhos, billing, RLS nem grants. Testes cobrem 302 `issue_comment`, spoof, dados parciais e overflow real.

A correcao nao certifica automaticamente os seis dominios do produto. O observer no merge #1020 (SHA `de754d14063a38e11060ffbc6ca5dee80c140069`) continuava reportando `product_ready=false`. As migrations `20261021014000` e `20261021021000` permanecem pendentes de autorizacao especifica de producao.

## 26/10/2026 — Trust boundary of Vercel provider evidence

The global observer can read GitHub commit statuses from the same Factory SHA.
But a status with context `Vercel` is not proof of the owned deployment: an
unrelated Vercel project can report a successful status or a matching health
payload. A successful provider status is now accepted as an **observed,
provider-only** operational signal only when its HTTPS `target_url` matches
the exact tenant/project path
`vercel.com/leandros-projects-102e32ab/ai-product-factory-console/<deployment-id>`
with an ASCII 20–40 character alphanumeric deployment ID. Other teams,
projects, origins, ports, credentials, fragments, queries and malformed paths
fail closed. The policy is the Python counterpart to
`scripts/console_visual_origin.mjs`; the offline regression checks their
shared constants and negative spoofed statuses.

An independently recorded product readiness pass is also downgraded to
`not_ready` while that same-SHA owned Vercel status is `pending` or failed.
Missing Vercel status remains explicitly `not_reported` (Preview can be N/A
for non-Console changes); this never creates a passing domain assessment.
Neither a provider status nor an encrypted browser artifact verifies all UX,
security, functional or operational requirements.

Regression: `python -m unittest tests.test_global_readiness_evidence -v`.
The candidate changes no `apps/console/**` file and requests no Vercel
deployment, credentials, migration, model calls or extra scheduler wake.
Production merge remains human-gated. Six-domain global `product_ready`
remains false without a fresh, linked, independently executed assessment.

## 26/10/2026 — Exact commit diff proves Console Preview applicability

After human merge #1107 at `c44f060939e21eb56e410cf137248f652202e02d`,
the read-only observer passed on Actions #40261727445 with six domains still
unverified. The Vercel GitHub commit status said `success` but the project-owned
deployment `dpl_9sXYWPdP5Lbxobt7uiGh8rCqJA8k` was `CANCELED`
(`ignored-build-step`) because no `apps/console/**` file changed.
Consequently even a project-owned GitHub `success` status cannot certify a
READY deployment.

The observer now reads GitHub's exact commit file delta bound to the same
SHA and first-parent identity, rejects missing/duplicate/unsafe paths and
paginates GitHub's 100-file REST pages through a 30-page fail-closed boundary, and checks both sides of renames.
On non-Console commits provider status is `not_applicable` (Preview N/A).
On Console commits GitHub status `success` remains only
`provider_status_success_unverified`. A relevant `pending` or `failed`
status still blocks conflicting old same-SHA readiness; neither `success`
nor N/A can manufacture the six-domain durable evaluation.

The added check runs strictly in the existing trusted observer with the
already configured GitHub read identity. No Vercel token/privileged browser,
new broker identity, paid model or production writes are introduced.
