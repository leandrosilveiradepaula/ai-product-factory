# Current status

Last reconciled: 2026-09-27.

## Operational foundation

The Factory now has a persistent Supabase Control Plane for projects, product specs, tasks, runs, decisions, human gates, evaluations, deployments, tool usage, Codex usage, and audit events.

The Factory Console reads live Control Plane state for projects, project backlog, runs, and gates. Console access is protected with Supabase Auth plus an RLS-protected operator allowlist. Privileged Control Plane operations use the service role only after operator authorization.

Human gates are durable. Routing can create a pending gate, and authorized operators can approve or reject it. Approval returns the task/run to the executable queue; rejection cancels it and records the decision/audit event.

## Autonomous runtime

Implemented runtime chain:

Idea / intake -> Discovery -> Specification -> Planning -> executable backlog -> routing -> claim -> GitHub Issue -> implementation producer -> branch -> commit -> PR -> CI -> verified preview -> human merge gate -> merge observation -> operations.

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
- explicit `runtime --mode alerts`, scheduled hourly with deterministic per-code deduplication and backend-only GitHub issue writes;
- optional fail-closed Vercel preview adapters: GitHub-integrated discovery using the workflow `GITHUB_TOKEN`, plus Vercel API token fallback; neither can target production;
- bounded scheduled `runtime --mode preview` with a read-only probe; Playwright is installed only when a queued run actually requires browser verification. Explicit project policy may mark Preview not applicable; all paths still stop at `awaiting_release`;
- side-effect-free readiness reporting for Vercel preview and GitHub Issues alerts; both remain disabled until explicit enable flags and complete configuration are present;
- modern Supabase server credentials (`SUPABASE_SECRET_KEY`) across the Console, Python runtime adapters, and GitHub Actions, with legacy service-role fallback;
- repo-aware GitHub credential resolution: the native Actions token is accepted only for the current repository, while cross-repository delivery requires explicit `FACTORY_GITHUB_TOKEN`;
- an hourly bounded autonomous runner for supported work;
- a bounded CI follow-up worker that resumes `ci_pending` Direct runs without model calls and moves green CI to `preview_ready`;
- a bounded release follow-up worker that only observes a human PR merge, records the merge evidence, marks the run `merged`, and closes the issue after that human action.

Scheduled Direct is wired but remains inert unless Primary is explicitly enabled and both model budget and per-run reservation are configured; runtime auth and the Control Plane cost ledger still fail closed before claim/provider use. Dispatch, CI follow-up, Preview follow-up, release observation, recovery, and operational alerts may run hourly without paid model access.

## Console deployment

The Factory Console is deployed on Vercel at `https://ai-product-factory-console.vercel.app` and connected to the live Supabase Control Plane.

Verified production state:
- Supabase Auth login is operational;
- the bootstrap administrator exists as an active `admin` operator;
- server-side Supabase access prefers `SUPABASE_SECRET_KEY` with legacy service-role fallback only;
- the production health probe `GET /api/health` is public, returns HTTP 200, and exposes only service status plus a truncated deployment commit;
- production deployment `dpl_9gokAMNCw8JnBY7jPNZ67LzcwiL9` for merge commit `96fb81c3eb6de66c955562a604d3460ad99a92ae` reached `READY`;
- production health was verified after the redesign release: `GET /api/health` returned HTTP 200 with service `ai-product-factory-console` and commit `96fb81c3eb6d`;
- unauthenticated production root returned the redesigned shell and login surface successfully; no runtime errors were reported by Vercel in the verification window.

## Authentication / model gate

OpenAI API authentication and Codex workspace authentication are intentionally separate.

The existing API key reached the OpenAI API but returned HTTP 429/quota, so the Factory does not use it for unattended paid work.

Codex Workload Identity Federation support has been prepared for GitHub OIDC. A manual preflight workflow exists. On 2026-09-27 the Infodive managed ChatGPT workspace Admin Portal was inspected directly in both current and legacy administration surfaces; the documented `Workload identity` section is not present. This confirms the external beta enablement is still missing. Issue #240 tracks the required OpenAI Support/admin action before the preflight can be exercised.

The selective Codex worker is implemented behind fail-closed activation: atomic Codex-only claim, isolated checkout, workspace-bounded CLI execution, file/byte limits, durable invocation ledger, existing GitHub Issue/branch/PR delivery loop, and an OIDC/WIF Actions job. The job performs no OIDC minting, CLI installation, queue claim, or Codex call unless the enable flag, WIF values, cross-repository GitHub credential, and Control Plane credentials are all present. GitHub credentials are used only by the parent checkout path and are removed from the Codex subprocess environment.

Production migration `20260927010724_factory_claim_next_codex_run` is applied and verified in the live Control Plane. The Codex claim and invocation-ledger functions are service-role-only; `anon` and `authenticated` have no execute permission. No Codex invocation was generated by activation.

Codex invocations performed by the Factory so far: 0.

## Codex official access-token fallback

Current OpenAI documentation confirms that ChatGPT Business supports Codex access tokens for trusted non-interactive automation. The Factory now supports the official `CODEX_ACCESS_TOKEN` path as a temporary alternative while workspace WIF beta remains unavailable.

Security rules:
- complete WIF remains preferred and takes precedence;
- partial WIF fails closed and never falls back to a token;
- the token is read only from GitHub Environment secret `openai-codex/CODEX_ACCESS_TOKEN`;
- the token is passed only to the Codex subprocess, not to clone/GitHub logic or generated files;
- browser cookies, scraped sessions, `CHATGPT_ACCESS_TOKEN`, API keys and other unofficial substitutes remain rejected;
- the manual Codex auth preflight validates login without running a Codex task.

No token has been created or stored by the Factory, and `FACTORY_CODEX_ENABLED` remains false until preflight evidence exists.

## First pilot

Repository: `leandrosilveiradepaula/agente-sql-langgraph`.

The project is onboarded and tracked by the Factory. Existing semantic/product constraints remain authoritative. The next planned-filters line was selected and implemented offline in pilot PR #18: generic fail-closed multi-value `IN` bindings, with full `Offline validation` green and no semantic activation. `dre_custos` and `dre_despesas_operacionais` remain semantically blocked until versioned evidence/decision exists. The 63-question benchmark is postponed and must not be started implicitly by the Factory.

## Production boundary

Production release requires a human gate. For repositories where merging the PR triggers production, the verified-preview path stops at `awaiting_release`; the Factory never performs that merge automatically. A follow-up observer may record the merge and close the linked issue only after the human merge has already happened. Destructive data changes, sensitive access expansion, paid-service creation, and material product requirement changes also require human authority regardless of environment.

## Factory completion audit

The Factory core now has an explicit executable completion contract in `docs/FACTORY_ACCEPTANCE.md` and `tests/test_factory_acceptance.py`. The dedicated CI job `factory-acceptance` verifies the lifecycle, routing, Preview policy, release boundary, operational workers, paid-model gates, Codex/WIF isolation, migration-history presence, and benchmark safety without calling external providers.

The completion audit also found historical Supabase migration-version drift. Repository migration filenames have been reconciled to the versions already recorded by production Supabase. The original base schema and FK-index migrations have been restored under their production version IDs.

Three runtime/delivery functions that predated complete migration-history discipline are consolidated in `20260927014211_reconcile_runtime_delivery_functions.sql` using their current production definitions. The migration was first validated against the live schema inside `BEGIN ... ROLLBACK`, then applied to production and verified for SECURITY INVOKER plus service-role-only EXECUTE access.

The Agent SQL pilot is explicitly deferred and is not part of the current Factory finalization scope.

## Live transactional validation

A production-schema transactional smoke was completed on 2026-09-27 with explicit rollbacks. The smoke covered intake/bootstrap, product stages, backlog dispatch, Direct execution claim/delivery persistence, human gate approval, Codex claim/ledger, and lease recovery.

It found and fixed a real Control Plane schema mismatch: seven RPCs wrote `task_id` into `factory_audit_events`, but the column was missing. Production migration `20260927014826_add_factory_audit_task_id` added the nullable FK and `idx_factory_audit_task`.

After the fix, all transactional smoke paths passed. Final residual state remained zero synthetic projects, zero active runs, zero pending gates, and zero persisted Codex invocations.

GitHub Actions validation is available during the temporary public-repository window opened on 2026-09-27. Main `validate` run #1041 completed successfully, including unit tests, compile and `factory-acceptance`; `Console validation` run #209 also completed successfully with install, typecheck and build. The previously quota-blocked exact redesign candidate `10f593d7d169d30fe5048eac9d98a94b8be1e151` was rerun and both `validate` and `Console validation` passed. Browser/Playwright evidence for that historical candidate remains a separate pending item.

## OpenAI authentication reconciliation

Current official OpenAI documentation was reconciled against the Factory runtime on 2026-09-27.

Findings:
- Codex workload identity requires `OPENAI_FEDERATION_RULE_ID` plus `OPENAI_IDENTITY_TOKEN_FILE`; the OIDC audience belongs to the external token-minting layer.
- The existing Codex producer incorrectly treated `OPENAI_WIF_AUDIENCE` as a Codex process credential. Issue #229 corrects that coupling while keeping audience validation in GitHub Actions.
- API workload identity is a separate OpenAI Platform feature. The Factory previously detected API WIF configuration but the Responses provider still required `OPENAI_API_KEY`; issue #229 implements the actual GitHub OIDC -> OpenAI short-lived token exchange using the official `OPENAI_IDENTITY_PROVIDER_ID`, `OPENAI_SERVICE_ACCOUNT_ID`, and `OPENAI_WIF_AUDIENCE` variables.
- API WIF improves credential security but does not bypass API Platform billing/quota.
- The connected OpenAI Platform account exposes organization `Personal` and project `Default project`; billing state is not exposed through the available connector.
- An OpenAI email dated 2026-09-04 reported the Infodive ChatGPT workspace out of credits at that time; the user has confirmed the workspace currently has credits. The historical email must not be treated as current status. ChatGPT workspace credits remain separate from API Platform credits.
- No new email response has been found confirming Codex WIF beta enablement or providing a federation rule.

No paid model call and no credit purchase were performed during this reconciliation.

## Codex WIF runtime hardening

Current official Codex WIF guidance was reconciled again on 2026-09-27. The Factory already pins Codex CLI `0.157.0`, satisfying the documented WIF minimum `0.148.0`.

Issue #235 hardens the GitHub Actions path before any workspace activation:
- preflight is bound to GitHub Environment `openai-codex`;
- GitHub OIDC claims are decoded locally and checked for exact issuer, audience, immutable subject (including stable owner/repository IDs), repository, main ref and environment;
- raw JWTs are never logged;
- identity-token writes are atomic with restrictive directory/file permissions;
- the long-running Codex worker refreshes GitHub OIDC every 240 seconds so a later Codex exchange can use a current source token;
- audit context now records `openai-codex` instead of the generic `ci` label.

OpenAI additionally recommends managed `permissions.filesystem.deny_read` protection for the token directory. That control belongs to managed Codex/workspace policy and remains part of the external Codex WIF rollout once the beta is enabled.

## OpenAI API WIF configured

The OpenAI API workload identity path is now configured end-to-end at the administrative level.

OpenAI Platform:
- Workload Identity Provider `github-actions-ai-product-factory`;
- provider ID `idp_cc3f1adbaa5185a08932c2e9`;
- audience `https://api.openai.com/v1`;
- project `Default project`;
- restricted service account `ai-product-factory-primary` with ID `user-964d27e5d9d6b216dd475e06`;
- intended GitHub mapping for the Factory repository, main ref and `openai-api` environment; current service-account mapping is not yet accepted by OpenAI because it does not match the actual immutable GitHub OIDC token attributes;
- model access restricted to the model-request/Responses capability required by the Factory.

GitHub:
- Environment `openai-api` exists with the three non-secret WIF variables configured;
- Environment `openai-codex` exists and remains intentionally empty pending the managed ChatGPT workspace federation rule.

The no-model API WIF preflight is implemented and has executed on a real GitHub-hosted runner. GitHub OIDC issuance succeeds, but OpenAI currently rejects the token exchange with `HTTP 401 / invalid_grant` because the configured service-account mapping does not match the token attributes. The observed immutable subject is `repo:leandrosilveiradepaula@256917842/ai-product-factory@1387883686:environment:openai-api`. Issue #250 tracks the required OpenAI Platform mapping correction. No model endpoint was called.

The API Platform Billing screen currently reports `$0.00` credit remaining. Therefore `FACTORY_PRIMARY_MODEL_ENABLED` remains false and no paid model smoke is authorized. No credits were added automatically.

## Operational Console redesign

Issue #224 is completed and PR #239 was merged to `main` by explicit human release authorization on 2026-09-27. The delivered Console includes the dark developer-tool shell, collapsible sidebar, overview, projects/project detail, New Work, runs/run detail, Work Queue, Human Gates, Evals, Deployments, Models & Usage, Audit Log, Configuration and operator administration.

All operational views use real Control Plane data through the existing server-side Supabase boundary. A live schema compatibility check confirmed zero missing database columns for the new queries. Factory acceptance requires these operational surfaces and checks that privileged Factory/OpenAI/GitHub secrets are not present in the Console TSX surface. The visual layer is centralized: `apps/console/app/theme.css` owns typography, palette, semantic status colors, radii and spacing, while `apps/console/app/ui.tsx` owns reusable page/header/metric/status/action primitives.

Release evidence:
- candidate commit `10f593d7d169d30fe5048eac9d98a94b8be1e151` had exact Vercel Preview deployment `dpl_CNFAo32v4DHzjCzgmx1xZUsKFkwX` in `READY` state and GitHub Vercel status `success`;
- At release time, GitHub Actions could not run because the account had consumed 2,000 / 2,000 included Actions minutes. After opening a temporary public window, the exact candidate `10f593d7d169d30fe5048eac9d98a94b8be1e151` was rerun and both `validate` (including `factory-acceptance`) and `Console validation` passed;
- Playwright/browser evidence was not rerun yet. The original production merge remains recorded as a human-authorized exception at release time, while the missing CI evidence has now been recovered retroactively;
- squash merge commit is `96fb81c3eb6de66c955562a604d3460ad99a92ae`;
- production Vercel deployment `dpl_9gokAMNCw8JnBY7jPNZ67LzcwiL9` reached `READY`;
- production `GET /api/health` returned HTTP 200 and commit `96fb81c3eb6d`;
- Vercel reported no runtime errors in the post-release verification window.

Figma MCP Starter calls remain exhausted, so no additional design-context comparison can be performed until that quota resets. GitHub Actions validation has been recovered during the temporary public window; only the historical exact-candidate Playwright/browser evidence remains pending.

## Temporary public Actions window

The repository was made public by the owner on 2026-09-27 to temporarily recover GitHub-hosted Actions capacity without adding paid Actions budget. Before opening, the repository was audited for literal credentials; fork workflows were disabled, default workflow permissions were read-only, Vercel Git Fork Protection was confirmed enabled, and acceptance checks reject `pull_request_target`, PR secrets and PR OIDC.

Current observed public-window state:
- 0 forks observed at the latest check;
- 0 open external pull requests observed at the latest check;
- main CI/factory-acceptance green;
- Console typecheck/build green;
- exact historical redesign candidate CI recovered green;
- paid model execution remains disabled;
- Codex execution remains disabled;
- Agent SQL 63-question benchmark remains excluded.

The repository must return to private after the remaining verification debt is closed or the temporary window is no longer needed.

## Console security boundary audit

The operational Console redesign was checked against the live Control Plane boundary:

- 1 active Console operator and 1 active admin exist;
- all 11 Factory Control Plane tables deny direct table privileges to `anon` and `authenticated` while retaining privileged server-side service access;
- 15 critical runtime/Console RPCs were checked and remain `SECURITY INVOKER`;
- those RPCs deny `EXECUTE` to `anon` and `authenticated` and allow the server-side `service_role`;
- the redesigned TSX client surface is covered by Factory acceptance assertions that privileged Supabase/OpenAI/GitHub secret names are not rendered into pages.

## Next engineering blocks

1. Configure the cross-repository GitHub credential `FACTORY_GITHUB_TOKEN` before executing Direct/Codex work against repositories other than `ai-product-factory`.
2. Configure the external managed-workspace values required by `docs/AUTH_ACTIVATION_READINESS.md`, validate Codex WIF preflight, and only then set `FACTORY_CODEX_ENABLED=true`.
3. Validate Primary model quota/billing once administratively ready; keep `FACTORY_PRIMARY_MODEL_ENABLED` false until then.
4. For projects with official Vercel↔GitHub integration, `mode: github` uses the workflow `GITHUB_TOKEN` and the manual Preview job self-hosts pinned Playwright/Chromium; no Vercel token or external browser service is required. `VERCEL_TOKEN` remains an API-mode fallback for other projects.
5. Verified Preview and operational alerts are now scheduled bounded follow-ups; production still stops at the human merge gate.
6. Supabase Auth leaked-password protection is currently reported disabled by the security advisor; enable it through the Supabase Auth dashboard when administrative hardening is performed.
