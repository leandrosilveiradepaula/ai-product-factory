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
- a supported primary authentication path;
- configured model budget;
- configured per-run reservation;
- known spend not already exhausting the configured budget.

Do not enable the primary model merely because an API key exists. Billing/quota readiness and a bounded smoke test are separate prerequisites. Scheduled Direct additionally requires non-empty budget and reservation variables; the runtime reads current known spend from the Control Plane ledger and blocks if paid usage has unknown cost.

## Verified Preview activation

The project supplies non-secret deployment metadata in `factory_projects.manifest.preview`. `mode: github` discovers the exact Vercel Preview from GitHub check-runs using `GITHUB_TOKEN`; `mode: api` creates/polls the Preview through the Vercel API and requires Vercel team/project metadata.

For the standard manual GitHub Actions path, the job itself provides the activation flags, uses the native `GITHUB_TOKEN`, installs pinned Playwright/Chromium, and invokes `scripts/verify_preview.mjs`. No external browser service or Vercel token is required when the project uses `mode: github`.

For alternative runtimes or `mode: api`, configuration remains explicit: `FACTORY_VERCEL_PREVIEW_ENABLED=true`, provider credentials (`GITHUB_TOKEN` or `VERCEL_TOKEN`), `FACTORY_BROWSER_EVIDENCE_ENABLED=true`, a reviewed `FACTORY_BROWSER_EVIDENCE_COMMAND_JSON`, and an optional bounded timeout.

The Vercel adapters refuse non-Preview environments. The browser adapter receives the exact deployed URL through `FACTORY_PREVIEW_URL` and must return structured JSON evidence. The built-in Playwright verifier checks page load, HTTP status, visible non-empty body, and browser console/page errors.

## Codex

Codex is a selective executor, not the orchestrator. Scheduled Direct remains disabled until the independent primary-model readiness gate is proven. Codex workspace WIF requires the real managed-workspace federation rule and audience; never invent them.

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

## Preview applicability policy

Preview is fail-closed by default. A project can make non-applicability explicit in `factory_projects.manifest.preview`:

- `required: false` with a reason for projects that have no deployable Preview surface;
- `required_paths: ["apps/web/**", ...]` for monorepos where only specific file changes require a Preview.

The policy is evaluated against the exact PR changed-file list. Skipping a Preview still produces durable release-readiness evidence and never skips the human production merge.
