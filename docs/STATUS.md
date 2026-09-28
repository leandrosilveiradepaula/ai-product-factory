# Current status

Last reconciled: 2026-09-28.

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

Scheduled Direct is enabled through the retained API key with a prepaid Factory budget of US$ 4.00 and a US$ 0.50 per-call/run reservation. It remains bounded by queue availability, real Control Plane spend and unknown-cost fail-closed checks before provider use. Product Stage uses the same paid boundary. Dispatch, CI follow-up, Preview follow-up, release observation, recovery, and operational alerts may run hourly without paid model access.

## Console deployment

The Factory Console is deployed on Vercel at `https://ai-product-factory-console.vercel.app` and connected to the live Supabase Control Plane.

Verified production state:
- production currently serves release commit `24fc055271c6` from the Figma fidelity release; later `main` commits are backend/docs-only and are intentionally skipped by the Console Vercel path guard;
- Supabase Auth login is operational;
- the bootstrap administrator exists as an active `admin` operator;
- server-side Supabase access prefers `SUPABASE_SECRET_KEY` with legacy service-role fallback only;
- the production health probe `GET /api/health` is public, returns HTTP 200, and exposes only service status plus a truncated deployment commit;
- production deployment `dpl_9gokAMNCw8JnBY7jPNZ67LzcwiL9` for merge commit `96fb81c3eb6de66c955562a604d3460ad99a92ae` reached `READY`;
- production health was verified after the redesign release: `GET /api/health` returned HTTP 200 with service `ai-product-factory-console` and commit `96fb81c3eb6d`;
- unauthenticated production root returned the redesigned shell and login surface successfully; no runtime errors were reported by Vercel in the verification window.

## Protected Preview / Console intake release

Vercel Trusted Sources now includes GitHub Actions OIDC for `leandrosilveiradepaula/ai-product-factory`, branch `main`, environment `Preview`. The browser verifier sends the short-lived GitHub OIDC token in `x-vercel-trusted-oidc-idp-token`; no Vercel token or reusable bypass secret is required for the standard path.

Released PR #269 candidate:
- head `505c712864950d94638c874d8e267531fb544d62`;
- exact Vercel Preview deployment `dpl_J9kneq8tf9bouJ3StBPyh4UNd7GX` is `READY`;
- Console `validate`, `factory-acceptance`, typecheck and build are green;
- Playwright/OIDC run `36376673624` passed `page_load`, `http_status`, `body_visible`, `expected_text` and `console_clean`;
- observed pt-BR shell includes `Visão geral`, `Projetos`, `Execuções`, `Fila de trabalho`, `Aprovações humanas`, `Avaliações`, `Implantações`, `Modelos e uso`, `Log de auditoria`, `Configuração` and `Operadores`.

PR #269 added the conversational new-project path, ongoing-project reconcile-first onboarding, private attachment storage, durable current-state snapshots and the pt-BR Console surface. Human authorization was given on 2026-09-28; the Supabase production migrations were applied and verified before release, including fail-closed RLS, service-role-only RPC access, a private 10 MiB attachment bucket, and the snapshot `run_id` FK index. PR #269 was then squash-merged as `98d81dee46c7ffc7ae4ae0662712fadcda3258b3`. Production deployment `dpl_KEEZQTBxLTcVJCzF42skk4V8kUAf` reached `READY`; `GET /api/health` returned HTTP 200 with commit `98d81dee46c7`; the unauthenticated production shell rendered in pt-BR; and Vercel reported no runtime errors in the verification window.

## Authentication / model gate

OpenAI API authentication and Codex workspace authentication are intentionally separate.

The retained API key is billing-ready and is the explicit current Primary auth mode. On 2026-09-28, after the user manually added US$ 5 of API Platform credit, workflow `OpenAI billing smoke once` run `36413373572` executed exactly one bounded GPT-5.6 Luna request and returned `FACTORY_SMOKE_OK`. Usage was 35 input + 9 output = 44 tokens, with estimated cost US$ 0.0000178 under a US$ 0.01 ceiling; the run, usage, provider reference and cost were persisted in the Control Plane. Primary was then enabled with a US$ 4.00 Factory budget and US$ 0.50 reservation, leaving US$ 1.00 outside the Factory budget. Real paid calls pre-reserve ledger cost; successful calls replace that reservation with actual measured cost; unmeterable paid outcomes become unknown-cost events that block subsequent paid execution.

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

## Manual Codex Control Plane activation

Production migration `20260927152310_manual_codex_handoff` is applied in Supabase and the repository migration history uses the same version ID.

A live-schema transactional smoke with explicit `ROLLBACK` verified:
- Codex-routed queue claim -> `preparing_codex_manual`;
- durable GitHub Issue binding -> `awaiting_codex_manual`;
- manual PR adoption -> `ci_pending`;
- candidate SHA/branch persistence;
- zero-cost GitHub PR evidence;
- automated Codex invocation count remains zero;
- the three manual-Codex audit events are persisted inside the transaction.

After rollback: zero synthetic projects, zero active runs, zero pending gates and zero Codex invocations remained.

## Manual Codex fallback

The operating strategy is now explicit: deterministic tools first, OpenAI API/Direct as the primary AI path, and Codex only when its marginal value justifies the extra cost/complexity.

While unattended Codex authentication is externally unavailable, a Codex-routed task no longer blocks unrelated Factory work. The scheduled runtime can:
- claim one queued Codex task into a durable `preparing_codex_manual` state;
- create or reuse a GitHub Issue containing the exact `Factory run: <run_id>` marker and operator instructions;
- move the run to `awaiting_codex_manual` without storing any human credential;
- watch for an open PR containing that exact marker;
- adopt the PR head SHA/branch as durable candidate evidence and move the run to `ci_pending`;
- resume the existing CI -> Preview -> `awaiting_release` path.

Manual work initiated outside the Factory does not increment `factory_codex_usage.invocation_count`. The GitHub PR adoption is recorded as zero-cost GitHub delivery evidence. Automatic Codex remains available later when WIF or the official access-token path is activated.

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

GitHub Actions validation is available during the temporary public-repository window opened on 2026-09-27. For the #269 production merge commit `98d81dee46c7ffc7ae4ae0662712fadcda3258b3`, both `validate` and `Console validation` completed successfully. The previously quota-blocked exact redesign candidate `10f593d7d169d30fe5048eac9d98a94b8be1e151` was rerun and both `validate` and `Console validation` passed. Its historical exact Playwright artifact was not recreated; the exact protected Preview evidence for the released #269 candidate is the operative release evidence.

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

The user manually added US$ 5.00 of API Platform credit on 2026-09-28 with auto-reload left OFF. The bounded smoke succeeded and Primary was subsequently enabled via explicit API-key mode under a US$ 4.00 Factory budget with US$ 0.50 reservation. WIF issue #250 remains open as authentication hardening and does not override or silently replace the selected API-key path.

## Operational Console redesign

Issue #224 is completed and PR #239 was merged to `main` by explicit human release authorization on 2026-09-27. The delivered Console includes the dark developer-tool shell, collapsible sidebar, overview, projects/project detail, New Work, runs/run detail, Work Queue, Human Gates, Evals, Deployments, Models & Usage, Audit Log, Configuration and operator administration.

All operational views use real Control Plane data through the existing server-side Supabase boundary. A live schema compatibility check confirmed zero missing database columns for the new queries. Factory acceptance requires these operational surfaces and checks that privileged Factory/OpenAI/GitHub secrets are not present in the Console TSX surface. The visual layer is centralized: `apps/console/app/theme.css` owns typography, palette, semantic status colors, radii and spacing, while `apps/console/app/ui.tsx` owns reusable page/header/metric/status/action primitives.

Release evidence:
- candidate commit `10f593d7d169d30fe5048eac9d98a94b8be1e151` had exact Vercel Preview deployment `dpl_CNFAo32v4DHzjCzgmx1xZUsKFkwX` in `READY` state and GitHub Vercel status `success`;
- At release time, GitHub Actions could not run because the account had consumed 2,000 / 2,000 included Actions minutes. After opening a temporary public window, the exact candidate `10f593d7d169d30fe5048eac9d98a94b8be1e151` was rerun and both `validate` (including `factory-acceptance`) and `Console validation` passed;
- the historical `10f593...` Playwright artifact was not recreated. The original production merge remains recorded as a human-authorized exception; the active PR #269 now has exact protected-Preview Playwright/OIDC evidence and supersedes the historical operational verification need;
- squash merge commit is `96fb81c3eb6de66c955562a604d3460ad99a92ae`;
- production Vercel deployment `dpl_9gokAMNCw8JnBY7jPNZ67LzcwiL9` reached `READY`;
- production `GET /api/health` returned HTTP 200 and commit `96fb81c3eb6d`;
- Vercel reported no runtime errors in the post-release verification window.

Figma MCP Starter calls remain exhausted, so no additional design-context comparison can be performed until that quota resets. GitHub Actions validation and current exact protected-Preview browser evidence are green. The unrecreated historical `10f593...` browser artifact is archival debt, not a blocker for the current release candidate.

## Temporary public Actions window

The repository was made public by the owner on 2026-09-27 to temporarily recover GitHub-hosted Actions capacity without adding paid Actions budget. Before opening, the repository was audited for literal credentials; fork workflows were disabled, default workflow permissions were read-only, Vercel Git Fork Protection was confirmed enabled, and acceptance checks reject `pull_request_target`, PR secrets and PR OIDC.

Current observed public-window state:
- no fork attributable to this repository was confirmed by the available repository search during the latest reconciliation; generic GitHub repository search is not treated as authoritative fork metadata;
- 0 open external pull requests observed at the latest check;
- main CI/factory-acceptance green;
- Console typecheck/build green;
- exact historical redesign candidate CI recovered green;
- Primary paid execution is enabled through explicit `api_key` mode under the prepaid US$ 4.00 Factory budget and US$ 0.50 reservation, with unknown paid cost remaining fail-closed;
- Codex automatic execution remains disabled;
- Agent SQL 63-question benchmark remains excluded.

The repository must return to private after the remaining verification debt is closed or the temporary window is no longer needed.

## Console security boundary audit

The operational Console redesign was checked against the live Control Plane boundary:

- 1 active Console operator and 1 active admin exist;
- all 11 Factory Control Plane tables deny direct table privileges to `anon` and `authenticated` while retaining privileged server-side service access;
- 15 critical runtime/Console RPCs were checked and remain `SECURITY INVOKER`;
- those RPCs deny `EXECUTE` to `anon` and `authenticated` and allow the server-side `service_role`;
- the redesigned TSX client surface is covered by Factory acceptance assertions that privileged Supabase/OpenAI/GitHub secret names are not rendered into pages.

## Reconciliation update - 2026-09-28 after API credit activation

A fresh live reconciliation after the prepaid Primary activation confirmed:
- Supabase project `fjplmxfcshhbmzgvyqlm` is `ACTIVE_HEALTHY`;
- 2 active projects, 0 pending/active runs, 0 failed/dead-letter runs, 0 pending human gates, 0 Codex invocations and 1 active operator;
- all 18 expected production migrations are registered, including ongoing-project reconciliation, private attachments and durable current-state snapshots;
- the Supabase security advisor still reports only the intentional fail-closed RLS-without-public-policy findings plus the administrative `Leaked Password Protection Disabled` warning;
- Console production remains deployment `dpl_KEEZQTBxLTcVJCzF42skk4V8kUAf` at commit `98d81dee46c7`; `GET /api/health` returned HTTP 200 and the Vercel runtime-error view reported no errors in the six-hour verification window;
- later main commits did not change `apps/console/**`, so their production builds were canceled by the intentional Vercel ignore-build policy; this does not replace the active Console production deployment;
- Gmail search found no new OpenAI support response about Codex/WIF enablement or federation values;
- issue #250 was reconciled so API WIF is explicitly treated as authentication hardening while `FACTORY_PRIMARY_AUTH_MODE=api_key` remains the operational mode.

## Next engineering blocks

1. Configure the cross-repository GitHub credential `FACTORY_GITHUB_TOKEN` before executing Direct/Codex work against repositories other than `ai-product-factory`.
2. Configure the external managed-workspace values required by `docs/AUTH_ACTIVATION_READINESS.md`, validate Codex WIF preflight, and only then set `FACTORY_CODEX_ENABLED=true`.
3. Monitor the active Primary budget/ledger; any unknown paid-cost event must remain a hard stop. WIF #250 can be completed later as authentication hardening without changing the current API-key operating mode until explicitly selected.
4. For projects with official Vercel↔GitHub integration, `mode: github` uses the workflow `GITHUB_TOKEN` and the manual Preview job self-hosts pinned Playwright/Chromium; no Vercel token or external browser service is required. `VERCEL_TOKEN` remains an API-mode fallback for other projects.
5. Verified Preview and operational alerts are now scheduled bounded follow-ups; production still stops at the human merge gate.
6. Supabase Auth leaked-password protection is currently reported disabled by the security advisor; enable it through the Supabase Auth dashboard when administrative hardening is performed.


## Audit reconciliation - 2026-09-28

A post-activation audit found and closed a paid-execution drift: historical
manual OpenAI workflows and the `openai-execute` CLI could call the provider
outside the durable Factory budget/ledger. Those shortcuts are retired; paid
operational execution is restricted to the metered product/direct runtime.
The API WIF preflight remains no-model.

Live reconciliation during the audit:
- repository `main` before this hardening pass: `41d666c597e1a9b35ef1d9358034106c0bd559d7`;
- 19 Git migrations exactly match the 19 migrations registered in production Supabase;
- 2 active projects, 0 open runs, 0 failed runs, 0 pending human gates, 0 Codex invocations, 1 active operator;
- visual-evidence registry is empty after authenticated capture cleanup;
- production `GET /api/health` is HTTP 200 and reports Console commit `24fc055271c6`;
- Vercel reported no runtime errors in the six-hour audit window;
- Supabase security advisor reports only the intentional RLS-without-public-policy informational findings plus the administrative Leaked Password Protection warning;
- performance advisor reports only currently-unused indexes; no index is removed solely from this short observation window.

The authenticated Figma correction remains separately pending in #309/#310
because the required Vercel Preview hit the account build-rate limit. The
Factory continues to fail closed rather than merging that Console candidate
without exact Preview evidence.
