# Operations Runbook

This runbook describes the safe operating modes of the AI Product Factory runtime. It intentionally contains no secret values.

## Runtime modes

| Mode | Purpose | External side effects | Default scheduling | Main gate |
| --- | --- | --- | --- | --- |
| `health` | Report configuration/readiness only | None | Hourly runner | None |
| `github-preflight` | Verify per-project GitHub capabilities with safe read probes | GitHub reads + Control Plane readiness evidence | Hourly when stale/blocked + manual | No synthetic write probes; missing capability stays fail-closed |
| `recovery` | Requeue expired leases or fail exhausted runs | Control Plane writes | Hourly runner | Bounded attempts |
| `product` | Execute one product-stage run | Model call + Control Plane writes | Hourly only when ready | Primary enable + auth + budget |
| `dispatch` | Route one planned task | Control Plane writes | Hourly bounded + manual | Optional project key |
| `direct` | Produce implementation and open PR | Model + GitHub writes | Hourly only after explicit Primary+budget activation; manual supported | Primary enable + auth + ledger budget + risk gate |
| `codex` | Execute one already-routed complex implementation through isolated Codex CLI and open PR | Codex workspace + GitHub writes | Hourly/manual only when explicitly enabled and auth-ready | Codex enable + complete WIF or official `CODEX_ACCESS_TOKEN` + repository-scoped GitHub credential + Control Plane; cross-repo additionally requires `FACTORY_GITHUB_TOKEN` |
| `ci` | Resume one `ci_pending` run | GitHub reads + evidence writes | Hourly | Matching durable PR evidence |
| `preview` | Deploy and verify one `preview_ready` run | Vercel Preview + browser/e2e + evidence writes | Hourly bounded + manual | Preview applicability/readiness + quality evidence |
| `release` | Observe one human PR merge | GitHub reads; issue close/evidence after merge | Hourly | Human merge must already exist |
| `alerts` | Evaluate operational alerts and publish deduplicated GitHub Issues | GitHub issue writes | Hourly bounded + manual | Backend GitHub issue permission |
| `retry` | Create one fresh auditable run from a terminal failed run | Control Plane writes only | Manual | Source run must be `failed`; original run is immutable; explicit retry reason required |

## Merge autonomy

The ChatGPT/operator layer may merge a PR directly after its applicable CI/quality gates are green **only when that merge cannot publish production**. It must use the verified head SHA and fail closed if the PR moved, became non-mergeable, or a human gate condition appeared.

This does not grant merge capability to the Factory runtime, does not enable GitHub auto-merge, and does not change the production boundary. Any PR whose merge publishes production remains a human action.

Production operators may execute that human action from the authenticated Factory Console when the dedicated Console release path is activated. The Console path is intentionally separate from the Python runtime and GitHub adapter. It requires an admin session, `VERCEL_ENV=production`, `FACTORY_RELEASE_GITHUB_TOKEN`, and an explicit source-controlled repository allowlist in `config/factory.release-policy.v1.json`. The token stays server-side and is never exposed to browser code, workers, agents or generated repositories.

## Per-project GitHub capability preflight

Every repository-backed project has a durable GitHub access record. The scheduler may run `github-preflight` before dispatch, using the repository-aware runtime credential.

The preflight:
- performs only safe GET requests;
- verifies repository metadata, contents, Issues, Pull Requests, Actions and Commit Statuses;
- treats Checks as optional when Actions + Commit Statuses provide equivalent CI evidence;
- never creates a fake branch, commit, issue or PR merely to test write access;
- preserves cross-repository write capabilities as unverified until they are backed by an explicitly approved credential;
- blocks Direct/Codex cross-repository writes unless `contents_write`, `issues_write` and `pull_requests_write` are durably verified;
- stores only non-secret readiness metadata in the Control Plane.

The Console shows this contract on each project. An admin can mark the record stale with **Verificar novamente**; the autonomous runner then re-runs the safe preflight. **Corrigir acesso no GitHub** remains an external consent step in Phase 1. The target architecture is a Factory-owned GitHub App with short-lived installation tokens; PAT expansion must never happen silently.

## Factory-owned GitHub App onboarding

The Console contains an inert-by-default GitHub App onboarding path. Registration and installation remain explicit human GitHub actions.

Registration uses GitHub's App Manifest flow from an authenticated Factory admin session. The temporary manifest code is exchanged server-side. The returned PEM, client secret and webhook secret are written directly to Supabase Vault; only non-secret App metadata is stored in the public Factory schema. These values are never rendered to the browser.

For a project, **Verificar GitHub App neste projeto**:
- authenticates as the registered App with a short-lived App JWT;
- asks GitHub for the installation associated with the exact `owner/repo`;
- mints a one-hour installation token constrained to that repository and to the source-controlled delivery permission set;
- verifies repository/contents/issues/pulls/actions/status/check evidence;
- infers write readiness from the granted installation permissions without performing synthetic write mutations;
- persists only `installation_id`, `repository_id`, capability evidence and `auth_mode=github_app`; the installation token is never persisted.

The source-controlled App permission set is limited to Actions read, Checks read, Contents write, Issues write, Pull Requests write and Commit Statuses read. Installing the App or changing repository access is a human GitHub consent action. Until an installation verifies successfully, the existing fine-grained PAT path remains an explicit fallback and cross-repository write stages stay fail-closed.

This phase does not yet switch the autonomous Python runtime to GitHub App tokens. Runtime replacement of `FACTORY_GITHUB_TOKEN` is a separate Phase 3 change after a real App installation is verified.

## Preview policy during existing-project onboarding

Imported projects must have an explicit Preview policy before Preview execution. The GitHub capability preflight may persist the safe positive case automatically when read-only GitHub evidence proves an existing Vercel integration on the repository default branch.

Automatic onboarding is deliberately narrow:

- a Vercel commit status with a `vercel.com` target or a check-run owned by the Vercel GitHub App is accepted as integration evidence;
- the persisted policy is only `{"provider":"vercel","mode":"github","required":true}`;
- an existing explicit `manifest.preview` policy is never overwritten;
- absence of Vercel evidence never becomes `required=false`;
- no Vercel team/project identifiers are invented;
- the evidence stores only normalized signal metadata, not raw GitHub payloads;
- the persistence RPC is service-role only and audited as `project.preview_policy.verified`.

If no explicit policy or verified integration exists, Preview remains fail-closed and the Console shows the policy as pending. Re-run the GitHub project preflight after correcting repository access or integration.

## Cross-repo Vercel Preview evidence

For `preview.mode=github`, generic CI evidence can remain valid with Actions + Commit Statuses when the fine-grained token cannot read Checks. Preview URL discovery has a stricter requirement: the Factory needs either a successful Vercel check-run that exposes a `.vercel.app` URL or a successful Vercel commit status plus a Vercel bot comment that exposes a **Ready** preview URL.

`checks_read` is therefore recorded separately as an optional GitHub capability. Missing Checks read does not block generic CI, but it can block Preview discovery when the Vercel bot comment is stale or does not contain a Ready URL. In that case the worker fails closed with an actionable error instead of reporting a generic timeout. The default GitHub path still does not require a Vercel API token.

## Cross-repo CI evidence with fine-grained tokens

For repositories outside the Factory repository, the runtime must not assume that the GitHub Checks API is available to a fine-grained personal access token. The preferred evidence order is:

1. use check-runs when the credential can read them;
2. on HTTP 403 from check-runs, fall back to GitHub Actions workflow runs plus Commit Statuses for the exact candidate SHA;
3. require at least one workflow run for the candidate SHA before treating CI as successful;
4. treat workflow failure or failing/error commit status as CI failure;
5. treat running workflows, non-terminal statuses, missing workflow evidence, or missing fallback capability as pending/blocked rather than success.

The fine-grained fallback requires repository permissions that expose Actions read and Commit statuses read. Do not widen a token to classic `repo` merely to recover the Checks API. Project onboarding/readiness should verify the capabilities actually available to the selected credential.

## Console release credential preflight

The production Console uses `FACTORY_RELEASE_GITHUB_TOKEN` only for the explicit human merge path. Before rendering **Fazer merge em produção**, the Console performs a safe GET of the exact pull request using that dedicated credential.

- HTTP 404 is treated as the credential not seeing the repository or PR.
- HTTP 403 is treated as insufficient read permission.
- HTTP 401 is treated as a rejected/invalid credential.
- No mutation is performed by this preflight.
- The actual merge still happens only after the human confirmation click.
- For a fine-grained PAT, GitHub's merge endpoint requires repository `Contents: write`; reading the PR also requires the token to include the target repository and appropriate pull-request read access.
- The release credential remains separate from runtime delivery credentials and is never exposed to generated code, agents, or the browser.

## Required release sequence

1. Implementation opens a PR; production is not touched.
2. CI follow-up verifies the PR head matches the durable candidate commit.
3. Green CI persists explicit `quality_gate` evidence.
4. Preview applicability is evaluated from explicit project policy and the PR changed files. Missing policy fails closed to Preview required. `required=false` or a non-matching `required_paths` policy records durable `preview_not_required` evidence instead of fabricating a deployment.
5. When Preview is required, it requires the same candidate commit, successful quality evidence, Preview deployment, and successful browser/e2e evidence for the exact Preview URL.
6. The run moves to `awaiting_release`.
7. A human reviews and merges the PR. The action may be performed in GitHub or by an admin clicking `Fazer merge em produção` in the production Console. The Console revalidates the exact candidate SHA and PR state before calling GitHub.
8. The release observer sees the already-merged PR, records/reconciles the merge SHA and audit evidence, marks the run `merged`, and closes the linked issue.

## Console human release action

The optional Console release action is an operator control, not a runtime capability.

Activation requirements:
- production Console only (`VERCEL_ENV=production`);
- authenticated active Console operator with role `admin`;
- dedicated `FACTORY_RELEASE_GITHUB_TOKEN` stored only in the production server environment;
- explicit `operator_allowed_repositories` allowlist in `config/factory.release-policy.v1.json`;
- source-controlled merge method from `config/factory.release-policy.v1.json`.

Before the irreversible GitHub merge request, the Console must confirm:
- the Control Plane release report is exactly `ready_for_human_release`;
- the run is `awaiting_release`;
- the project repository is valid and allowlisted;
- the PR number comes from the durable release report;
- the PR is open, non-draft, targets `main`, and is not from a fork;
- GitHub reports the PR mergeable;
- PR head SHA exactly equals the durable candidate commit and the SHA submitted by the rendered form.

The Console records a durable pre-merge audit event before invoking GitHub. Success/failure evidence is also recorded when possible. A successful Console merge can mark the release report released immediately; the ordinary release observer remains responsible for idempotently reconciling the run/task/issue lifecycle.

Missing token, non-production environment, non-admin operator, repository outside the source-controlled allowlist, stale SHA, draft/closed/non-mergeable PR, or any Control Plane mismatch fails closed.

## Console human migration action

Production database migrations may be applied from the authenticated Factory Console only as an explicit human action on a pending durable gate whose metadata declares `requested_action=apply_control_plane_migration`.

Activation requirements:
- production Console only;
- active Console admin;
- dedicated `FACTORY_SUPABASE_MANAGEMENT_TOKEN` stored only in the Vercel production server environment;
- existing `FACTORY_RELEASE_GITHUB_TOKEN` for read/revalidation of the exact PR and migration file;
- project/repository/ref allowlist in `config/factory.supabase-migration-policy.v1.json`.

Before applying, the Console revalidates pending gate/run/task state, exact candidate SHA, the source PR identity, required green checks, the strict `supabase/migrations/<timestamp>_<name>.sql` path, migration name/file consistency, bounded file size, and the source-controlled Supabase project ref. An open PR must be non-draft. If the source PR was already merged before the migration gate was clicked, recovery is allowed only when GitHub proves a real merge, the PR still targets `main` in the same repository, the head is not a fork, and the durable candidate SHA is still exactly the PR head SHA. A closed unmerged PR remains blocked. SQL is fetched from GitHub at the exact candidate SHA; the browser cannot submit arbitrary SQL.

The Console uses the Supabase Management API migrations endpoint. It lists migration history first for idempotency, applies only when absent, verifies the migration appears afterward, records requested/succeeded/failed audit events, and resolves the human gate only after success. If the account does not expose the official migrations endpoint, the action fails closed; do not fall back to a generic SQL endpoint.

The Management token is never exposed to browser code, Python runtime workers, agents or generated repositories. There is no scheduled/automatic migration apply path.

## Primary model activation

`product` and `direct` are fail-closed inside the Python runtime itself. They require all of:

- `FACTORY_PRIMARY_MODEL_ENABLED=true`;
- a supported primary authentication path: API key or API workload identity;
- configured model budget;
- configured per-run reservation;
- known spend not already exhausting the configured budget.

Do not enable the primary model merely because an API key or API WIF mapping exists. Billing/quota readiness and a bounded smoke test are separate prerequisites. Scheduled Direct additionally requires non-empty budget and reservation variables; the runtime reads current known spend from the Control Plane ledger and blocks if paid usage has unknown cost.

## Verified Preview activation

The project supplies non-secret deployment metadata in `factory_projects.manifest.preview`. `mode: github` discovers the exact Vercel Preview from GitHub check-runs using `GITHUB_TOKEN`; `mode: api` creates/polls the Preview through the Vercel API and requires Vercel team/project metadata.

For the standard manual GitHub Actions path, the job itself provides the activation flags, uses the native `GITHUB_TOKEN`, installs pinned Playwright/Chromium, and invokes `scripts/verify_preview.mjs`. No external browser service or Vercel token is required when the project uses `mode: github`.

When Vercel Authentication protects Preview deployments, configure **Project Settings -> Deployment Protection -> Trusted Sources** with GitHub Actions scoped to the Factory repository, trusted branch (`main`) and `Preview` environment. Keep the default GitHub OIDC audience unless the workflow explicitly calls `getIDToken()` with a custom audience. The browser job requires `id-token: write`, mints a short-lived token with `core.getIDToken()`, masks it, and sends it only as the `x-vercel-trusted-oidc-idp-token` request header. A successful check must end on the Factory Preview, not on `vercel.com/login`.

For alternative runtimes or `mode: api`, configuration remains explicit: `FACTORY_VERCEL_PREVIEW_ENABLED=true`, provider credentials (`GITHUB_TOKEN` or `VERCEL_TOKEN`), `FACTORY_BROWSER_EVIDENCE_ENABLED=true`, a reviewed `FACTORY_BROWSER_EVIDENCE_COMMAND_JSON`, and an optional bounded timeout.

The Vercel adapters refuse non-Preview environments. The browser adapter receives the exact deployed URL through `FACTORY_PREVIEW_URL` and must return structured JSON evidence. The built-in Playwright verifier checks page load, HTTP status, visible non-empty body, and browser console/page errors.

## Multi-agent team planning

The engineering plan is semantic input, not the scheduler itself. Planning tasks must provide a stable `task_key`, `required_capabilities`, repository `scope_keys`, dependencies by task key, and an optional preferred specialist role only when materially required.

After planning, the deterministic Execution Team Planner reads the live Agent Registry and produces a versioned team plan. It selects the minimum capability-covering/least-privileged specialists, calculates planned workers and dependency/scope-aware waves, records exclusions and blockers, and persists the decision in the Control Plane. It makes no extra paid model call.

Agent `max_concurrency` is a ceiling, never a target. Work may share a wave only when dependencies are satisfied, agent capacity is available and write scopes do not overlap. Parent/child scopes conflict.

A task must have one safe owner. Do not solve a cross-specialist task by granting a read-only reviewer write permission. Instead split implementation, security review, QA/eval or operations verification into independent work units/lanes. Until dedicated read-only specialist lanes exist, policy-required reviewer participation is recorded as advisory and fails closed rather than entering the generic Direct/Codex write worker.

The target integration model is one Change Set per objective: parallel work units use isolated branches/workspaces and converge in dependency order into one controlled integration candidate. Security/QA then evaluate the candidate that will actually ship. Production still stops at the human merge gate.

See `docs/MULTI_AGENT_ARCHITECTURE.md` for selection rules, context packets, adaptive concurrency, metrics and the implementation roadmap.

## Project Brain and Impact Engine

After Planning, the runtime builds a deterministic Project Brain snapshot from the engineering plan and any durable reconciliation snapshot already present in context. No additional model call is made.

The Brain stores versioned nodes/edges with provenance for project, tasks, repository scopes, capabilities, components and observed sources/evidence. Direct public access remains denied by RLS; server-side service access is required.

Before a Change Set builder generates code, the Impact Engine resolves the work-unit task key, loads the current Brain snapshot and traverses relevant dependency/scope/capability relations. The resulting impact packet contains confidence, seed nodes, impacted nodes and explicit unknowns. It is persisted and then passed as factual context to Direct/Codex. Missing knowledge is recorded as unknown rather than invented.

## Change Sets

A ready Execution Team Plan materializes one Change Set. Only builder tasks become work units; Security, QA and Operations remain independent review lanes.

The first builder observes the repository `main` SHA and binds it as the immutable Change Set source. Every work unit in the current wave receives the current integrated candidate as its exact base. Work-unit branches do not create release pull requests.

When all work units in a wave are complete, the Change Set integrator:

1. verifies every work unit was based on the current candidate;
2. rejects duplicate changed-file ownership across the wave;
3. reads exact file contents from each output commit;
4. commits the combined files once to the integration branch;
5. advances to the next wave, or creates one final PR after the last wave.

The final PR head SHA must equal the durable Change Set candidate. The existing CI, specialist review, Preview and human release pipeline then takes over. Integrator retries are bounded; exhausted builder/integration retries block the Change Set.

## Specialist review lanes

After green CI, `factory_enqueue_specialist_lanes` reads the latest ready Execution Team Plan and creates only required Security, QA and Operations jobs for the exact candidate SHA.

Lifecycle:

1. CI persists quality-gate evidence.
2. Required specialist jobs are queued and the run becomes `specialist_review_pending`.
3. Each read-only worker claims at most one durable job with a bounded lease.
4. Candidate SHA is revalidated before evaluation.
5. Findings and evidence are persisted.
6. Any failed or blocked required lane sets `specialist_review_failed`.
7. When all required lanes pass, the run becomes `preview_ready`.

Expired leases are requeued only below the retry ceiling; exhausted retries become `specialist_retry_exhausted` blockers. This version is deterministic-first and does not call a paid model merely to perform review.

## Adaptive concurrency

The Agent Registry `max_concurrency` is a hard ceiling, not a desired worker count. Before exposing a Direct/Codex matrix to GitHub Actions, the adaptive controller computes an effective concurrency per agent.

V1 inputs are runnable assigned work, latest provider quota pressure, unknown paid cost, recent repair rate, first-pass CI yield and CI queue age. Unknown paid cost or critical/blocked quota yields zero workers. Attention/unknown quota and poor quality/queue signals reduce concurrency conservatively.

Each decision is stored in `factory_agent_concurrency_decisions` with the pressure snapshot and human-readable reasons. The controller does not mutate Agent Registry ceilings and makes no model call.

## Requirement traceability and Definition of Done

After planning is persisted, the runtime derives stable requirement keys from each task's acceptance criteria, links them to materialized tasks, and records a versioned Definition of Done.

Evidence is factual:
- `github_ci` comes from exact-candidate CI;
- `security`, `qa` and `operations` come from independent specialist lanes;
- `preview` and `browser_evidence` come from verified Preview;
- `human_release` is recorded only when the release observer sees a human merge.

Readiness contains explicit satisfied/missing checks; there is no release score. Checks without an implemented evidence provider remain missing rather than being guessed as passed.

## Policy-as-Code and Release Intelligence

The release policy is source-controlled in `config/factory.release-policy.v1.json`. It explicitly forbids automatic merge and requires human production release.

After Preview evidence (or explicit Preview non-applicability), the runtime builds a factual release assessment from current DoD readiness, requirements/evidence, specialist evaluations, changed files, task risk, paid-cost health and rollback evidence. Missing non-human DoD checks, unknown paid cost, or an unverified migration rollback blocks transition to `awaiting_release` and persists `release_policy_blocked`.

A successful automatic decision is only `ready_for_human_release`. The release observer marks the report `released` only after GitHub shows a human merge.

## Codex

Codex is a selective executor, not the orchestrator. Scheduled Direct remains disabled until the independent primary-model readiness gate is proven. Codex workspace WIF requires the real managed-workspace federation rule and audience; never invent them.

The Codex worker is independently gated by `FACTORY_CODEX_ENABLED=true`, one complete official Codex auth path (WIF or `CODEX_ACCESS_TOKEN`), the repository-scoped native `GITHUB_TOKEN`, and Control Plane credentials. WIF has precedence; any partial WIF configuration blocks token fallback. The GitHub Actions token-minting layer also requires `OPENAI_WIF_AUDIENCE` to request the external OIDC assertion. Same-repository work may use the native Actions token; cross-repository work still fails closed unless `FACTORY_GITHUB_TOKEN` is configured. The scheduled/manual Actions job checks readiness before checkout, OIDC minting, Node/Codex installation, or queue claim.

A Codex run is claimed only when `execution_route=codex`. Claiming uses a lease and bounded recovery. Repository code is cloned to a temporary checkout with the GitHub credential held by the parent process; the remote is removed before Codex starts, and GitHub/API credentials are not passed to the Codex subprocess. Codex runs with `workspace-write` and non-interactive approvals, never `danger-full-access`. Output is limited by file count and total bytes, rejects deletions, symlinks, non-UTF-8 files, path traversal, and secret-bearing paths, then enters the same Issue -> branch -> commit -> PR -> CI -> Preview -> `awaiting_release` loop as Direct.

The durable `factory_codex_usage` policy row is created at dispatch with zero invocations. The worker increments it only immediately before a real Codex CLI invocation. Do not fabricate token/cost data when the CLI does not report it. The Agent SQL 63-question benchmark remains explicitly excluded from implicit Codex work.

## Manual Codex fallback

Codex remains a selective executor. When `FACTORY_CODEX_ENABLED` is not true, the scheduled `codex-manual` job may handle Codex-routed work without any OpenAI credential.

The flow is:

1. claim one `execution_route=codex` run as `preparing_codex_manual`;
2. create or reuse a GitHub Issue with the exact marker `Factory run: <run_id>`;
3. persist the Issue binding and move the run to `awaiting_codex_manual`;
4. an operator opens Codex using the managed ChatGPT Business account and asks it to implement that Issue;
5. the Codex-created PR must target `main` and include the exact run marker in its body;
6. the follow-up worker discovers that PR, persists its head SHA/branch as candidate evidence and moves the run to `ci_pending`;
7. normal CI, Preview and human production release semantics resume.

The manual handoff never stores ChatGPT cookies, browser sessions, human tokens, `OPENAI_API_KEY` or `CODEX_ACCESS_TOKEN`. It does not increment the automated Codex invocation ledger because the invocation occurred outside the Factory. Lease recovery covers interrupted `preparing_codex_manual` claims.

Setting `FACTORY_CODEX_MANUAL_FALLBACK_ENABLED=false` disables new manual handoffs. Existing `awaiting_codex_manual` runs may still be followed up. Once `FACTORY_CODEX_ENABLED=true` is safely activated, new queued Codex work is left to the automatic worker and the manual prepare step stops claiming work.

## Failed-run retry

Use `runtime --mode retry --source-run-id <uuid> --retry-reason "<reason>"` only after the root cause of a terminal failed run is understood and fixed.

The retry path is model-free. The Control Plane RPC locks and validates the source run, refuses non-failed sources and duplicate retry-of the same source, creates a fresh queued run on the same task/source commit, strips transient worker/error metadata, persists `retry_of` / `retry_reason`, and records `run.retry_queued` audit evidence. The original failed run is never rewritten.

Creating a retry does not bypass routing, model budget, unknown-cost checks, CI, specialist review, Preview policy or the human production-release gate. Do not use administrative SQL to recycle the original run now that the native retry path exists.

Operational `failed_runs` alerts count only actionable failures: the run is `failed` and the task's current status is also `failed`. Historical failed runs remain queryable for audit but no longer keep an incident open after the task has recovered, integrated, completed or been explicitly blocked.

## Operational alerts

The scheduled alerts job explicitly enables the GitHub Issues sink for that job only. Alert issues are deduplicated by deterministic code. Non-billable GitHub/Supabase usage without cost data must not be treated as unknown paid spend.

The GitHub Issues sink reconciles active and resolved conditions on every alerts cycle. Active codes remain open/deduplicated by their deterministic `<!-- factory-alert:<code> -->` marker. A known code that is no longer active is closed automatically only when an open issue contains that exact marker. Unknown markers, pull requests and ordinary issues are never closed by alert reconciliation.

## Supabase credentials

Server-side code prefers `SUPABASE_SECRET_KEY` (`sb_secret_...`) and keeps `SUPABASE_SERVICE_ROLE_KEY` only as legacy fallback. Modern secret keys are sent as `apikey` only; they are not JWT bearer tokens.

Factory tables intentionally use RLS with no public client policies. Privileged worker/Console operations use backend credentials only.

## Incident handling

- Expired worker lease: recovery may requeue within the bounded attempt limit.
- Exhausted attempts: terminal failure/dead-letter visibility; do not infinite-retry.
- CI failure: return to bounded correction/repair, never merge.
- Browser/e2e failure: persist failure evidence and stop before release.
- Candidate SHA mismatch at CI/Preview/Release: fail closed; do not reinterpret the run.
- Unknown paid cost or exhausted budget: block paid execution.
- Missing external credentials: report blocked readiness; do not fabricate values.

## Production safety invariants

- Production release is always human-gated.
- The release-followup worker has no code-write or PR-merge permission.
- Preview cannot target production.
- Direct is manual-only while primary authentication remains externally blocked.
- The 63-question Agent SQL benchmark is not an implicit Factory task.

## Health checks

Factory Console production health:

`GET https://ai-product-factory-console.vercel.app/api/health`

The response is intentionally minimal and contains only service status and a truncated deployed commit.

## Vercel deployment budget policy

The Console must not create a deployment for every implementation commit.

Active policy:
- `main` remains the production branch;
- implementation branches such as `console/**`, `test/**`, `ci/**` and `security/**` do not deploy automatically;
- after `Console validation` completes successfully for a PR that actually changes `apps/console/**`, the trusted default-branch promotion workflow automatically revalidates the exact PR head plus `test`, `factory-acceptance` and `validate` before moving `preview/pr-<n>` to that SHA; manual `workflow_dispatch` remains an explicit fallback;
- only `preview/**` is allowed to create the final Preview candidate;
- if `preview/pr-<n>` already points to the exact candidate SHA, the workflow reuses it before any budget check and does not request another deployment;
- Preview promotion does not require a Vercel token: when provider usage credentials are absent, GitHub Actions enforces a hard local budget of five successful promotion-workflow runs per rolling 24 hours, counting both automatic and manual triggers conservatively;
- when read-only `VERCEL_TOKEN` and `FACTORY_VERCEL_TEAM_ID` are configured, the same guard prefers the shared Vercel rolling-24h deployment count and applies the 70/85/95% thresholds;
- a Vercel API read failure falls back to the bounded GitHub budget instead of blocking all development or bypassing protection;
- the workflow never calls Vercel CLI or a Vercel deployment-creation API; deployment creation remains the Git integration's responsibility;
- promotion evidence is retained in the GitHub Actions run summary; normal Control Plane reconciliation remains responsible for project lifecycle evidence;
- ref updates performed by the native `GITHUB_TOKEN` do not recursively start push workflows, so the promoter explicitly dispatches `Exact Preview browser evidence` for the exact candidate and waits for the candidate-scoped `Factory Preview browser evidence` commit status; `evidence/preview/**` is a non-deploying recovery trigger, while only `preview/**` can request Vercel deployment;
- exact browser evidence waits for the Vercel commit status to reach success before using a Vercel check URL; early Preview Comments checks are not sufficient readiness evidence;
- `ignoreCommand` remains a path-based second guard;
- Vercel `api-deployments-free-per-day` remains an external quota: do not retry deployments or buy capacity automatically.

## Resource quota observability

The Control Plane records provider/resource/metric, used value, limit, percentage inputs, measurement quality, source, window/reset and status. The optional Vercel collector runs every six hours only when its read-only provider credentials are already configured; missing credentials skip that collector cleanly. Preview safety does not depend on those credentials because the GitHub-local promotion budget remains active. GitHub Actions usage remains unknown until a reliable billing/usage source is connected.

## Preview applicability policy

Preview is fail-closed by default. A project can make non-applicability explicit in `factory_projects.manifest.preview`:

- `required: false` with a reason for projects that have no deployable Preview surface;
- `required_paths: ["apps/web/**", ...]` for monorepos where only specific file changes require a Preview.

The policy is evaluated against the exact PR changed-file list. Skipping a Preview still produces durable release-readiness evidence and never skips the human production merge.

## GitHub credentials across repositories

GitHub Actions `GITHUB_TOKEN` is treated as repository-scoped. Inside Actions it may be used only when the target repository equals `GITHUB_REPOSITORY`.

Cross-repository issue/branch/PR/CI/Preview operations require `FACTORY_GITHUB_TOKEN`. The runtime never falls back to the current repository token for a different repository. Configure that secret only in the Factory execution environment and never expose it to generated code or browser clients.

Minimum target-repository permissions depend on the operation: contents read/write, issues read/write, pull requests read/write, and checks read for full Direct delivery. Follow-up readers can use narrower permissions when separate credentials are used.
