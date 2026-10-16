# Authenticated Console visual evidence — exact served SHA (16 Oct 2026)

## Incident and measured evidence

- Human merge of UI PR #882 at 2026-10-16 13:01:15 UTC introduced
  `53bd03b274129925f713f614243093e165f03ed1` into `main`.
  GitHub `validate`, `factory-acceptance` and `Console validation`
  passed on the merge commit.
- GitHub Vercel commit status on that SHA became `success` at
  2026-10-16 13:02:40 UTC: "Deployment has completed". **This status alone
  is not proof that the Console's production alias serves that SHA**.
- The existing workflow
  [#38904687637](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/38904687637)
  was started on that `main` push because the Playwright script changed.
  Its target resolution nevertheless loaded the *historical*
  `.github/authenticated-visual-target.json` with
  `34c614be92a544bb52c1b2634fc6c82b1be6d25e`.
  The validation step checked only that this commit existed, not that
  the actual Vercel URL was serving the declared commit. The test could
  have incorrectly marked UI #882 verified even if its browser run were green.
- The capture actually **failed**, with React production hydration error
  `#418` at `/configuration` (`pageErrorCount=1`,
  `consoleErrorCount=0`, `badResponses=[]`).
  The broker cleanup step succeeded. **No authenticated browser
  evidence for the actual #882 commit was accepted**. A single error
  does not prove that the redesign caused it; reproduce on the exact
  release before editing UI.

## Fail-closed correction

1. Every push to `main` changing `apps/console/**` uses its own
   `GITHUB_SHA` and official production Console hostname, instead of
   reading a stale historical JSON target. Requires checked-out parent
   and safe diff; failures do not assume "no changes".
2. Explicit `workflow_dispatch` requests still accept an exact SHA and
   allowlisted HTTPS `*.vercel.app` origin. Changes without Console code
   may use a **pinned source-controlled target**. This incident pins
   `53bd03b...` for the follow-up audit without manufacturing a second
   Vercel deployment.
3. Require `Vercel` commit status `success` **on the full 40-digit SHA**.
   Independently poll `/api/health` at the exact intended URL and demand
   `status:"ok"`, `service:"ai-product-factory-console"` and
   `commit === SHA.slice(0,12)`. A bare HTTP 200 is insufficient.
   Perform these read-only guards **before** Playwright download and
   ephemeral user provisioning, then recheck after capture before
   accepting/uploading evidence. Tokens remain in runner env only and
   responses do not log sensitive content.
4. The existing Playwright checks continue failing on browser page errors,
   console errors, 4xx/5xx and mobile overflow. Never suppress hydration
   warnings or mark a capture successful after a failed assertion.
   The broker must still delete/expire the ephemeral user on every path.
5. Deterministic Node tests exercise source selection, stale-pin override,
   malicious/unallowed targets, exact health identity and mismatch
   rejection; Python security contracts cover step ordering and fail-closed
   broker semantics. No paid models, provider balance probing, new credits,
   new Vercel deployments or production migrations.

## Release interpretation and remaining gates

The #882 merge already occurred through a human GitHub action and a
corresponding Vercel status was recorded; neither implies product readiness.
The visual check for #882 is **failed/unverified**. After the corrective PR
has CI green and receives **human** merge, the trusted audit should run
against the **still-serving exact #882 production SHA**, if that revision
remains deployed. It must stop before user provisioning if production moved,
the provider status is missing or the health SHA differs.

The separate React `#418` /configuration incident remains to be
reproduced and fixed with genuine browser evidence. Do not "solve" it by
disabling error detection or skipping this route. Future Console changes
require Preview evidence at their candidate SHA **before** production merge;
a green CI/commit status alone is not an acceptable substitute.
