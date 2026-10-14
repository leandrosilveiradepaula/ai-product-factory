## 14/10/2026 — Confirmacao pos-merge das correcoes de operacao

- PR #806 mergeado em `2c604bec`: o alerta `scheduler_pipeline` foi exercitado pela reconciliacao `/factory-alerts` (run `38628800312` SUCCESS); issue #809 foi aberta pelo bot, pois run agendado #38619635786 concluiu FAILURE. `scheduler_gap` (heartbeat) estar fechado nao equivale a pipeline recuperado.
- PR #807 mergeado em `10016635`: CI de push `38629927087` SUCCESS; issue #804 encerrada. Scan paginado de `factory_runs` e leitura em lotes sao codigo de producao, mas **nenhuma validacao com mais de 200 runs reais** foi feita: o banco possui 81. Regressao simulada no CI cobre >200.
- Para o proximo ciclo, confirmar duas `schedule` de `autonomous-runner.yml` nativas, consecutivas, com `conclusion=success`, antes de fechar #809. Rerun, `workflow_dispatch`, issue_comment e OIDC backup nao contam. Nao criar trabalhos falsos, creditos de API nem redeploy do Vercel.
- Ao testar #786, conferir SHA exato e sinais READY + browser, sem reutilizar URLs antigos. A migration RPC ja esta aplicada; evitar executa-la novamente. Publicacao de producao exige gate humano.
- O diagnostico de custos/saude nao concede permissao para dispatch ou calls pagas.

## Operational runs: complete bounded read, no false healthy totals (2026-10-14 candidate #804)

\`SupabaseOperationalHealthReader\` must not infer the current number of failed, dead-letter, or expired-lease incidents from the latest 200 \`factory_runs\` only. The run history now paginates in deterministic \`created_at desc,id desc\` order (200 records/page, up to 20 pages), validates unique run IDs and known statuses, and **raises an error** instead of reporting incomplete totals. The limit is intentional (4,000 runs): reaching it without observing the final short page fails closed. Failed-run parent task statuses are fetched in bounded 100-ID batches, preserving the rule that recovered/completed tasks suppress obsolete historical failure warnings. Independently partitioned Preview and usage-ledger scans keep their earlier rules.

\`offset\` pagination is not a transactional snapshot. Concurrent inserts/deletes can move boundaries; overlapping IDs or inverted timestamp order are detected and rejected. Missing rows caused by concurrent shifting that produce no duplicate cannot be ruled out by offset scans: for immutable complete historical accounting at much higher volume, use a privileged transactional snapshot/keyset pagination strategy in a separately reviewed change. Operational health is **observability**, never evidence authorizing paid-model calls, dispatch, or release. No production schema change, paid model usage, Console Preview, or new token permission is required.

Observed production on 2026-10-14: 81 total Factory runs, so the 200-row truncation was a latent growth hazard, not a live missing incident. Tests exercise 201+ histories with failed/expired/recovered incidents, duplicate IDs, invalid statuses/timestamps, batch lookup, and bounded overflow. Merge into production still requires the human gate; after human merge, verify scheduled alert evaluation against a read-only Control Plane snapshot.

## Native scheduler completion vs heartbeat (2026-10-14 candidate)

The existing \`scheduler_gap\` is a **delivery-cadence** warning derived from two native \`schedule_probe.native_observed\` events in Supabase. Those are emitted before alert evaluation; therefore they cannot prove the GitHub Actions workflow completed successfully. A manual \`/factory-alerts\` pass can legitimately clear the cadence warning while a preceding native workflow failed. Never claim an autonomous runner is end-to-end healthy on that basis alone.

\`scheduler_pipeline\` independently observes the GitHub Actions REST \`actions/runs?event=schedule\` inventory, filtering to \`.github/workflows/autonomous-runner.yml\` on the trusted \`main\` repository. It requires the **last two completed** native scheduled workflows to have \`conclusion=success\`, with the newest fresh (under 2 hours) and the completion observations within 2 hours. The currently running scheduled workflow is not considered complete; unrelated scheduled preflights, dispatches, owner comments and backup wakes never count. Read-only API errors or malformed results retain a warning and cannot silently resolve the issue. This uses the existing GitHub token/client and opens/closes only the existing deduplicated alert mechanism; no extra cron, workflow permissions, database migration, paid provider, or deployment is introduced.

After a human merge, a **real** scheduled runner must complete twice (at timely intervals) for pipeline health. Verify the GitHub Actions run IDs/conclusions independently; alert-only checks are evidence of the alert system, not the completion of the native runner. If the token cannot read the Actions inventory, investigate its existing permissions before making any access expansion. No automatic permission change is authorized by this patch.

## Hotfix: production BIGINT cost usage IDs (2026-10-14)
At native scheduled run [38619635786](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/38619635786) at 18:58 UTC, the alert step failed with `RuntimeError: cost usage inventory has invalid or duplicate ID` introduced by #803. The live schema proves `factory_tool_usage.id bigint NOT NULL` (identity sequence), so PostgREST returns the IDs as JSON numbers, whereas #803's read-only pagination erroneously required strings. Live SQL verified 97 distinct/non-null IDs; no corruption.
The reader now accepts signed-BIGINT-range **positive integer** JSON values or decimal-string forms and normalizes them to the same canonical ID before duplicate detection. It rejects booleans, floats, zero, negatives, malformed strings or out-of-range values. Existing cost pagination and fail-closed budget/ledger semantics remain unchanged. Tests use numeric IDs mirroring the production schema, include numeric-string cross-page duplicate detection and invalid boundary values.
The two genuine native scheduler heartbeat rows at 18:40:54Z and 18:58:22Z now meet the heartbeat timing threshold, but the second *whole run failed*. Scheduler recovery must not be declared operationally end-to-end until a successful alerts-only / real scheduled validation after this hotfix's human merge. No database migration, spending or Preview is needed.

## Complete operational cost observation and recovered dead-letter signal (2026-10-14)
The operational alerts reader formerly selected only the newest 1,000 `factory_tool_usage` rows and summed them as though they were the entire historical budget, potentially suppressing `budget_exhausted` and `unknown_cost` warnings when usage exceeded the page. It now retrieves deterministic 1,000-row pages ordered by `created_at,id`, validates unique row IDs and nonnegative finite amounts, and refuses an incomplete inventory after a bounded 20-page limit. Partial or malformed observations are errors, never successful budget totals; underlying model-execution paid ledger and production purchase/authorization gates remain separate and unchanged. At verification, Supabase held 97 tool-use rows, so overflow was a future-safety bug, not an observed current budget breach.
The same reader previously counted historical failed runs with `maximum attempts` as dead-letter incidents after their tasks were recovered/completed. It now counts failed/dead-letter incidents only if the linked task remains failed, and it rejects incomplete failed-task lookup results. This preserves existing previews and has no database migration, model request, or dashboard code change.
Regression exercises >1,000 usage events including late unknown paid cost, duplication across pages, invalid/negative amount, recovered historical failure and missing task records. Read-only GETs with bounded paging; no changes to control-plane data.

## Backlog inventory — unknown Work Unit state fail-closed (14/10/2026)
The live PostgreSQL CHECK constraint `factory_change_set_work_units_status_check` enumerates exactly `pending, queued, running, completed, integrated, failed, blocked`. Prior to this hardening, the read-only inventory accepted *any string* as a unit status, counted it as not active and could report a completed-parent child as historically inactive even if the database contract had drifted or the response was corrupted.
The reader now rejects an unknown/missing/non-string Work Unit status with `RuntimeError`. The seven states allowed by the current database constraint retain their previous active/inactive classification and diagnostics. This does not mutate Work Units, change dispatch/claim permissions, infer queued-work eligibility, or require a migration. Tests cover every allowed state plus malformed/unexpected values. Keep this classifier distinct from the authoritative atomic planner/dispatcher.

## Queued children under completed parents: diagnostic visibility (14/10/2026)
The versioned migration `20261006023500_completed_parent_keeps_backlog.sql` explicitly restores queued children under a completed parent: completion can satisfy a dependency rather than terminate a child's backlog. The live read-only inspection found **10 queued children of completed parents**, of which **8 have no Work Unit** and **2 have integrated Work Units**, with zero active Work Units. The original backlog inventory labeled all ten historical, which is not sufficient evidence that all ten are ineligible for future materialization.
The inventory now preserves its existing summary fields for compatibility and exposes separate `completed_parent_without_work_units` and `completed_parent_with_inactive_work_units` counters. Unknown/non-terminal parent states, including `failed` and `merged` when no policy establishes task-level terminality, remain visible through `other_queued_without_active_units` and `unverified_parent_status_without_active_units`; malformed parent status fails closed. This is **read-only diagnostics**, not automatic dispatch, backlog reactivation, state repair, or proof that any child should execute. The actual source of dispatch eligibility remains the authoritative planned-work RPC and claims with human gates.
The prior #800 suggestion to simply add `failed/merged` to a terminal set was rejected after checking actual task statuses and the completed-parent migration: neither status currently appears in `factory_tasks`, and neither should silently suppress potential work without a separately reviewed lifecycle policy.

## Draft PR Preview observability (14/10/2026)
A Console validation on draft PR #795 triggered the automatic Preview promotion, but the resolver returned a red workflow for an intentional non-deployable draft. This is an *inapplicable candidate*, not a failed build. The resolver now emits `not_applicable_draft` only for a verified open, same-repository main-branch PR whose SHA matches the successful CI and whose trigger is automatic. It does not update Preview refs, call Vercel, consume quota or dispatch browser evidence. Explicit manual attempts still fail closed for drafts. Mark a Console PR ready for review only after policy permits real Preview and the provider rate limit is no longer observed. No UI/release success is inferred from green CI or from the draft skip.

## Preview rate-limit guard: recently closed PRs and superseding Vercel statuses
After PR #792 merged, the observer's initial version checked only open PR heads. A Vercel rate-limit failure could vanish from that inventory when a PR was merged or closed, and a newer Vercel success on the same SHA could otherwise be masked by historical failures. The guard now inventories open and recently closed PR heads within a rolling 24-hour window, reads bounded Vercel commit status history, and treats a newer verified success as superseding older failures on the same SHA. A pending state does not clear cooldown. Incomplete/truncated inventories, missing timestamps and invalid status history fail closed; no false assumption of quota availability is made.
This is an additional preventive signal, not an authoritative provider quota. A rewritten/superseded PR head from an earlier ref may still be missed; source-of-truth rate-limit data from Vercel or the Control Plane would be required to remove that limitation. No Vercel token, API purchases, Preview build, or production mutation is needed to test this change.

## Vercel Preview rate-limit observation cooldown (2026-10-14 candidate)
When GitHub receives a Vercel commit status such as `Deployment rate limited — retry in 24 hours`, new Preview promotions must not burn more attempts. The provider status is a negative signal, not a complete quota measurement. `scripts.preview_provider_cooldown` reads current open PR head statuses using GitHub REST before the existing budget observer: a recent exact Vercel rate-limit message blocks for a 24-hour observation window; unknown inventory, authorization and status errors fail closed. It does not require a Vercel token, buy credits, alter limits, write to Control Plane or disable browser evidence. After 24 hours the check may be retried, but a green GitHub preflight does **not** guarantee available Vercel quota. Scope: only open PR heads; a rate-limit on an already closed or superseded head may not be observed. The official Vercel API limit snapshot remains authoritative when configured, and no false quota confidence is inferred from negative signals alone. If the candidate's exact SHA is currently Vercel rate-limited, leave the release in draft/awaiting_release, not merged. The existing production human gate is unchanged.

## Verified release ordering after PR #789 (2026-10-14)
1. Review PR #787: manual and automated Preview dispatches must both verify exact open same-repository main PR head, non-draft and `apps/console/**` changes. PR #787 has green `validate` and Preview N/A because it changes only workflow/tests. Merge only via the human production gate; the runtime GitHub adapter has **no automatic merge capability**.
2. After the merge is observed and main CI reconciled, PR #789 may be marked ready for human review if its exact Vercel/Browser status remains successful. The candidate `a87cbb38...` has `Vercel=success` and `Factory Preview browser evidence=success` backed by trusted Actions workflows. A **human** then decides on the main merge; do not deploy any Preview simply to 'check again' when candidate evidence is already exact and green.
3. PR #786 remains draft until an operator explicitly approves and applies the versioned atomic-continuation migration in production, then verifies the RPC signature, `service_role`-only grants, shared project lock, and Supabase migration history. CI and Preview **cannot replace** database installation evidence.
4. Do not clear scheduler_gap issue #790 based on OIDC preflight, alert reconciler, manual dispatch, or the first recovered Cron event. Observe at least two timely consecutive native scheduled heartbeats and re-evaluate freshness. Treat a stale native scheduler as degraded autonomy even if overall CI is green.
5. The Vercel ignored-build step executes `sh ./vercel-ignore-build.sh` from the Console root; only `preview/pr-N` promoted refs are eligible for candidate builds. It compares against `VERCEL_GIT_PREVIOUS_SHA` when the previous SHA exists in the Git checkout; missing/unavailable history builds rather than claiming no change. Non-candidate Preview refs are skipped. The script's exit codes follow Vercel: 0 ignores; 1 builds. All rollout validation uses exact SHA and browser evidence; do not infer provider deployment from local tests.

## Atomic project continuation — deployment order (14/10/2026)
1. **Do not merge PR #786 while the production RPC is absent.** CI and a verified Vercel Preview do not apply SQL automatically. The candidate is deliberately a draft pending this administrative gate.
2. Human operator reviews `supabase/migrations/20261014160500_atomic_project_continuation.sql` at the exact candidate SHA, validates diff and applies it through the official privileged Supabase migration path with explicit production approval. No scheduler, agent or GitHub adapter may apply it.
3. Read-only production verification should confirm `to_regprocedure('public.factory_enqueue_project_continuation(text,text,uuid,integer)') is not null`, `FOR UPDATE` in `pg_get_functiondef('public.factory_enqueue_project_bootstrap(text)'::regprocedure)`, and restricted function EXECUTE grants to `service_role` only. Check Supabase migration history as well. Never claim deployed based solely on an API 200 or CI success.
4. **Only after step 3:** mark PR #786 ready for review, revalidate expected candidate SHA, CI, Preview/browser checks and release policy, then perform the human production merge. Verify Console health and a legitimate continuation run separately; no synthetic product tasks or paid model probes.
5. If the migration is not approved, leave PR #786 in draft; keep the current Console/Control Plane in place. If a response to an already submitted continuation is ambiguous, do not delete private files merely because HTTP returned 409/5xx or timed out; the request may be durably committed. The isolated PostgreSQL workflow checks same/different request races, transaction rollback, historical children, existing bootstrap race and service-only privileges.

## Do not clear scheduler gap after one cron event (candidate)
A native `schedule_probe.native_observed` record proves one successful GitHub schedule wake, **not a stable cadence**. The liveness contract now requires the two newest native records to both exist, the newest to be younger than two hours and their separation shorter than two hours before `scheduler_gap` can resolve. Old generic audit events and operator/backup `issue_comment`/`workflow_run` wakes never count. This intentionally preserves warnings after a cold start or prolonged outage until the second timely native wake.

Issue #772 was prematurely closed at 13:47:10 UTC on 14/10 after only the first native record; this was a logic bug, not proof of health. The GitHub alert adapter currently searches only open marked issues, so it may create a new numbered warning when the corrected reconciler first runs. Record linkage to #772 in that new issue; never close it based on just CI green or an owner manual wake. No changes to cron frequency, queue dispatch, Preview or human production gate.

## Scheduler native heartbeat provenance (candidate)
Use schedule_probe.native_observed for GitHub event_name=schedule only. A workflow_run fallback or manual operator wake records schedule_probe.observed, never proving the native cron healthy. A native heartbeat write failure fails that probe; backup telemetry may remain best effort. No schema changes. Verify live schedule and native DB event after human merge; do not close scheduler_gap on fallback-only success.

## Required CI and human-only DoD whitelist (candidate)
Candidate release readiness requires `github_ci` explicitly satisfied; absence of the key blocks even if the DoD lists are structurally valid. A missing item can be marked `human_only: true` only when its key is exactly `human_release`. Any other human-only claim is treated as an unauthorized attempt to waive a deterministic gate and blocks release. These rules supplement strict JSON booleans and duplicate/conflict validation. They do not themselves certify the CI run for a SHA; the evidence collector must still verify exact SHA check-runs and Preview as applicable. Even a legitimate candidate remains subject to the human production merge gate.

## Fail-closed Definition of Done inputs (candidate)
When preparing a release assessment, do **not** coerce `human_only` or allow untyped DoD `missing` entries to vanish. Only a literal JSON boolean `true` denotes a human-only item. Strings such as `"false"`/`"true"` and numeric flags are invalid and block release. Omitted or malformed `definition_of_done.satisfied` or `definition_of_done.missing` arrays, duplicate missing keys, invalid missing rows, and simultaneous satisfied/missing keys also block deterministically. A missing DoD must never be treated as evidence that all checks passed. Separately, the human production gate always applies, even when nonhuman checks are complete.

## Mandatory product-readiness domains and evidence format (candidate)
The product-wide readiness evaluator may only accept `product_experience=not_applicable` for documented headless workloads, never `security`, `observability_operations`, `test_strategy`, `documentation`, or `functional_completeness`. Every mandatory domain needs full required coverage and valid evidence. `evidence` and `coverage` values must be lists of strings; any non-string entry fails closed rather than being coerced into a bogus reference. The release reporter reuses this evaluator for the SHA-exact product assessment.

This deliberately does not authenticate arbitrary external evidence strings or claim complete product readiness in absence of verified evidence. All production merge/release gates and provider Preview policies remain separate, unchanged.

## Exact-candidate full product readiness in release reports (candidate)
Release reports must **not** treat `facts.product_readiness.ready=true` as a trusted completion verdict. `build_release_assessment` now revalidates the six `domains` using the same deterministic `assess_product_readiness` contract and requires `assessed_commit == candidate_commit`, a real `assessment_ref`, coverage/evidence/verification state, and no critical blockers. `baseline_ref` is historical context, not equivalent to an assessed candidate SHA. When evidence is missing or malformed, the report stays `readiness_scope=release_candidate` and `product_complete=false`; no release outcome or human production gate is changed. In particular, Preview or CI for a single PR never constitutes a whole-product assessment.

## Conditional backup alert observer via OIDC preflight (candidate)
Scheduled GitHub Actions events can be delayed/dropped under load even with off-hour-minute Cron entries; no code-only change can guarantee cron delivery. The existing `control-plane-oidc-preflight.yml` runs every six hours and is an independent workflow file in the **same GitHub provider** (not a separate infrastructure scheduler). It now probes durable `schedule_probe.observed` timestamps read-only after its usual authenticated Control Plane check. Only if the existing `scheduler_gap` predicate is true does an alerts-only job start, authenticating via protected OIDC with read-only contents, OIDC token minting, and scoped GitHub issue write. No model, Codex or cross-repo credentials are injected; this fallback must not dispatch implementation work.

Investigate issue #772 and schedule delivery using GitHub Actions run history (event=`schedule`) against the Supabase timestamps. The `scheduler_gap` issue may stay open after a manual wake: do not treat manual calls as proof the native Cron is healthy. If an actual independent scheduler is required, the production Supabase project currently lacks `pg_cron` and `pg_net`; enabling it and furnishing a supported, scoped GitHub App/token for `workflow_dispatch` are separate infrastructure/access decisions requiring authorization. This candidate does not enable any extension, create recurring paid execution, or add cron frequency.

## Owner-only alerts wake without dispatch (candidate)
When scheduled GitHub Actions wakes are delayed, the safe recovery command is a *GitHub issue comment* containing exactly `/factory-alerts`, authored by the repository OWNER. It deliberately does not reuse `/factory-wake`, which can run the scheduler, recovery and executor lanes. A PR comment, a non-owner comment, altered/mixed command text, or an issue edit must not start the alerts job.

`alerts-owner-comment` independently checks out main, installs the pinned Python runtime, obtains protected Control Plane access via OIDC, validates availability fail-closed, and invokes only `python -m ai_product_factory.runtime_cli --mode alerts`. It gets only `contents:read`, `id-token:write` and `issues:write`; neither model nor Codex secrets are passed. Alert deduplication/reconciliation still depends on authoritative live DB data. Verify the workflow run and resolved GitHub issues after dispatch; never infer success from posting a comment alone.

This GitHub-hosted operator hook is not independent monitoring if GitHub Actions itself cannot start jobs. Production release, cost, auth and Preview gates remain unchanged.

## Scheduler wake-gap alerting (candidate)
Operational alerts now include `scheduler_gap` from the durable Control Plane `schedule_probe.observed` timestamps. The read-only health check inspects the newest two entries; a latest probe age >=2 hours or a separation >=2 hours raises a deduplicated warning. Missing evidence also warns. It uses normal alert issue marker/closing reconciliation and does not disclose credentials.

**Limitation:** GitHub cron is best-effort; if GitHub never schedules the Factory, this in-run detector cannot emit an alert until another scheduled or owner-triggered alerts-only run executes. This is not independent uptime monitoring and does not constitute a guaranteed wake SLA. Do not compensate by adding paid services, noisy deployments, or production work. Investigate the schedule itself and consider an independent, approved monitoring channel if a wake SLA becomes a requirement.

## Read-only queued backlog audit (candidate)
When `schedule-probe` reports no executable work, it does NOT imply all `factory_tasks` are terminal. Historical planning child tasks may remain `queued` under completed parents with no active `factory_change_set_work_units`. Use `python -m ai_product_factory.runtime_cli --mode backlog-audit` for an explicitly read-only report, or inspect its best-effort scheduled log when `work_detected=false`.

The reader uses only GET queries with bounded rows (100 queued tasks, 500 work units), validates all identities and parent references and fails closed rather than misreporting partial data. It does not promote tasks, create runs, claim work, contact a model, or infer human release approval. A queued task with active unit is still not necessarily dispatchable: only authoritative scheduler/claim gates decide. No schema migration is needed.

## Stale Preview alert provenance (candidate)
The operational health reader now separates real overdue delivery candidates from historic product-readiness audit rows (`metadata.source=dogfood_manual_audit`) using the same `is_delivery_preview_run` rule as the Preview queue. It reads an oldest-first `preview_ready` partition, not the newest 200 general runs. An overflow >200, malformed row or missing delivery timestamp fails closed before the alert reconciler can incorrectly close an issue. This does not change run status, queue scheduling, quota, or Preview/production gate rules.

Post-merge, the existing `alerts` runtime can reconcile issue #754 when the current Control Plane reports no actionable overdue deliveries; no manual reset or invented Preview evidence is needed.

## Agent scope race prevention (candidate)
The follow-up migration `20261014092500_serialize_agent_scope_claims.sql` is **not installed until human release gate**. Agent-row `FOR UPDATE` locks alone cannot protect a scope hierarchy across two independently assigned agents. A transaction-scoped PostgreSQL advisory lock by project serializes the final scope-conflict query and insert inside `factory_claim_agent_slot`; no persistent lock row or new privileges are introduced. An empty scope array does not require project serialization. Per-run/per-agent protections still operate independently.

The dedicated `Codex PostgreSQL claims` workflow now loads the real versioned functions `factory_claim_agent_slot` and `factory_schedule_run_agent` instead of a simulated allocator. The test fixture schema is isolated and simplified, but concurrent PostgreSQL transactions exercise the same SQL bodies. Do not apply this migration or report production race protection until the merged SHA is confirmed and the official Supabase migration tool verifies function body and ACL afterward.

## Real PostgreSQL regression for Codex claim isolation (candidate)
Run `scripts/verify_codex_claim_postgres.py` only in the dedicated `factory_codex_claim_test` database on loopback with `FACTORY_CODEX_PG_TEST_ISOLATED=true`; the integration harness fails closed otherwise. The `Codex PostgreSQL claims` workflow provisions ephemeral Postgres 16 on GitHub Actions, installs the pinned psycopg client, and executes the exact versioned manual/automatic claim, scheduler and work-matrix functions in concurrent transactions. It never accesses the production Supabase project, calls Codex or grants new production permissions.

The generic agent allocator is represented by a minimal fixture, NOT by the real `factory_schedule_run_agent` function. Hence the suite proves mode-aware claim row-lock behavior and related route filters, not scope-lock/capacity allocator correctness. Existing RLS and cost/auth gates remain separate. Do not report full Codex end-to-end until protected auth, paid ledger, real task, PR/CI and human release observer are verified.

## Codex automatic agent claim hardening (candidate)
The follow-up SQL migration `20261014032600_codex_claim_agent_hardening.sql` is **not** installed yet. It requires both `codex` and `github_write` tools when choosing, advertising or claiming an automatic Codex agent. Scheduling rejects a mismatched agent returned by the generic role-aware allocator transactionally. The claimer rechecks exact agent key, task capabilities, active project and queued Work Unit with row locks and checks assignment update success. Python consumers also reject mismatched run/agent IDs. This adds defense in depth but **does not** prove simultaneous claim behavior without an isolated multi-transaction integration test. No synthetic work is created in the production Control Plane; official Codex auth, paid ledger and human release gates remain unchanged.

## Codex mode isolation (candidate)
New Codex runs are stamped manual/automatic in one transaction; both claimers filter exact mode. Untagged historical runs fail closed. Automatic Codex scheduling uses Codex-capable agents only and the exact run ID. Activation needs protected Codex auth and FACTORY_CODEX_COST_APPROVED=true; this variable remains off until cost entitlement and real ledger approval. Migration 20261014015500_codex_atomic_mode_isolation.sql was applied via the official Supabase migration tool after human PR #763 merge and verified against pg_proc ACLs; `codex_atomic_mode_isolation` is recorded in history. No automatic production merge.

## Codex routing safety: mandatory durable execution-mode isolation

The protected Codex route preflight added in PR #760 proves presence of
configuration only. It must **not** enable automatic Codex claims by itself.
The legacy `factory_claim_next_manual_codex_handoff` RPC currently accepts
every queued Codex run without checking an execution-mode discriminator.
Automatic Codex dispatcher/worker therefore cannot safely coexist with
the manual handoff consumer, even if the automatic worker is configured.
New automatic claims are temporarily fail-closed; explicitly enabled manual
handoffs are unchanged.

Activation requires a follow-up **atomic Control Plane migration**: stamp
`manual` or `automatic` in the same transaction that routes the run;
enforce that stamp in both automatic and manual claim RPCs; assign the exact
newly routed automatic run (not an unrelated queued run); and test both
concurrent claims in isolated transactions. Do not enable automatic Codex
until the migration is installed, CI and preview requirements satisfied and
official login/ledger gates approved. Never workaround by automatically
merging production.

## Independent Codex preclaim readiness and official access token fallback

The protected `openai-codex` workflow now exposes a strict boolean route
preflight to dispatch only when actual routed work exists and Codex is
explicitly enabled. It requires a complete official WIF federation mapping
or a configured `CODEX_ACCESS_TOKEN`, plus an explicit cross-repository
GitHub credential. Partial WIF rejects token fallback; secrets NEVER reach
the dispatcher or the Primary jobs.

This is a **configuration preflight**, not an official Codex login success:
the `codex` worker rechecks WIF/token, attempts the official auth mode and
fails closed before any model invocation if credentials are invalid.
Activation still requires a prior no-model auth validation recorded by an
operator; do not flip `FACTORY_CODEX_ENABLED` merely because a secret
exists. No token values or invented federation settings belong in docs.

Automatic Codex route authorization is independent from Primary budget or
API key. If Primary is disabled but Codex is explicitly active and protected
preflight passes, only Codex may be claimed. If neither route is available,
work remains unclaimed. The manual Codex path remains separate and
explicitly opt-in when automatic Codex is off. No auto-merge or Preview
policy is changed.

## Downstream stage wakeup without REST-window starvation

`factory_scheduler_queue_signals` now also uses read-only PostgreSQL
`EXISTS` for Change Set integration, CI follow-up, human release observation,
and queued specialist security/QA/operations work. These signals are
independent of 200/400-row history windows. Terminal specialist lanes never
wake a worker. Strict nine-boolean response validation fails closed when
the RPC is not yet deployed.

Preview retains its separate SHA, origin and quota policy. Direct/Primary
auth, Codex WIF, ledger/cost and human merge gates remain unchanged.
Deploy migration `20261014001500_extend_scheduler_queue_signals.sql`
after CI and human merge, and verify ACLs and empty-queue signals.

## Authoritative queue wakeup signals

The status-window scan is diagnostic only. The `factory_scheduler_queue_signals`
read-only, stable, security-invoker, service-role-only RPC uses indexed
PostgreSQL EXISTS/joins to detect genuine product runs, routed Direct/Codex
runs and pending manual Codex followups independent of legacy queue volume.
The query checks active projects and task/run state. New Work Units still
require the existing eligible portfolio RPC. This avoids false idle when
a genuine run falls between oldest/newest REST windows.

The scheduler fails closed if the RPC is missing, malformed or inaccessible;
do **not** treat that state as successful idle. Therefore
`20261013235000_scheduler_queue_signals.sql` must be applied and ACL-tested
immediately after a human merge, before depending on a production schedule.
Preview eligibility, quota, model/ledger gates and human release gates stay
unchanged. This is queue detection only, not paid-model authorization.

## Bounded queue join and newest-run fairness

When a run status partition reaches 200, the read-only probe samples **both**
the oldest and newest 200 rows for that status. This prevents a historical
manual-preview backlog from hiding new delivery work while retaining old FIFO
work. Because the task status partitions are bounded independently from runs,
the probe also resolves missing run/task references through batched exact
PostgREST task-ID lookups (40 IDs/request, 400 additional IDs maximum).
Identifier format and row membership are validated before use. A malformed
server response fails closed; all requests remain read-only and zero-model.

Audit diagnostics report capped status partitions and linked-task lookup
truncation so the system never claims exhaustive queue coverage beyond these
hard limits. Only a transactionally eligible Change Set wakes new dispatch,
and Preview still uses its source/sha/quota policy. This is not a replacement
for a future SQL-indexed existence RPC if one status exceeds these bounds.

## Status-partitioned work detection after recovery

The autonomous runner's read-only schedule probe used to fetch the oldest 200
runs across *all* statuses and 200 tasks across two statuses. Historical
Preview/audit rows could therefore hide newly queued Direct/ Codex work, and
legacy queued tasks could hide an active queued_execution task. The probe now
reads each status in an independently bounded 200-row partition, retaining
per-status caps in audit diagnostics and de-duplicating IDs by the latest
observed status if a transition happens while probing.

This affects only wakeup detection, not claim authorization. A pending Work Unit
still requires a real eligible portfolio candidate. Manual Preview audit rows
never cause deployment. A queued execution wakes the dispatcher, which still
checks executor readiness and the known-cost ledger before creating any new
assignment. Status partitions at the 200 cap are diagnostic evidence of possible
further backlog; do not claim complete coverage beyond that bound. No changes
to human merge gates, Primary activation or Codex WIF.

## Fail-closed recovery and route-isolated workers
The recovery job can requeue expired runs, resume decisions and release expired agent slots, but **must not allocate a new agent**. Generic `factory_schedule_next_unassigned_run` can select Codex manual or Direct work while its executor is disabled. Direct allocation is handled only by dispatch after Primary auth, real budget and ledger checks, through `factory_schedule_eligible_direct_run`.

When a Direct/Codex worker starts without an exact run ID, it may read only the durable existing assignments for its own route using `factory_agent_work_matrix`. It must not call the generic scheduler or implicitly create a new assignment. Missing assignments produce `empty`. Neither operation activates Codex WIF or Primary, requeues historical work, or authorizes a production merge.

## Route-safe Direct scheduling and post-gate recovery (PR #753 extension)

The versioned `factory_schedule_eligible_direct_run` RPC assigns only an
active project's Direct run when its run is `queued`, task is
`queued_execution`, and no assigned/claimed agent slot exists. It uses
row locks and passes the persisted agent role, capabilities and scope keys
to the existing capacity/scope-checked allocator. An explicit run ID
schedules a freshly claimed Direct candidate; a null run ID safely resumes
previously queued Direct work after human approval or agent-capacity recovery.
No Codex manual work may be scheduled by this RPC.

Python skips agent assignment for all `human_gate_required` runs and only
drains unassigned Direct work when Primary auth and the paid ledger have
passed the existing fail-closed gate. If Primary is disabled, it leaves
approved Direct work queued without consuming slots. Owner issue-comment
wakes can prepare independently enabled Codex manual handoffs.

Migration `20261013224500_schedule_eligible_direct_run.sql` must be applied
only after CI and human merge; until then the new RPC fails closed. No paid
model smoke or fabricated product task is authorized by these tests.

## Agent slots after atomic dispatch

The dispatcher must schedule the **exact run ID** returned by the atomic
route-aware claim. It must not call the global schedule-next RPC immediately
after a new claim, because that RPC can assign an unrelated older run.

Manual Codex handoffs are an intentionally unstaffed waiting state:
when the selected and approved route is Codex manual, no agent slot is
reserved. The dispatcher includes the claimed Codex route in its durable
output; the workflow uses that signal to wake the manual Codex prepare job
without requiring a work-matrix agent assignment. A Direct route still
receives an agent assignment by exact run ID and the planned preferred agent
key when specified. Empty/malformed claim IDs fail closed.

Previously assigned in-flight work and recovery remain separate concerns;
this patch does not requeue historical runs, enable Codex WIF, purchase
model credit, create Previews, or alter the production release gate.

## Manual Codex handoff — explicit opt-in and issue provenance

A **new** manual Codex handoff may be claimed only when
`FACTORY_CODEX_ENABLED` is not enabled and
`FACTORY_CODEX_MANUAL_FALLBACK_ENABLED` is explicitly the exact value
`true`. An unset, empty or malformed flag is **disabled** in both the
GitHub Actions prepare step and the Python worker. The dispatcher has the same
strict default-off rule. This avoids accidentally claiming a task that would
need a human Codex operator.

For a pre-existing handoff the read-only PR-followup path remains usable even
if the opt-in flag has since been disabled; no new handoff is claimed during
followup. Before marking any new handoff `awaiting_codex_manual`, the worker
confirms the Issue's body contains the exact Factory run marker and, when an
Issue was previously bound, the Issue number still matches. A mismatch aborts
before persisting a new binding or transitioning the run.

This is a human **implementation handoff**, not proof of autonomous Codex WIF
execution or a license for automatic merges. Do not enable manual fallback
solely to manufacture an E2E test or reactivate old plan tasks.

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

## Atomic route-aware dispatch (candidate; requires migration)

The pending Work Unit can be *peeked* without side effects. Python decides
Direct vs Codex using the existing deterministic router, then calls a single
new transactional RPC with the exact Work Unit ID, a 32-character fingerprint
of the task/unit/Change Set, and the routing decision. The RPC locks and
rechecks the latest ready plan, task/unit state, current wave and fingerprint
before creating the run. It records the route, audit and human execution
gate in the same PostgreSQL transaction. A mismatch aborts the claim; there
is no fallback to the blind claim RPC, whose service_role grant is revoked.

New Direct claims require the protected Primary API readiness boolean and
known-cost budget checks. New Codex claims are independent of Primary only
when the existing manual Codex fallback is **explicitly** enabled by the
corresponding repository variable, automatic Codex is off, and the derived
dispatch readiness signal matches. This is a manual handoff, not an automatic
Codex entitlement or a new production gate. Automatic Codex remains unavailable
for new claims until official WIF/token readiness is proved. No Codex or
OpenAI credential is passed into the dispatcher.

Versioned migration `20261013220500_route_aware_atomic_dispatch.sql` must
be applied in a controlled deployment after merge. Between merging code and
applying the migration, new dispatches fail closed (the new RPCs do not yet
exist); no historical work is reactivated. Verify first with a truly new,
bounded task; zero pending units alone is not a real end-to-end test.
## Preclaim executor readiness for planned Work Units

The dispatcher cannot turn a pending Work Unit into a run unless a real executor
is configured. The product-stage job performs the existing Primary authentication
preflight in the protected openai-api environment, even for dispatch-only work,
without calling the model for dispatch-only readiness.

Dispatch sees only a boolean readiness signal and the explicit primary flag,
not OPENAI_API_KEY. Before any claim, Python checks the enable flag, verified
auth signal and read-only ledger budget/unknown-cost status. Missing readiness
returns blocked_executor_readiness with empty matrices, no new run, and no model call.
The Direct worker independently checks budget and authentication again.

Because route selection currently happens after the atomic claim, this guard
conservatively also prevents NEW Codex routing when Primary is disabled.
Already-routed Codex and manual handoffs continue under independent paths.
Allowing new Codex-only claims without Primary requires a separately designed
route-aware transactional preclaim selector; bypassing this guard is unsafe.
## Same-run dispatch after product planning

The initial scheduler probe's `product_work` signal only indicates a possible
product-stage run; it does **not** prove any Work Units exist. The dispatcher
must not start just because the product-stage job was successful (a job may
succeed after reporting disabled primary credentials). The product-stage job
writes a structured `claimed/completed` result; only a completed claimed
run triggers one additional read-only Control Plane schedule probe. Dispatch
is eligible during a scheduled/owner-wake run if either the initial probe or
the fresh post-product probe reports `dispatch_work=true`. This preserves
same-run planning -> Change Set -> dispatcher responsiveness without an
unproductive dispatch or unnecessary Model/Preview operation. The manual
`workflow_dispatch` intent remains independent. The post-product probe
records existing durable schedule-probe audit events only; it does not
invent or resurrect Work Units.

## Primary-model opt-in for unattended product and Direct execution

The production GitHub Actions `product-stage` and `direct` jobs read the protected
`FACTORY_PRIMARY_MODEL_ENABLED` GitHub variable as a strict, case-sensitive
boolean. When the variable is absent, malformed, or anything other than
`true`, the jobs receive `false`. The mere existence of `OPENAI_API_KEY`
or WIF configuration does **not** authorize paid requests.

Before an administrator explicitly enables that variable, verify the existing
approved API billing/quota and model access, plus Control Plane ledger health
(known spend, no unknown-cost events) and the fixed US$ 4.00 total budget /
US$ 0.50 reservation. The Python runtime rechecks both the enable flag and
the ledger *before claiming* a product-stage or Direct run, and the metered
provider still enforces the real per-run reservation. Do not perform paid
smoke calls just to poll readiness, and never purchase credit automatically.

This explicit opt-in does not enable Codex, change GitHub App permissions,
authorize production merges, bypass preview verification, or requeue historical
`plan-*` tasks. A newly created real task must still demonstrate
planning -> new Change Set -> claimable Work Units -> PR -> CI/evals ->
verified Preview when applicable -> awaiting_release. A deterministic
fixture test exercises only the early planning/materialization contract; it
is **not** a release or production E2E signal.

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

The Python runtime supports Phase 3 repository-scoped GitHub App credentials without broadening access. For cross-repository work, it first checks the durable project access record. Only `auth_mode=github_app` with `status=ready`, a verified `installation_id` and the exact `repository_id` may mint a short-lived installation token. The trusted Control Plane Edge Function reads the private PEM from Vault and signs the App JWT inside Supabase; neither PEM nor App JWT leaves that broker. GitHub Actions receives only the short-lived installation token restricted to that one repository ID and the reviewed permission set, and the token is never persisted or logged. Same-repository Actions work continues to use the native `GITHUB_TOKEN`. Projects that have not migrated to the App may still use the explicit `FACTORY_GITHUB_TOKEN` fallback; once a project is marked `github_app`, a blocked/incomplete App installation fails closed and never silently falls back to the PAT.

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

## Factory Console Preview cost policy

Automatic exact Preview/browser evidence for the Factory repository is applicable only when a pushed `preview/**` or `evidence/preview/**` candidate changes `apps/console/**`. Runtime, documentation, tests, broker, or other non-Console changes must not consume a Vercel Preview or browser verification merely because the branch name uses the Preview namespace.

The Vercel project uses the same rule: Preview branches are ignored when the commit does not change the Console tree. Production `main` keeps its broader ignore rule so source-controlled release-policy changes can still publish the Console when required.

Explicit `workflow_dispatch` of exact Preview evidence remains available for a reviewed exceptional case and is not widened by the automatic path filter.

The trusted browser verifier itself is manual-only and requires the exact Vercel URL as an explicit runtime input. Do not persist a reusable Preview URL/candidate pair in the repository: Vercel Preview deployments are ephemeral and a historical URL can later return 410. Exact candidate discovery belongs to the exact-Preview/cross-repo resolver, which reads current GitHub/Vercel checks and then dispatches the trusted verifier with the resolved URL.

## GitHub-hosted browser runtime

Trusted Preview verification on GitHub-hosted Ubuntu 24 runners uses the Chrome executable already provided by the runner image at `/usr/bin/google-chrome`. The workflow still pins the Playwright npm package version, but sets `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1` and does not run `playwright install --with-deps`.

This is a performance/cost hardening only:
- Playwright remains the browser automation library;
- browser verification remains mandatory when Preview is applicable;
- the workflow verifies that the expected Chrome executable exists and fails closed if it does not;
- no browser binary, Vercel bypass secret, reusable credential or generated-code token is persisted;
- the autonomous Preview worker installs the Playwright package only after `preview-probe` reports real browser work.

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
- when `preview/pr-<n>` does not exist yet, the promoter seeds it at the candidate parent and immediately advances the same ref to the exact candidate; this produces a real ref update for the Vercel Git integration while the branch-creation event itself remains non-authoritative;
- if `preview/pr-<n>` already points to the exact candidate SHA, the workflow reuses it before any budget check and does not request another deployment;
- Preview promotion does not require a Vercel token: when provider usage credentials are absent, GitHub Actions records actual preview-ref promotions in the rolling 24-hour window as advisory telemetry; this local count never masquerades as provider quota and cannot block an exact final candidate by itself; no-op/stale promoter runs do not count, and a run is observed whenever its ref-update step succeeded even if a later step failed;
- the standard Preview promoter intentionally receives no persistent Vercel token or team id; its local GitHub promotion count is advisory only and never masquerades as provider quota;
- provider API usage collection is a separate optional Control Plane job. When read-only `VERCEL_TOKEN` and `FACTORY_VERCEL_TEAM_ID` are explicitly configured for that collector, it records rolling-24h deployment usage and the 70/85/95% policy inputs without coupling Preview creation to long-lived provider credentials;
- the Vercel Git integration remains authoritative for whether a deployment can actually be created; a real provider refusal still fails the exact-candidate Preview path;
- the workflow never calls Vercel CLI or a Vercel deployment-creation API; deployment creation remains the Git integration's responsibility;
- promotion evidence is retained in the GitHub Actions run summary; normal Control Plane reconciliation remains responsible for project lifecycle evidence;
- ref updates performed by the native `GITHUB_TOKEN` do not recursively start push workflows, so the promoter explicitly dispatches `Exact Preview browser evidence` for the exact candidate and waits for the candidate-scoped `Factory Preview browser evidence` commit status; `evidence/preview/**` is a non-deploying recovery trigger, while only `preview/**` can request Vercel deployment;
- exact browser evidence waits for the Vercel commit status to reach success before using a Vercel check URL; early Preview Comments checks are not sufficient readiness evidence;
- `ignoreCommand` remains a path-based second guard;
- Vercel `api-deployments-free-per-day` remains an external quota: do not retry deployments or buy capacity automatically.

## Resource quota observability

The Control Plane records provider/resource/metric, used value, limit, percentage inputs, measurement quality, source, window/reset and status. The optional Vercel collector runs every six hours only when its read-only provider credentials are already configured; missing credentials skip that collector cleanly. Preview safety does not depend on those credentials: exact-candidate binding, stale-candidate cancellation, ref reuse and path gating remain active, while the GitHub-local promotion count is advisory rather than an invented provider quota. GitHub Actions usage remains unknown until a reliable billing/usage source is connected.

## Preview applicability policy

Preview is fail-closed by default. A project can make non-applicability explicit in `factory_projects.manifest.preview`:

- `required: false` with a reason for projects that have no deployable Preview surface;
- `required_paths: ["apps/web/**", ...]` for monorepos where only specific file changes require a Preview.

The policy is evaluated against the exact PR changed-file list. Skipping a Preview still produces durable release-readiness evidence and never skips the human production merge.

## GitHub credentials across repositories

GitHub Actions `GITHUB_TOKEN` is treated as repository-scoped. Inside Actions it may be used only when the target repository equals `GITHUB_REPOSITORY`.

Cross-repository issue/branch/PR/CI/Preview operations require `FACTORY_GITHUB_TOKEN`. The runtime never falls back to the current repository token for a different repository. Configure that secret only in the Factory execution environment and never expose it to generated code or browser clients.

Minimum target-repository permissions depend on the operation: contents read/write, issues read/write, pull requests read/write, and checks read for full Direct delivery. Follow-up readers can use narrower permissions when separate credentials are used.

GitHub App cross-repo onboarding: after registration, `/gates` derives installation actions for active cross-repository projects whose access is not yet `github_app/ready`. The Factory binds the install attempt to the intended project in an HttpOnly, short-lived cookie, sends the operator to GitHub for the real consent action, and automatically performs server-side verification after GitHub returns to the configured setup URL. The `installation_id` query parameter on the setup URL is never trusted as authorization; verification independently asks GitHub for the installation associated with the exact project repository. Installation should be limited to the intended repository and is not trusted until that verification succeeds with a short-lived installation token.
