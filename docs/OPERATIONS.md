# Operations Runbook

This runbook describes the safe operating modes of the AI Product Factory runtime. It intentionally contains no secret values.

## Runtime modes

| Mode | Purpose | External side effects | Default scheduling | Main gate |
| --- | --- | --- | --- | --- |
| `health` | Report configuration/readiness only | None | Hourly runner | None |
| `recovery` | Requeue expired leases or fail exhausted runs | Control Plane writes | Hourly runner | Bounded attempts |
| `product` | Execute one product-stage run | Model call + Control Plane writes | Hourly only when ready | Primary enable + auth + budget |
| `dispatch` | Route one planned task | Control Plane writes | Hourly bounded + manual | Optional project key |
| `direct` | Produce implementation and open PR | Model + GitHub writes | Hourly only after explicit Primary+budget activation; manual supported | Primary enable + auth + ledger budget + risk gate |
| `codex` | Execute one already-routed complex implementation through isolated Codex CLI and open PR | Codex workspace + GitHub writes | Hourly/manual only when explicitly enabled and auth-ready | Codex enable + complete WIF or official `CODEX_ACCESS_TOKEN` + repository-scoped GitHub credential + Control Plane; cross-repo additionally requires `FACTORY_GITHUB_TOKEN` |
| `ci` | Resume one `ci_pending` run | GitHub reads + evidence writes | Hourly | Matching durable PR evidence |
| `preview` | Deploy and verify one `preview_ready` run | Vercel Preview + browser/e2e + evidence writes | Hourly bounded + manual | Preview applicability/readiness + quality evidence |
| `release` | Observe one human PR merge | GitHub reads; issue close/evidence after merge | Hourly | Human merge must already exist |
| `alerts` | Evaluate operational alerts and publish deduplicated GitHub Issues | GitHub issue writes | Hourly bounded + manual | Backend GitHub issue permission |

## Required release sequence

1. Implementation opens a PR; production is not touched.
2. CI follow-up verifies the PR head matches the durable candidate commit.
3. Green CI persists explicit `quality_gate` evidence.
4. Preview applicability is evaluated from explicit project policy and the PR changed files. Missing policy fails closed to Preview required. `required=false` or a non-matching `required_paths` policy records durable `preview_not_required` evidence instead of fabricating a deployment.
5. When Preview is required, it requires the same candidate commit, successful quality evidence, Preview deployment, and successful browser/e2e evidence for the exact Preview URL.
6. The run moves to `awaiting_release`.
7. A human reviews and merges the PR. The Factory never performs this production merge.
8. The release observer sees the already-merged PR, records the merge SHA/audit evidence, marks the run `merged`, and closes the linked issue.

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

## Operational alerts

The scheduled alerts job explicitly enables the GitHub Issues sink for that job only. Alert issues are deduplicated by deterministic code. Non-billable GitHub/Supabase usage without cost data must not be treated as unknown paid spend.

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

Target policy (PR #341):
- `main` remains the production branch;
- implementation branches such as `console/**` and `test/**` do not deploy automatically;
- after required CI/acceptance checks are green, the explicit candidate-promotion workflow moves `preview/pr-<n>` to the exact PR head SHA;
- only `preview/**` is allowed to create the final Preview candidate;
- `ignoreCommand` remains a path-based second guard;
- Vercel `api-deployments-free-per-day` is an external quota blocker: do not retry deployments or buy capacity automatically.

Until #341 is released, the repository is still operating under the previous Vercel Git policy. Do not describe the target policy as active before that release.

## Resource quota observability

The Control Plane records provider/resource/metric, used value, limit, percentage inputs, measurement quality, source, window/reset and status. Unknown provider usage remains unknown rather than estimated. Current Vercel daily deployment usage is measured as a derived rolling-window count from deployment API data; GitHub Actions usage remains unknown until a reliable billing/usage source is connected.

## Preview applicability policy

Preview is fail-closed by default. A project can make non-applicability explicit in `factory_projects.manifest.preview`:

- `required: false` with a reason for projects that have no deployable Preview surface;
- `required_paths: ["apps/web/**", ...]` for monorepos where only specific file changes require a Preview.

The policy is evaluated against the exact PR changed-file list. Skipping a Preview still produces durable release-readiness evidence and never skips the human production merge.

## GitHub credentials across repositories

GitHub Actions `GITHUB_TOKEN` is treated as repository-scoped. Inside Actions it may be used only when the target repository equals `GITHUB_REPOSITORY`.

Cross-repository issue/branch/PR/CI/Preview operations require `FACTORY_GITHUB_TOKEN`. The runtime never falls back to the current repository token for a different repository. Configure that secret only in the Factory execution environment and never expose it to generated code or browser clients.

Minimum target-repository permissions depend on the operation: contents read/write, issues read/write, pull requests read/write, and checks read for full Direct delivery. Follow-up readers can use narrower permissions when separate credentials are used.
