## Reconciliation 2026-10-04 - GitHub App runtime
- CRM GitHub App access is verified `ready` in the Control Plane with short-lived installation credentials and no token persistence.
- Real Actions preflight run `37209692130` succeeded after #644: repository `leandrosilveiradepaula/crm-infodive`, private=true, default branch main, head `23b4992727adb768a7a5b513cd0a181ea5d1e2d5`, auth `github_app_ephemeral`, credential path `github_app_only`, token_persisted=false.
- The first post-activation preflight exposed and fixed a real OIDC broker defect: the runtime no longer attempts generic Control Plane proxy reads before the dedicated GitHub App token broker. The narrow broker boundary remains intact.
- A synthetic write probe was intentionally not added because the CRM preflight is acceptance-protected as read-only and adding another trusted write workflow only to test would expand the security surface. The first real CRM write task should provide the remaining write-path evidence.
- Current external authentication blockers remain #240 and #250. #402, #426 and #474 are complete.

## Reconciliation 2026-10-04 - main ruleset
- GitHub main protection #474 is complete. Repository ruleset `Protect main - human release` is active on the default branch with no bypass actors, pull-request-only updates, deletion/non-fast-forward protection, and required GitHub Actions checks `test` and `factory-acceptance`.
- `strict_required_status_checks_policy=false` is intentional to avoid unnecessary merge-queue churn while still binding required checks to the exact PR head.
- The Factory runtime/GitHub adapter still has no merge capability. Production merge remains a human action; docs/non-production merges may still be performed by the orchestrator only after applicable gates are green.
- Remaining external/authentication blockers are #240 (Codex workspace WIF enablement/real federation values) and #250 (OpenAI API WIF mapping hardening). Supabase Leaked Password Protection is paid-plan hardening, not a technical blocker on Free.

## Reconciliation 2026-10-04
- Factory `main` is `c1e003ad8a6f7cf0192c6ec65e95d31ec9c651fe` after the human merge of PR #633. The production Vercel deployment for this merge is being observed separately; do not infer release success from the merge alone.
- The recent Console continuation flow is now complete through private evidence handling: PR #627 added attachments to ongoing-project requests; PR #629 surfaced the latest request context; PR #631 added authenticated server-side download without exposing Storage paths; PR #633 added bounded durable request history backed by `project.continuation.requested` audit events.
- The Factory repository has no open implementation PR at this checkpoint. The Control Plane reconciliation immediately before this update showed the Factory and CRM with zero open tasks, zero open runs and zero pending human gates.
- CRM Infodive is active in lifecycle `operations`, with no open GitHub PRs/issues at the checkpoint. Its current `main` is `23b4992727adb768a7a5b513cd0a181ea5d1e2d5`; Vercel reports success for that commit. The latest CRM operational change limits Preview creation to final candidates, reducing unnecessary deployment consumption.
- The Factory core lifecycle, deterministic routing, Direct execution, multi-agent planning, quality/eval gates, exact Preview, human production release boundary, release observation, Control Plane and Console are implemented. Remaining work is primarily operational hardening, finalization and external/admin enablement rather than a missing core orchestration stage.
- External/admin blockers remain #240 (Codex workspace WIF enablement and real federation values), #250 (OpenAI API WIF mapping hardening), #474 (main protection/ruleset), and Supabase leaked-password protection. Issue #426 is closed: GitHub-hosted Actions are healthy again with the repository private. None of the remaining blockers may be bypassed by invented credentials, permissive RLS or automatic purchases.
- Production merge remains exclusively human. The runtime and GitHub adapter must not gain automatic merge capability. The 63-question SQL Agent benchmark remains explicitly postponed.

# Current status

Last reconciled: 2026-10-02.

## Reconciliation 2026-10-02

- Factory `main` is `676bb31be41f2563ae56d0f2dc1d01eb9faea86c` after the autonomous non-production merge of PR #597. That fix changed only Preview workflow/tests/docs, so it did not publish the Console to production.
- PR #597 fixed the first-candidate Preview defect found during #595 dogfood: a new `preview/pr-<n>` ref is seeded at the candidate parent and then advanced to the exact candidate so the Vercel Git integration receives a real ref update. The recovery experiment and the next #595 cycle both produced Vercel `success` plus `Factory Preview browser evidence=success`.
- GitHub App `infodive-ai-product-factory` is registered in the Control Plane. Its private key and client secret are stored server-side in Supabase Vault; no repository installation was created silently.
- CRM Infodive is reconciled to lifecycle `operations` with repository head `23b4992727adb768a7a5b513cd0a181ea5d1e2d5`. Its cross-repository GitHub access remains `fine_grained_pat/partial` until the new GitHub App is installed and verified for that exact repository.
- Agente SQL Financeiro remains at `planning`, with GitHub access blocked and the 63-question benchmark explicitly postponed. No GitHub App access has been granted to it.
- PR #595 (`09ae4f51d5bf5c3eaa6e639eca74e54990cfdec1`) is technically ready: `validate`, `factory-acceptance`, `Console validation`, exact Vercel Preview, automatic promotion and exact browser evidence are green. Because it changes `apps/console/**`, its merge is a production gate and remains a human action.
- PR #599 (`624dc9d61d1032d38158b407574d83b1f1b1e3e1`) prepares GitHub App Phase 3 in the Python runtime. CI and factory-acceptance are green, but release remains intentionally blocked until a real CRM installation is verified. The design mints short-lived installation tokens restricted to the verified `repository_id`; same-repo work keeps native `GITHUB_TOKEN`, unmigrated projects may still use explicit PAT fallback, and a project already marked `github_app` fails closed instead of silently falling back.
- Control Plane currently has no pending human gate rows; the GitHub App registration state itself is registered and repository installation remains the next real human access-expansion action after #595 reaches production.
- External/admin blockers remain Codex workspace WIF enablement/real federation values (#240), OpenAI API WIF mapping (#250), main-protection/ruleset hardening (#474), future private-repository revalidation (#426), and Supabase leaked-password protection.
- Production merge remains human-gated. The Factory runtime still has no automatic merge capability and repository auto-merge remains disabled.

## Reconciliation 2026-10-01

- `main`: `582322059cf564a454c8e7c9cdfda262bbe2459a` after human merge of PR #514.
- No open pull requests were present at reconciliation time.
- GitHub Actions is healthy while the repository remains public: `validate` run `36859817890` and `Console validation` run `36859817834` both succeeded on the current `main`. Issue #426 is therefore not an active Actions incident; it remains the administrative revalidation gate for the future GitHub Pro/private transition.
- Console production deployment `dpl_59HGsseu5UdcXFZip4dPFW7VeMgc` is `READY` for the exact current `main`; `GET /api/health` returned HTTP 200 with commit `582322059cf5`, and Vercel reported zero runtime errors in the checked six-hour window.
- Control Plane project `fjplmxfcshhbmzgvyqlm` is `ACTIVE_HEALTHY`: 3 active projects, 0 open runs, 0 actionable failed runs, 0 pending human gates, 13 Codex routing rows with 0 actual Codex invocations, 1 active Console operator, and known cumulative tool/model cost US$ 0.3478338.
- Supabase security advisor still reports the intentional fail-closed `RLS Enabled No Policy` findings plus the plan-gated `Leaked Password Protection Disabled` warning (Pro+; not a technical blocker on Free). Do not add permissive public policies.
- UX umbrella #483 is completed and closed. The delivered sequence #491/#492/#494/#496/#498/#500/#502/#504/#506/#508/#510/#512/#514 materially satisfies the guided-flow, legibility, mobile, accessibility and gate-feedback acceptance criteria. Do not reopen the umbrella for cosmetic iteration without a concrete regression.
- Issues #512, #513 and #514 are closed/merged/released and must not be revisited in the normal work loop.
- External/admin blockers remain #240 (Codex workspace WIF enablement/real federation values), #250 (OpenAI API WIF mapping), #474 (main protection/ruleset), #426 (private-repository revalidation after plan change), and the Supabase leaked-password hardening control.
- Production merge remains human-gated. The Factory runtime still has no automatic merge capability and repository `allow_auto_merge=false`.

## Reconciliation 2026-09-30

- `main`: `9f85c1129986c247645fa8edad7578fb779732e9` after PR #467. The commits after the last Console code release are runtime/observability/test changes; the currently served Console production application remains the verified PR #440 release at `6353ff595338100d5c68ae4f984f5b4508ba259f`, and Vercel correctly cancels later production builds when `apps/console/**` is unchanged.
- Vercel production deployment `dpl_CgQJ6zyubHBnteAgmsi8au4wKZQ5` is READY for Console commit `6353ff595338100d5c68ae4f984f5b4508ba259f`; Vercel reported no runtime errors in the verified post-release window.
- Console interaction audit #433 is complete. Authenticated evidence run `36703504585` targeted the exact production commit `6353ff595338100d5c68ae4f984f5b4508ba259f`: all primary navigation routes returned HTTP 200, operator RBAC correctly redirected `/admin/operators` to `/unauthorized`, Novo Projeto -> Revisao -> Editar restored values without starting Discovery, CRM project detail loaded, and 390px mobile checks had no horizontal overflow.
- Runtime ledger/OIDC fix #438 and end-to-end delivery metrics #432 are released on `main`. Paid-ledger access through the GitHub OIDC broker now sends Bearer authentication while modern `sb_secret_*` credentials remain apikey-only.
- Dogfood #430 is complete. The Factory produced a real two-wave Direct change set for durable schedule-probe telemetry, reached green CI plus Security/QA/Operations review, recorded Preview as explicitly not applicable, stopped at `awaiting_release`, and the release observer recorded the human merge of PR #464 at `4fff56e258084e7461a15402e49b0168caee4ea7`. The issue is closed with durable release evidence.
- The paid ledger currently has known cumulative cost US$ 0.3478338 and zero unknown paid-cost events. Factory budget remains US$ 4.00 with US$ 0.50 reservation per paid run/call.
- Native retry for terminal failed runs is released. PR #466 added the fail-closed `factory_retry_failed_run` RPC, `runtime --mode retry`, immutable source-run history and durable `run.retry_queued` audit evidence; production migration `factory_retry_failed_run` is applied and issue #443 is closed.
- CRM Supabase OAuth is complete and remains fail-closed/read-only: project ref `mpmhmjepmmpxbsmekldf`, `status=ready_read`, `access_mode=oauth`, `permission_mode=read`. Issue #338 is closed.
- Cross-repository CRM access is configured with explicit `FACTORY_GITHUB_TOKEN`; read-only permissions remain intentionally scoped to `crm-infodive`. Issue #326 is closed.
- The Factory repository remains temporarily public while issue #426 waits for the planned GitHub Pro upgrade and final private-repository revalidation. Do not purchase or change plan automatically.
- Schedule-probe optimization #427 and durable telemetry #430 are released. The probe now records sanitized `work_detected` / `work_classes` observations in the existing audit store without creating a new schema or changing dispatch semantics.
- Next.js 15.5.27 is still not published in npm as of the latest 2026-09-30 check; 15.5.26 remains the 15.5 backport tag. Issue #402 remains open; do not use beta/canary.
- OpenAI API WIF #250 and Codex workspace auth #240 remain external hardening/enablement items; the operational Primary path remains the bounded API-key path.
- GitHub Actions same-repository PR creation is now verified: issue #463 was closed after the runtime adapter created disposable PR #465 with the native `GITHUB_TOKEN`; the probe PR was closed without merge and repository `allow_auto_merge=false` remains unchanged.
- Operational failed-run alerting now counts only actionable failures (failed run whose current task is still failed). After PR #467 the Control Plane has 6 historical failed runs, 0 actionable failed runs and 0 dead letters; issue #461 is closed.
- Control Plane reconciliation: 3 active projects, 0 open runs, 0 actionable failed runs, 0 pending human gates, 13 Codex routing-decision rows but `sum(invocation_count)=0`, and known paid cost US$ 0.3478338.
- OpenAI Support case 15851318 confirmed the supported Codex WIF model (GitHub OIDC, short-lived credentials, managed-workspace principal) but did not confirm that WIF is enabled for the Infodive ChatGPT Business workspace. Issue #240 therefore remains externally blocked; no federation rule ID or audience may be invented.


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
- current served Console production commit: `6353ff595338100d5c68ae4f984f5b4508ba259f` from human-merged PR #440;
- Vercel production deployment `dpl_CgQJ6zyubHBnteAgmsi8au4wKZQ5` is `READY`;
- post-merge `validate` run `36700177302` and `Console validation` run `36700177080` succeeded for #440;
- authenticated production interaction evidence run `36703504585` succeeded against exact target commit `6353ff595338100d5c68ae4f984f5b4508ba259f`;
- the authenticated audit captured overview, projects, runs, new-project, gates, run detail, queue, agents, orchestration, evals, deployments, usage, audit and configuration;
- all audited navigation routes returned HTTP 200; operator-only administration failed closed for the ephemeral operator; intake Review/Edit preserved values; CRM detail loaded; mobile widths remained 390px without horizontal overflow;
- bootstrap diagnostics reported zero console errors, zero page errors and zero bad responses;
- Vercel reported no runtime errors in the verification window;
- Supabase Auth login and server-side Control Plane access remain operational; backend access continues to prefer `SUPABASE_SECRET_KEY` with legacy service-role fallback only;
- `main` may be ahead of the served Console commit when later commits touch only runtime, docs, tests or evidence metadata and Vercel correctly skips/cancels unnecessary Console builds.

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
- the Supabase security advisor still reports only the intentional fail-closed RLS-without-public-policy findings plus the plan-gated `Leaked Password Protection Disabled` warning (Pro+; not a technical blocker on Free);
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
- Supabase security advisor reports only the intentional RLS-without-public-policy informational findings plus the plan-gated Leaked Password Protection warning (Pro+; not a technical blocker on Free);
- performance advisor reports only currently-unused indexes; no index is removed solely from this short observation window.

The authenticated Figma correction in #309 is now visually complete on the
current consolidated Console candidate. PR #407 head
`711e50acc8c93f3f46fa729845e149b444e87d8a` has exact Vercel Preview
`dpl_4svzTt3EPikybj24CnrjEUwVLaeN` in READY state and authenticated visual
evidence run `36607077404` passed capture, encryption, upload and cleanup.
The captured manifest records 11/11 routes with HTTP 200 and zero application
console errors, page errors or bad responses. The remaining #309 acceptance
item is the human production release plus post-release observation; no
auto-merge is authorized. Trusted Source access issue #412 is completed.
Dependency hardening #402 remains open for Next.js 15.5.27 revalidation when
that upstream release is available.


## Secret-presence audit on 2026-09-29

- GitHub Actions repo/environment audit exposed presence only, never secret values.
- `OPENAI_API_KEY` is present and the scheduled runner reports primary auth as `openai_api_key` with the paid-primary budget controls active.
- `FACTORY_GITHUB_TOKEN` is absent in repository scope, `openai-api`, and `openai-codex`; CRM cross-repo remains blocked on that explicit credential.
- `VERCEL_TOKEN` is absent, intentionally non-blocking for the Factory default GitHub/Vercel preview path.
- Control Plane access does not require a persistent GitHub Supabase key: GitHub OIDC successfully mints the short-lived runtime credential.
- Vercel Console environment has `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY`, `FACTORY_BOOTSTRAP_ADMIN_EMAIL`, `SUPABASE_OAUTH_CLIENT_ID`, and `SUPABASE_OAUTH_CLIENT_SECRET` present. Legacy `SUPABASE_SERVICE_ROLE_KEY` is absent and not required.
- Supabase Vault currently contains no stored secrets, which is expected before the first project OAuth authorization persists access/refresh tokens.
- OpenAI API WIF identifiers/audience are present in `openai-api`; the API-WIF blocker is mapping validation, not a missing secret.
- Codex workspace auth remains unconfigured: no federation rule/audience in `openai-codex` and no official access-token credential; Codex automatic execution remains fail-closed.


## Supabase OAuth production initiation recheck

- Vercel already has `SUPABASE_OAUTH_CLIENT_ID` and `SUPABASE_OAUTH_CLIENT_SECRET`.
- The authenticated CRM project detail renders the `Conectar Supabase` action for database binding `5086d662-42eb-43a6-a8da-0da59cb39d75`, whose expected project ref `mpmhmjepmmpxbsmekldf` matches the CRM repository.
- The official visual-evidence broker intentionally provisions role `operator`; the OAuth connect route requires `requireConsoleAdmin()`. An automated operator therefore cannot cross the admin gate, and the Factory did not weaken that boundary just for testing.
- Audit run `36633088137` was cleaned/expired; normal authenticated evidence run `36633521570` subsequently passed and was recorded as `captured`; zero ephemeral visual operators remain.
- The only remaining OAuth activation step is interactive admin consent in the production Console, followed by the built-in project identity and read-only database verification.
