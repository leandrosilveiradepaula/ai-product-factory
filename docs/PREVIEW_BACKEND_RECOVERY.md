# Preview backend unavailable — bounded delivery recovery

## Why this exists (observed, not simulated)

In the greenfield pilot, the Factory produced the real [Service Desk PR #10](https://github.com/leandrosilveiradepaula/infodive-service-desk/pull/10), candidate `17edf217dceb0b75bf944e8e1737a0ba92bfb2fc`, and native CI/quality/security/QA/operations PASS. The Vercel Preview deployment was READY, but browser `browser_e2e` actually failed with `HTTP 503 /api/session` (`backend_unavailable`). The delivery run `52998a8f-b478-46b3-9529-08bea72034f3` and task became failed; the Change Set `60dd6b73-3e98-4da0-bc36-4be6d7562f45` remains `ci_pending`.

The existing `factory_resume_preview_browser_infrastructure_failure` only handles a missing pinned Chromium executable. It explicitly rejects this backend-503 failure. Do not loosen that existing exception or erase negative browser evidence. Do **not** mark the greenfield proof complete because a Vercel deployment says READY.

The Service Desk is destined to be a module of CRM Infodive. This patch does **not** provision a separate Supabase project, copy CRM credentials, add Service Desk functionality, enable an old branch or merge anything.

## What the recovery does

After separately authorized, correctly scoped **Preview backend configuration**, a privileged operator can invoke a deterministic, secretless preflight. It verifies the live GitHub PR (open, non-draft, exact branch/SHA/repository), pinned Vercel provider signal, Control Plane Preview deployment/failed browser evidence, and the same SHA and URL. It performs an unauthenticated HTTPS GET of `/api/session`, without cookies or authorization. Only HTTP **200 or 401 with a JSON content type**, no redirects, counts as evidence that the previous 503 is absent. The probe installs an explicit no-redirect HTTP handler *before opening the URL*; a malicious 3xx `Location` must never be fetched, even if a later check would otherwise reject the final URL. This is a readiness probe, **not** a complete browser test.

The new PostgreSQL `factory_resume_preview_backend_unavailable_v1` RPC (service-role-only, `SECURITY INVOKER`) rechecks run/task/Change Set, project state/epoch, lease, exact CI and quality, specialists, original 503 evidence, real Preview URL and a probe at most ten minutes old. It allows **at most two** resumptions per original run, using durable audit history and row locks. A successful resume changes only failed run → `preview_ready` and failed task → `integrated`, preserving the original `browser_e2e: failure` and leaving Change Set `ci_pending`. It never asserts `browser_verified`, `awaiting_release` or `product_ready`.

The existing Preview lane must then run a **new** authenticated/sandboxed browser check. If the backend is still broken, it must fail closed again. Production release always requires a new verified Preview, exact quality gates and **human merge**. There is no new model call, Product Stage replay, new branch, PR, deploy, user, or auto-merge in this recovery.

## Autonomous waiting for new backend-503 incidents (candidate hardening)

The Factory's existing Preview lane previously turned every Playwright failure,
including a real `http_503: fetch /api/session`, into terminal
`factory_runs.status=failed` and `factory_tasks.status=failed`. That is
appropriate for genuine code/E2E failures, but made a missing *external*
Preview backend configuration require privileged manual recovery every time.

The new fail-closed path applies **only** when the actual browser returned
`status=failure` with the specific session 503 marker on the exact successful
Preview URL. It records the original `browser_e2e=failure` and an audit event,
but leaves the delivery `preview_ready` rather than reporting a successful
browser. The next scheduler probe verifies the *latest* failed browser
evaluation is bound to an existing successful deployment for the **same
run, candidate SHA and URL**. If the backend still refuses a credentialless
JSON session GET, it returns `waiting_external_backend`, with
`claimed=false`, so Actions does not install Playwright or rerun Product
Stage. On HTTP 200/401 JSON the normal **new** E2E executes, with full
SHA/epoch/base/PR and human-release gates still required.

- No redirect, cookie, bearer credential or body is transmitted/recorded by
  the environmental probe. It never sets a PASS status or authorizes release.
- Other browser errors (including generic HTTP 503 from other routes) retain
  the existing terminal-failure policy and do not become infinite retries.
- A forged, stale, cross-SHA or unbound prior browser evaluation **blocks** the
  preflight before it makes the external network request.
- Existing **historical failed runs remain failed**. In particular the
  original Service Desk run `52998a8f-b478-46b3-9529-08bea72034f3`
  still requires the independently authorized, already installed recovery
  RPC after legitimate environment remediation. No Product Stage replay.
- This capability itself cannot resolve the missing Service Desk Preview
  configuration; do not copy CRM credentials or assume its separate Vercel
  deployment represents the future Service Desk module within CRM.

Global certification remains `product_ready=false` until independent E2E
evidence completes the six domains.

## Activation (human gates, not part of this PR)

1. Merge the Factory PR **humanly** only after `validate`, `factory-acceptance` and `preview-backend-recovery-postgres` are green on the exact final SHA. No change under `apps/console/**`: Factory Console Preview is **N/A** by path policy.
2. Review and **separately authorize** applying `20261026170000_resume_preview_backend_unavailable.sql` to Factory Control Plane; confirm migration history and service-role-only grants. No schema application happens in this PR.
3. Reconcile the product decision Service Desk-as-CRM-module, authorize the required Preview authentication/backend environment and configure secrets *server-side*, never in GitHub comments, the browser or chat. Do not create paid infrastructure or copy CRM credentials automatically.
4. In a trusted operator environment that has the configured Factory Control Plane key and legitimate GitHub App/`FACTORY_GITHUB_TOKEN` permissions, execute the **read-only** preflight (fails on 503, redirect, missing JSON or changed SHA):

   ```bash
   PYTHONPATH=src python scripts/resume_preview_backend_unavailable.py \
     --project-key infodive-service-desk \
     --run-id 52998a8f-b478-46b3-9529-08bea72034f3
   ```

5. Only after the environment's authorization and preflight PASS, invoke the same command with `--execute --ack-environment-authorized`. This is the privileged **nonproduction status-recovery** action; no SQL is executed by the initial preflight.
6. Allow the existing scheduled Preview follower to rerun on the exact preserved candidate. Observe fresh `browser_e2e` and whether the Factory correctly advances to `awaiting_release` or fails again. The eventual release/operations proof still requires authorized human merge and post-release observation.

## Verification

- Offline: `PYTHONPATH=src python -m unittest tests.test_preview_backend_unavailable -v`.
- Real disposable PostgreSQL 16: `.github/workflows/preview-backend-recovery-postgres.yml`, guarded by `FACTORY_PREVIEW_BACKEND_TEST_ISOLATED=true` and exact local database identity.
- Negative cases: missing probe fields, malformed hostname, wrong PR/SHA/repository/branch, stale/future proof, 503/redirect/HTML, changed epoch/paused project, lease owner, pending specialist, missing CI, failed browser of another class, double dispatch, two-attempt limit.
- No credentials, production migration, real deploy, paid API or Service Desk mutation are used by those tests.

This is a **recovery capability**, not completion of greenfield certification. Six independent global domains remain subject to separate current-SHA evidence.
