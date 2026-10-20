## 20/10/2026 — Candidato: classificacao de fonte gratuita em toda reconciliacao platform

- A execucao real de issue_comment 39359305907 validou preflight gratis com path scripts/audit_autonomy_journey.py no SHA 5b590825; Product Stage e workers pagos ficaram skipped. Run original #987 permanece failed; isto NAO comprova E2E.
- A reconciliacao platform ja le fonte GitHub antes do modelo, mas nao diferenciava fonte completa, parcial, arquivos ainda a criar ou briefing sem paths. Evidencia estrutural forjada (SHA mismatch, path inconsistente, recibo contraditorio) deve bloquear consumo de API com razao duravel.
- Novo contrato classifica complete/partial/new_files_only/unscoped SEM criar gates artificiais: arquivo faltante pode ser justamente a funcionalidade pedida; grandes tarefas nao podem ficar paradas por limite de snippet. Auditor somente leitura reporta parcial de forma honesta, e claim bloqueia apenas recibos invalidos.
- Testes gratuitos em code/test fakes, integracao de claim com erro redigido, leitura de issue e isolamento de modelos. Sem migration/Console/auto-merge; CI no SHA exato antes de liberar producao.
## 20/10/2026 — Candidato: Product Stage preflight real e gratuito por run

- Merge #988 confirmou CI e Console saudável, mas a run real 16b12d17-9cb0-4578-a0e2-0d601f36b856 continua failed, sem replay. Na verificação mais recente, zero runs executáveis, zero Change Sets ativos e zero eventos novos de modelos pagos.
- O novo preflight proposto lê somente GET e cruza project_key, run, task, generation, snapshot e GitHub SHA. Corrige falta de código em contexto quando pedido platform só cita uma issue: extrai paths de issue do mesmo repo sem copiar instruções da issue ao modelo.
- \`run_offline_preflight\` como modo manual isolado reutiliza OIDC existente; schedule-probe/agents são SKIPPED. Fonte verificável não equivale a Product Stage executado nem E2E real.
- Antes de merge: CI completo, testes offline e verificar alteração de custo = zero. Sem migration, mudanças de RLS, merge automático ou chamadas pagas de teste.

## 20/10/2026 - Candidato: feedback imediato de continuacao + preflight platform

- Incidente real: operador clicou duas vezes em Iniciar novo ciclo para issue #987 no projeto ai-product-factory. Control Plane confirmou uma unica nova task/run (run 16b12d17-9cb0-4578-a0e2-0d601f36b856) em 2026-10-20T01:14:21Z. Wake foi solicitado; GHA 39352319002 assumiu, mas falhou antes do modelo com reconciliation_context_preflight_failed.
- Raiz nos logs: a rotina de contexto exige project_kind=existing e Preview PR fixado; a Factory e project_kind=platform e usa main. Nao houve uso de modelo para essa run. Nenhuma run sera reativada automaticamente.
- Este candidato exibe feedback via React useFormStatus, botao disabled enquanto o servidor grava e aria-live; o request_id idempotente permanece estavel. Inclui origem GitHub main exata, somente leitura, com governanca obrigatoria para platform; projetos existing mantem regra do PR fixado. Testes de regressao e CI/Preview sao requisitos antes de liberar merge em producao. Nao ha migration nem custo de modelo nesta mudanca.

## 19/10/2026 — Estado apos merge humano da PR #983

- Factory main verificada em 3da90ed2628d240c47163f7ce3ec676c4f59e86e; validate verde. Nao confundir CI da Factory com prova de E2E autonomo de novo projeto.
- Control Plane: zero Change Sets executaveis, zero gates humanos pendentes, scheduler sem trabalho. 5 Change Sets CRM e 10 tarefas historicas foram encerrados com auditoria, sem DELETE.
- Budget real: total US$ 10, reserva US$ 0,50 por run, uso conhecido US$ 9,0264452; proibido executar modelos apenas para teste.
- Proxima prova: operador inicia um projeto NOVO manualmente, e a Factory deve chegar por si a CI, Preview conforme politica e awaiting_release. Auditor de jornada em preparacao, somente leitura (docs/AUTONOMY_JOURNEY_EVIDENCE.md); nao declarar produto pronto por simulacao.
- O proximo PR da Factory nao deve executar worker pago, autostart, auto-merge ou migration. O teste real so ocorrera quando existir Start humano e fluxo aprovado.


- Auditor PR #984: corrigida leitura de dados reais do CRM (reconciliation/gap_analysis), recibos de release com project_id NULL e prova de ancestralidade do commit de Work Unit; sem Start novo, nao existe ainda prova operacional E2E.

## 2026-10-18 — Durable project-control wake (candidate)

Five functional blocks: SQL outbox trigger recording START/RESUME/RESTART atomically; privileged claim/ack lease with five attempts and generation fencing; postcommit Console delivery with durable failure; existing scheduled runner observes pending work without paid calls; project UI exposes status, with PostgreSQL 16 concurrency/idempotence testing.

The SQL migration `20261019002000_project_control_wake_outbox.sql` is **not applied**. Needs SHA-exact CI and Console Preview, human Factory production PR merge, and separate migration authorization. No registration autostart, paid probe, broader RLS access, new timers or runtime auto-merge. "Observed" means runner saw the wake, NOT task executed.
## 2026-10-18 — CRM #180 proved CI → verified Preview → nonproduction merge (candidate observer)

- GitHub CRM PR #180, candidate `aee522fe742589e961420e15e9dc92a1500ae502`, passed CI, Factory quality gate and specialist Security/QA/Operations. The Vercel deployment and Playwright/browser evaluation passed at the candidate SHA, with four browser checks.
- An authorized operator merged this PR **only into** `preview/hardening-release-candidate`, merge SHA `88c3517529654911ed4ee3315fdcdafc200e3004`, at 2026-10-18T21:26:52Z; verified `main` stayed at `e521308e14380121670b22f1aa3078d14e1883d7`. Vercel returned exact merge-SHA success at 21:27:26Z, proving a Preview build but **not** a production release or postmerge browser E2E.
- Postmerge trusted browser workflow [#39168485494](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/39168485494) independently verified merge SHA `88c35175` with expected Infodive UI text, and persisted Control Plane snapshot `7baee883-3887-4185-8565-42aaa3fbe923`; this new candidate binds its atomic integration to this exact merged-SHA snapshot, never reusing only the old candidate browser evidence.
- The existing release observer intentionally refuses to mark a `preview/**` target as released, but leaves its run stuck in `awaiting_release` forever. **This candidate** introduces a separate fail-closed read-only GitHub observer and privileged atomic RPC that mark a nonprod Change Set as integrated, record merge evidence and mark the old production release report blocked pending a separate verified `main` PR. It never calls merge in the Python runtime, never emits `human_release`, and never claims the product ready.
- **Deployment gate:** production code/migration are NOT yet applied by creating this PR. CI, human Factory production merge, and separate authorization for migration `20261018213500_observe_preview_branch_integration.sql` are required before the observer can reconcile CRM #180.

## 2026-10-16 — Policy UI reconciliation, migration already applied (candidate #866)

- The privileged Supabase migration `factory_primary_cost_policy` is already present in production migration history as version `20261015232347` (verified 16 October). It seeds the previously authorized internal budget USD 10.00 and reservation USD 0.50; this does **not** prove OpenAI Platform credits or permit automatic purchases.
- This branch rebases the staged admin-configurable budget UI/runtime onto the live post-#881/#863 Factory code. Exact merged GitHub fixes for early-human-merged CI and OpenAI pre-response credit rejection are preserved. Both the production merge and exact-SHA Console Preview/browser evidence remain mandatory.
- Do not reapply the policy migration, auto-merge, requeue Service Desk, run paid model probes, or infer current OpenAI credit from the internal ledger.

## 2026-10-16 — Service Desk: human merge before CI + cross-repo QA credential incident (candidate, not deployed)

- GitHub **verified** PR #7 of `leandrosilveiradepaula/infodive-service-desk` was human-merged at 10:59:11 UTC into `main` `412f24d6dc7d0805b231ce91f12874ced743eebb`, from candidate `60be648ef78a2fba4971f227c8d49c026834c580`, before real CI/quality/Preview. Factory run `605212cf-b47e-418a-b4c4-79ad1efc6f59` and Change Set `effc36be-212c-42f2-928b-97381b6d8a28` remain `ci_pending`. Control Plane incident audit #1041 documents the observed external merge without pretending it was a verified release; pilot issue #8 tracks remediation.
- Factory PR #880 was human-merged at 11:44 UTC, enabling a bounded owner-initiated cross-repo QA workflow; Factory CI passed on PR and merged main. Owner command `/service-desk-qa pr=3 sha=1001cb9e7508f0c484f4d0d5ae590ecf4d35f51c` was executed exactly once on issue #841. Real Factory runner #38895967648 started and correctly **failed closed before checkout**, because `FACTORY_GITHUB_TOKEN` is absent in this workflow. No npm install, CI evidence, billable model call, or release happened. The native private-pilot runner also remains blocked. Never replace the token with Factory `GITHUB_TOKEN`, broaden OIDC scope, or buy capacity without explicit approval.
- **This candidate** adds a deterministic early-human-merge CI follow-up branch and service-role-only transactional RPC `factory_block_early_merged_ci_candidate`. An exact GitHub PR head + merge SHA causes the existing `ci_pending` run and linked Change Set to transition atomically to `blocked`, with an audit event and explicit `quality_gate_passed=false` / `preview_verified=false` / `release_authorized=false`. The candidate SHA is preserved. Repeated evidence is idempotent; changed heads, missing merge SHAs, stale states, missing create-PR proof or released reports fail closed.
- This is **code/migration proposal, not applied**. The original Service Desk run has not been mutated by this candidate. Human merge of the Factory PR and a separately approved, verified Supabase production migration remain gates. With the function deployed, the existing CI follow-up can observe and block the stale PR #7 once; it does not bypass product QA. The pilot PRs #3/#5 remain Draft and cannot be considered release-ready until real TSX/CI/build, two-tenant RLS, Preview applicability/evidence, and human release policy are satisfied.


## 2026-10-16 — Console: falhas por crédito OpenAI no painel (PR #875 reconciliada)

- O Control Plane mantém execuções `blocked` que não estavam entrando no resumo operacional; o operador precisava visitar telas técnicas para encontrar o incidente. Esta alteração torna o bloqueio visível na página inicial e no detalhe da run, sem confundir o total de falhas com dead letters ou com a quantidade de aprovações humanas.
- A classificação é baseada em erro de provedor `credit_balance_exhausted`/rejeição de quota com mensagem inequívoca; orçamento interno da Factory e rate limit genérico não acionam o mesmo aviso.
- O aviso informa **quando ocorreu o bloqueio**, não afirma saldo atual zero. Reposição de crédito, status atual de billing, reconciliação de ledger e retomada são verificações/gates separados. Nenhum crédito é comprado ou retry é disparado nesta PR.
- A proposta preserva a nova arquitetura da #882 (3 destinos principais, mobile e disclosure técnico). É candidata: requer CI, Vercel Preview do SHA exato, teste browser autenticado e merge humano para produção.

## 2026-10-16 — Authenticated Console visual audit targeted stale SHA after #882 (candidate)

- PR #882 was human-merged at 13:01:15 UTC in `53bd03b274129925f713f614243093e165f03ed1`; merge-SHA `validate`, `factory-acceptance` and `Console validation` all green. Vercel commit status reported successful deployment at 13:02:40 UTC. Neither check asserts `/api/health` is serving this exact commit.
- Real authenticated audit run [#38904687637](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/38904687637) incorrectly selected historical pinned SHA `34c614be...` from `.github/authenticated-visual-target.json`. The run failed on React hydration `#418` at `/configuration`; post-failure cleanup succeeded. No authenticated browser evidence for #882 was accepted, and the cause of hydration remains unverified.
- Candidate follow-up guards `push main` changed Console paths to exact `GITHUB_SHA`; retains manual pinned audit for workflow-only change; requires Vercel success status on full SHA and live `/api/health` `commit === SHA.slice(0,12)` before Playwright/user creation and after capture. Test mismatch fail-closed. Source-controlled pinned target now refers to #882 for a focused follow-up, without new deployment. Independent incident + details: `docs/CONSOLE_VISUAL_SHA_GUARD_20261016.md`.
- Human gate remains for merge of any production-publishing PR. This preparation makes no production change, creates no paid model request, bypass, Preview or migration. A repaired audit is **not** evidence that the React hydration issue was fixed; resolve/reproduce separately.

## 2026-10-16 — Console UX: operação e aprovações à frente da infraestrutura (PR candidata)

- Revisão da `main` `5710b9d64797cc9199d120766245916ad002a982`: 13 destinos visíveis, ações redundantes, instruções permanentes antes dos projetos, experiência móvel confusa, percentuais de etapa potencialmente interpretados como prontidão. O formulário de intake possuía dois campos `name="users"` na criação greenfield.
- Candidato UI: 3 entradas principais (Visão geral, Projetos, Aprovações), 10 ferramentas técnicas preservadas em disclosure; barra inferior mobile, menu completo; home com projetos reais e decisões acionáveis; edição com uma CTA principal, integrações/evidências colapsáveis; etapa do fluxo sem falso percentual; intake simplificado sem duplicação de campo.
- Mudanças limitadas a Console, capture visual autenticado, testes e documentação. Nenhuma migração, autorização de custo, alteração de Control Plane ou auto-merge. A checagem de Preview **é obrigatória** para `apps/console/**`, somente com deployment READY e browser evidence no SHA exato; política fail-closed se não estiver disponível.
- Plano e critérios de aceite detalhados em `docs/CONSOLE_UX_REVIEW_20261016.md`. **Mudança candidata, não publicada.** O release continua condicionado a CI, Preview verificado e merge humano.

## 2026-10-16 — Reposição de crédito OpenAI e reconciliação de chamada rejeitada (candidate, não publicado)

- O operador confirmou novo crédito pré-pago. Ainda não houve chamada de modelo para sondar saldo. O Change Set do Service Desk segue bloqueado na onda 7; a mesma run `fffee538-9781-4905-a69d-f3427d6f66b3` mantém tentativa 1 e o ledger possui **exatamente um** evento pago de custo desconhecido (usage #117) oriundo de HTTP 429 `credit_balance_exhausted`.
- O runtime `require_paid_runtime_budget` e Product Stage `primary_readiness_blocker` corretamente bloqueiam qualquer execução paga se `unknown_cost_events > 0`. Reposição de saldo não remove o guard financeiro.
- Candidato: tipar exclusivamente rejeição estruturada de crédito sem Response/tokens; manter outras falhas como `cost_unknown`. Migration versionada separada e idempotente classifica somente a evidência histórica exata, mediante **revisão humana de faturamento e aplicação administrativa de produção**. Nada foi alterado no banco nesta preparação, nem compra/retry disparado.
- Procedimento e provas em `docs/CREDIT_DENIAL_RECONCILIATION.md`. Após migration auditada e gate financeiro novamente verde, recupera-se a **mesma** run e depois um único wake; merge de produção sempre humano.

## 2026-10-16 — Integration attempt counter per wave (candidate, not deployed)

- Real greenfield Service Desk eight-wave Change Set `effc36be-212c-42f2-928b-97381b6d8a28`: wave 4 `knowledge-base` Direct run `28497089-9415-43e8-b8e4-06bf754b5607` completed and produced `dc044aaaf23f64ca6a3df818430ec1e2a1fa3df5`, but Factory GHA [#38839037505](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/38839037505) Change Set integration logged `claimed:false, processed:0` even though its job was green.
- **Confirmed root cause (Supabase production read-only):** `factory_claim_change_set_integration` requires `s.attempt_count<3`, and the Change Set has `attempt_count=3` from successful integrations of waves 1, 2 and 3. `factory_complete_change_set_integration` advanced the `current_wave` without resetting the counter. It would silently starve all eight-wave plans after three successful waves.
- Proposed SQL fix **preserves** the maximum three attempts within each wave and resets `attempt_count=0` **only on successful advancement to a later wave**, while persisting `integration_attempts_by_wave` history; an unsuccessful integration does not reset the retry count. The claim/recovery SQL is intentionally unchanged, and all functions remain `SECURITY INVOKER`/service-role-only.
- The versioned migration includes an **exact-identity, fail-closed and audited one-time repair** for this recorded Change Set. It checks the project ID, exact candidate/base, no leases, precisely 3 prior integrated waves/4 units, the completed wave 4 run/commit and 8 untouched later work units. It does not create a run, merge a PR, or touch the pilot data schema. All mismatches abort the migration atomically.
- **PRODUCTION GATE:** GitHub CI and PR merge alone do not apply SQL. Administrator must explicitly apply the migration via the authorized Console path, then independently verify the function definition and the audit/counter in Supabase. Only after applied migration and confirmed candidate branch SHAs may one OWNER `/factory-wake` resume existing wave 4 integration. No autonomous migration, no auto-merge, no paid test calls. The pilot's security/React/CI blockers remain open issues #1/#2; green Factory jobs with `processed:0` are not quality evidence.

## 2026-10-16 — Safe greenfield continuation scopes (PR candidate, NOT released)

- Real Service Desk second-wave Direct run `151954cb-91ba-4434-bd50-6b389175906f` on GHA [#38836556208](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/38836556208) was claimed after first-wave integration, but stopped in preflight with `semantic write scope could not be resolved safely: auth`. The original run, work unit and Change Set remain blocked; the other 11 units remain pending. This is a legitimate fail-closed result, not an OpenAI billing problem.
- Root cause: scope resolution relied on filenames already existing; the eight-wave greenfield plan explicitly names semantic areas whose modules must be created later. The README-only bootstrap applies only to wave 1 and correctly does not permit blanket writes in later waves.
- Candidate fix reads authoritative `project_kind` from Control Plane and enables bounded architectural namespace mapping only for post-foundation greenfield work units, only with existing README, package metadata and `src/` foundation. Versioned migration writes require an existing migration root. Known structural suffixes (domain, API, UI, services, jobs, workspace, portal, layouts and queries) work for other products without product-specific exceptions; unknown scopes, uninitialized repos and imported projects retain fail-closed behavior. Exact explicit context paths are never overridden. Model writes are still checked by `enforce_write_scopes`; no repo-root scope, `.github/**`, credentials, or production path is introduced.
- Regression tests cover the real wave 2, all 12 planned scope groups, imported project refusal, unexpected paths, frozen context, missing migration roots and path traversal. No calls to paid models, provider quota checks or Vercel deployments are part of these tests. Only GitHub PR CI is evidence before merge.
- **Recovery remains separate**: never automatically requeue the blocked second-wave run or create a duplicate. After a human production merge and verified CI, revalidate the exact blocked run, task, assignment, work unit, and Change Set, then perform an individually authorized, transactional/audited same-run recovery before one OWNER wake. No auto-merge.

## 2026-10-16 — README-only greenfield foundation preflight (awaiting merge)

- Real Service Desk GHA [#38826947695](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/38826947695): after human-merged #868, adaptive concurrency correctly became **1** despite Vercel `deployments_daily=blocked`, and the real protected Direct job **started** run `e0d94242-9236-4288-a415-54d81a9553d7` for the first foundation wave. This is not code success. `change_set_worker._resolved_repository_context` blocked with `repository context discovery found no relevant files; replan with explicit context_paths`. Database set run, task, work unit and change set to `blocked`; no model cost increase or commit occurred.
- Root cause: `leandrosilveiradepaula/infodive-service-desk` at its frozen SHA `62dcc97187c78f53408ac60cba88b83585d6323b` contains **only README.md**, while work unit `foundation-app`, wave 1, requests the semantic foundation scopes `application-foundation`, `database-migrations`, `environment-template`, `domain-shared` to create the initial TypeScript files. Existing context ranking requires already-matching code files; it cannot bootstrap an empty codebase.
- Candidate change is generic, **not hardcoded to Service Desk**: in a README-only/metadata-only repository, for **wave 1**, an explicit foundation/bootstrap/scaffold plan task and **only known semantic scope keys** may resolve to a fixed, allowlisted set of structural paths (package.json, TypeScript config, `src/**`, tests, migration directories and safe configuration source files). Always include README and any actual AGENTS/CURRENT_TASK governance in the bounded frozen-SHA context snapshot. Never grant `.` or `.github/**`, live `.env`, secrets, unrestricted root, or override explicit context paths. Populated repos, later waves, unknown scopes and unrelated work retain strict failure. Model-produced writes still pass `enforce_write_scopes`; out-of-scope writes block the unit with auditable `repository_governance`.
- New deterministic tests exercise README-only success, AGENTS governance, no root scope, fresh-file acceptance, populated-repo rejection, unknown scope/later wave rejection, invalid explicit paths, and attempted workflow writes. **No paid model call or real provider usage** is performed by CI.
- **Important recovery gate:** original run `e0d94242...`, work unit `389631fb-13b6-4c9b-ad0d-065b91b86a10`, change set `effc36be-212c-42f2-928b-97381b6d8a28` remain durably `blocked`. The standard recovery RPC only requeues expired running leases, and `factory_retry_failed_run` supports `failed` tasks only; neither silently unblocks this stopped work. After human merge and verified CI, a **separate explicitly approved** audited, idempotent Control Plane recovery must requeue exactly the original run/work unit and reset the change set if no other blockers; never create a duplicate run or reset later waves. Document and confirm the recovery state before triggering the next authorized wake.
- No `apps/console/**` changes: Factory Preview N/A for this candidate. #866 Console financial policy remains Draft until real Vercel Preview READY + browser evidence at its own SHA; Vercel provider quota remains blocked. Release merge is always human.

## 2026-10-15 — Service Desk Direct concurrency blocked by unrelated Vercel Preview quota

- Real run [#38825991468](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/38825991468) was triggered exactly once through the existing OWNER-only `/factory-wake` path, after #867 merged. Queue probe found 13 eligible portfolio work units; Product Stage published protected `primary_ready=true`; dispatcher **correctly created the first Direct run** `e0d94242-9236-4288-a415-54d81a9553d7` and assigned the development agent. This verifies #867's scope fix in real production behavior.
- But the dispatch work matrix returned `direct=[]`, `effective_concurrency=0`, reason **`resource quota is blocked`**, and the Direct GitHub job was SKIPPED. The durable run is queued, not completed; Service Desk change set `effc36be-212c-42f2-928b-97381b6d8a28` now has 1 queued unit in wave 1 and 12 pending units across waves 2–8, with no code commit or PR.
- Live Control Plane `factory_resource_limit_snapshots` has only **Vercel / team / deployments_daily** signals (latest persisted 2026-10-13 17:38 UTC, blocked). `factory_agent_concurrency_decisions` recorded that same blocked signal as an unscoped global quota for a Direct task. Vercel **deployment** quota only applies when publishing/validating Console Preview or release; it is not consumed by Direct code writing to GitHub. This cross-provider coupling is the actual root cause, not exhausted OpenAI budget: known paid ledger USD 3.7210392, 0 unknown events; existing protected model gates stay in place.
- Candidate change (Python + tests + docs only): exclude **only** Vercel `deployments_daily` signals from the Direct/Codex concurrency matrix. Keep all other provider and resource quota blocks, unknown paid-cost blocks, per-run reservation, protected Primary enablement/identity, and provider-billing gates. If no execution-relevant quota is observed, status remains `unknown` and concurrency stays capped at 1 rather than presumed healthy. Record Preview quota separately as telemetry; **do not change Preview's own fail-closed Vercel cooldown or deployment evidence**.
- New deterministic tests replay the exact `vercel/deployments_daily/blocked` case and verify a single runnable Direct item; prove independent OpenAI/GitHub/other blocked quotas and unknown paid costs still enforce concurrency=0. No API calls, Vercel deploys, schema migrations, fresh tasks or credits.
- The patch is **not deployed** until human merge of its green CI PR; next native/authorized wake should resume the existing queued run without duplicating it. Check a real Direct job, commit, PR and cost ledger before claiming implementation succeeded. Preview N/A for the Python-only Factory patch. PR #866 Console remains Draft until exact-SHA Preview/browser evidence.

## 2026-10-15 — Service Desk wave 1 dispatch gate fix awaiting human merge

- Production Evidence: GHA [run 38822922959](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/38822922959) Product Stage `FACTORY_PRIMARY_MODEL_ENABLED=true` inside protected `openai-api` environment, completed Service Desk planning run `d5f1ea54-c388-4266-83b1-b8b06f2fd302`, materialized change set `effc36be-212c-42f2-928b-97381b6d8a28` with 13 pending work units across eight dependency waves. Dispatcher subsequently logged `FACTORY_PRIMARY_MODEL_ENABLED=false`, `FACTORY_DISPATCH_PRIMARY_READY=true` and returned `blocked_executor_readiness` because unprotected `dispatch` cannot see environment-scoped GitHub vars.
- Candidate fixes only `dispatch` to use the **trusted, fail-closed output of protected Product Stage** for both the primary flag and prior authentication readiness signal. If Product Stage is absent/blocked the output is not `true` and dispatch stays disabled. The Python gate `require_dispatch_claim_readiness` still requires both booleans and rechecks the real ledger/reserve before any atomic claim. No secrets are passed into dispatcher; Direct itself still checks opt-in + credentials + cost with protected `openai-api` environment.
- Regression contracts assert the source is the protected job, that the dispatcher cannot depend on repository-level vars for this decision, that the protected jobs retain strict explicit opt-in, and that no API token appears in dispatch. No Console path changes: Preview **not applicable** for this patch.
- No runtime merge or paid probe, no change to total US$10/reserve US$0.50, no API purchase, no Codex token, no changes in #866 Draft. Publish to main only by human review/merge.

## 2026-10-15 — Primary paid budget configurable in Console (candidate, NOT deployed)

- The operator identified a verified split-brain: PR #865 was merged and `main` runner used a US$ 10.00 cumulative total with US$ 0.50 reservation, but `/usage` still rendered a fixed US$ 4.00.
- This candidate introduces a **singleton, versioned** `factory_primary_cost_policy` row in Supabase seeded to the already authorized 10.00/0.50 at migration, with no anonymous/authenticated RLS policy. All subsequent changes require a privileged Console admin POST with exact Origin check, an explicit confirmation, a reason, optimistic version check, row lock and an append-only audit entry in the same PostgreSQL transaction.
- Runtime `Product Stage`, Direct preclaim, per-model-call metered reservation, no-model readiness and cost alerts **read the same Control Plane policy**. No environment fallback: missing/malformed policy/ledger or unknown paid costs blocks execution. Provider quota and actual OpenAI API credit remain independent and **unverified** until normal guarded real work occurs; no billing probes or purchases.
- Configuration screen provides the editable admin form, spend and remaining internal ceiling, ledger unknown-cost state and policy version. `/usage` now reads the real persisted budget instead of advertising stale US$ 4.00. Operator read-only view remains.
- **Human gates:** (1) apply and verify `supabase/migrations/20261015231500_factory_primary_cost_policy.sql` in production before any runtime promotion; (2) verify CI and SHA-exact Vercel Preview/browser evidence for `apps/console/**` change; (3) a human merges the code PR to publish production only after the migration and gates. Preview may be rate-limited; do not bypass it or claim READY.
- The metered reservation continues to record a durable before-call usage row. The existing separate-check/read and usage-row write are not an atomic global budget reservation across simultaneous paid workers; this candidate does not claim to solve that pre-existing concurrency risk. Keep conservative concurrency/quotas and fail closed.

## 2026-10-15 — Authorized Factory internal ceiling US$ 10.00 (candidate pending human merge)

- Explicit operator approval at 22:49 UTC: raise the **total internal** model ceiling from US$ 4.00 to US$ 10.00, keep the US$ 0.50 reservation. The PR updates all six autonomous-runner budget environments and the separate quota/alerts preflight, plus regression contracts. It does not enable any new model or change auth, Supabase RLS, GitHub App permissions, Codex, Preview, or release policies.
- Read-only Control Plane ledger before this PR: cumulative OpenAI cost US$ 3.5887672; 0 OpenAI unknown-cost events. `infodive-service-desk` remains `planning`, with run `d5f1ea54-c388-4266-83b1-b8b06f2fd302` in `created` (0 attempts) and one queued task. Last preflight blocked `budget_exhausted`, did not claim or charge a new call.
- The US$ 10 Factory limit does **not** purchase or reload OpenAI API credit. Original US$ 5 deposited by the operator on 2026-09-28 is historical. Current actual provider balance is unverified; OpenAI 429/quota/billing failures must remain fail-closed. No paid smoke tests to check the balance and no automatic purchase.
- After CI and **human production merge only**, rely on the existing scheduler/authorized GitHub App to resume the existing queued task when ledger, auth, and API provider allow. Do not enqueue duplicate work or bypass the human release gate. No `apps/console/**` modifications: Vercel Preview not applicable by policy.

## 2026-10-15 — Reused Preview ref ≠ Vercel deployment (candidato sem Console)

- Caso real #863: a ref `preview/pr-863` aponta para o SHA candidato, mas a Vercel retornou `Deployment rate limited` às 22:23:10 UTC e não publicou Preview. A primeira recuperação (#861) detectou um deployment posterior no SHA #860, mas a tentativa de novo Preview consumiu uma promoção de ref e recebeu nova negativa do provider.
- Este candidato adiciona o guard determinístico `scripts.preview_reuse_guard` ao fluxo já existente: quando `preview/pr-N` é reutilizada no mesmo SHA, exige status Vercel mais recente, inequívoco, `Deployment has completed`/`Deployment ready` e URL HTTPS de deployment concreto no mesmo commit. Rate limit, `Ignored Build Step`, ausência de status, empate de timestamps e inventário inválido bloqueiam antes de disparar outro browser workflow; o bloqueio é explicitado no resumo.
- Não força a ref de volta ao parent nem recria branch, não chama Vercel API/CLI, não habilita quota paga e não atribui Preview `READY` a uma referência Git. A prova pelo navegador continua obrigatória após status Vercel real. Para o mesmo SHA previamente recusado, um **novo deployment autorizado pelo provider** permanece dependência externa; rerun do promotor por si só não o cria.
- Somente Python, workflow e documentação; Preview Console N/A para o patch da Factory, CI obrigatório e merge de produção humano.

## 2026-10-15 — Atomic project intake and first run (#713)

The previous Console submitted create-intake, attachment-finalization and initial-bootstrap as three independent database calls. A failure after creation could strand a project with no initial run; repeating the form then hit the duplicate project key.

A new privileged SECURITY INVOKER function factory_start_project_intake_v1 executes those operations in one PostgreSQL transaction, using the original draft UUID as a stable idempotency key. The server obtains the operator identity and re-counts the private draft attachments (0–10), including finalized records for exact retries, rather than trusting a count in the URL. Any count mismatch, changed intake, conflicting project key, missing task or missing durable run fails closed. The same exact retry returns the existing run rather than starting another cycle, even after it has finished. The Console no longer calls the unsafe three-step sequence on project review.

**Preview validation:** a promoted `preview/pr-*` candidate always builds, even if that SHA was seen on a previously skipped branch. A Vercel status `Canceled by Ignored Build Step` is not READY evidence. Browser verification still requires a real SHA-exact Preview URL.\n\n**Required human gate:** apply and verify the versioned Supabase production migration before merging or deploying the Console change. There is intentionally no fallback to the old non-atomic flow when the RPC is unavailable. The PR's CI and Preview are only candidate evidence; they do not prove production database rollout or complete greenfield product E2E. No RLS widening, paid model calls or automatic production merge is introduced.

## 2026-10-15 — Non-starving autonomous CI/release followup (#713)

- After #832 human merge (Factory main `8854d640dcf6e70ed4d40370b145d3c285facb7c`), a concrete fairness gap remained: the bounded CI/release drain intentionally stops when its oldest `ci_pending` run is waiting for external CI or its oldest `awaiting_release` PR has not been human-merged. This could prevent later *independent* ready CI results or human merges being reconciled during the same scheduler wake.
- Both existing read-only Supabase queue selectors now accept a bounded tuple of previously observed run IDs. An empty tuple retains the original `limit=1` call; non-empty tuples read up to the 12 oldest candidates and select the first not yet observed **in the current wake**. Identifiers are never interpolated into a REST query; no schema/RLS change or Control Plane writes are introduced by selection.
- New `drain_waiting_followups` scans at most 8 distinct run IDs, completes at most 3 ready CI/release items per native scheduler job and records waits separately. It fails closed on duplicate IDs, malformed worker responses or bounds violations. A waiting human release gate is never approved or merged by the runtime; only an *already existing human merge* may be observed by `run_release_once`. CI keeps its existing SHA/quality checks.
- All other deterministic lanes, Direct, Codex, product stage, Preview and model/budget gates retain their existing behavior. This is a bounded fairness improvement, not a claim of greenfield full E2E. No historical queued task replay, new cron, paid model calls, Vercel Preview or Supabase migration.

## 2026-10-15 — Autonomous deterministic continuation within one scheduler wake (#713)

- Live Control Plane read-only check: 3 projects, 0 active runs, 0 pending human gates; 10 historical `queued` children of completed parents, **not eligible for automatic replay**. The native scheduler is active and can legitimately report no work. Never synthesize tasks or mark `product_ready` because CI/Preview passed.
- Previously, CI followup, Change Set integration, each Security/QA/Operations specialist lane and the release observer handled **one** candidate per scheduler run. The runtime now supports `--batch-items 3` for these **existing deterministic workers only**, processing at most 3 verified independent items per job and stopping on empty queues, unresolved CI, unmerged release, duplicate durable IDs, blocked status, or invalid worker output.
- `--batch-items` defaults to 1 for manual CLI calls; generic batch helper rejects bounds >4, booleans, non-allowlisted identities, duplicate IDs and malformed responses. GitHub Action permissions, OIDC, required CI/quality, exact SHA, paid budget controls and human release observer semantics do not change.
- Product/Direct/Codex/Preview remain single-item and governed by their existing cost, identity, quota, safety and release policies. Batch processing neither issues paid model calls nor invokes a merge operation. The scheduled job executes only when the authoritative queue probe signals work; no extra cron, GitHub Actions or Vercel deployments are requested.
- Regression tests include 8 deterministic batch invariants and workflow contracts. Following a human merge, verify the next *actual eligible work* and not merely the scheduler heartbeat; no newly eligible work is presently live. Do not interpret this implementation as E2E greenfield completion.

## 2026-10-15 — Exact cross-repo browser evidence correlation candidate (#713)

- Defeito reproduzido por inspeção: o workflow cross-repo escolhia qualquer run recente do navegador na main, o que podia associar uma execução concorrente a outro candidato. O patch inclui nonce UUID único por dispatch, run-name do filho, matching exato de workflow/branch/Factory SHA/attempt/URL/id/tempo e falha fechada para ambiguidade.
- O snapshot carrega provenance de execução filha (ID, UUID, SHA Factory), sem inferir prontidão de produto. Testes Node determinísticos e contrato Python. Sem novos Preview/deploy/permissions, sem RLS/migration ou custo modelo. CI precisa validar este candidato; merge de produção humano.

## 2026-10-15 — CRM pinned GitHub tree inventory (#713)

A new read-only GitHub API collector checks repository identity, open CRM PR #56, exact head SHA and complete commit tree, then emits only count-based `inventory_only` evidence. It runs as an added step within the **already broker-allowlisted** `crm-cross-repo-preflight.yml` in trusted Factory `main`, after a human merge or explicit workflow dispatch, using the same existing OIDC/GitHub App credential. A separately created workflow was rejected during security review because it would have received HTTP 403 from the broker OIDC workflow allowlist; this design does not expand that allowlist or deploy a new Edge Function. The artifact contains no source contents or tokens; the job fails closed on stale PR, truncated tree, unsupported symlink/submodule or missing cross-repo authorization. It never records a passing `factory_evaluations` baseline or changes the CRM database.

The GitHub API preflight found 961 tracked files, 558 sources, 136 test files, 79 migrations, one workflow and 52 route files at `f5f7d91f8e98cfaf482cca72c974abb7a82f6a5e`. These are inventory counts, not evidence of inherited debt review, tenant RLS, remote E2E or product readiness. The CRM database remains unavailable in the connected Supabase account. Further E2E and target database checks are still required.

## 2026-10-15 — Candidate #713: inventario Git existente deterministicamente limitado

- Criado leitor read-only `existing_project_inventory` que compara HEAD do checkout ao SHA candidato e inspeciona apenas `git ls-tree` para contar superficies e localizar lacunas; output sempre `not_assessed` e `inventory_only`. Nao ha conexao ao CRM Supabase por este projeto; nao sao fabricadas aprovacoes de RLS, journeys nem product readiness.
- CRM PR #56 ainda aponta para `f5f7d91f8e98cfaf482cca72c974abb7a82f6a5e`, 397 arquivos alterados, CI e Preview Vercel concluídos. O projeto de dados do CRM nao esta entre as duas instancias Supabase conectadas, portanto migracoes/RLS remotas permanecem sem evidencia.
- O modulo agrega testes com Git fixture em CI; nenhum workflow novo, permissao OIDC, job pago, migration ou alteração `apps/console/**`. A suite de CI do candidato, e não esta anotacao, determina se o patch esta apto ao gate humano de merge.

## 2026-10-15 — Greenfield lifecycle gate audit (#713, candidate Python only)

- A revisão real dos testes achou uma simulação greenfield que chamava `PREVIEW -> RELEASE -> OPERATIONS` sem `HUMAN_GATE` e a maquina de estados também permitia `BLOCKED -> RELEASE/OPERATIONS`. Estes atalhos eram inconsistentes com o contrato obrigatório de merge humano em produção.
- O candidato rejeita estas transições, preserva `PREVIEW -> HUMAN_GATE -> RELEASE -> OPERATIONS` e redireciona testes low-risk/offline para `HUMAN_GATE`. `decide_execution(RiskProfile())` continua Direct/autônomo para tarefas low-risk não-prod; `evaluate_release(PROD)` requer humano em todos os casos.
- **Limite da evidência:** a transição `HUMAN_GATE -> RELEASE` representa apenas estado lógico. Ela não autentica o operador nem valida o merge; somente o observador GitHub/Control Plane pode fornecer essa evidência. O teste offline não prova que um projeto novo atravessou realmente o pipeline completo.
- CRM #56 continua aberto em SHA `f5f7d91f8e98cfaf482cca72c974abb7a82f6a5e`, CI verde e Preview Vercel READY já registrados, mas E2E remoto autenticado, schema/RLS real e baseline completo seguem sem comprovação. As avaliações `product_readiness` persistidas no Control Plane eram `failed` em 2026-10-07 (SHA diferente do candidato atual); não reaproveitar esses estados como avaliação do SHA novo.
- Somente Python, testes e docs são alterados neste candidato; Vercel Preview N/A, sem migrations, modelos pagos, execução de benchmark 63, reativação de tarefas ou auto-merge de produção.

## 2026-10-15 — Auditoria #713: baseline existente fail-closed (candidato Python sem deploy)

- Leitura do Control Plane: `factory_projects` registra `crm-infodive` como `existing`, e os tres `factory_evaluations` de `eval_type=product_readiness` do CRM estao `failed`. Nenhum registro de `existing_project_baseline` foi observado no inventario de tipos. Greenfield E2E e existing E2E completos seguem **nao comprovados**.
- Gap encontrado: release intelligence revalidava seis dominios e SHA, mas nao exigia uma linha de baseline independente para projetos existentes; uma avaliacao auto-relatada poderia concluir `product_complete` sem cobertura de heranca. O candidato passa a ler `project_kind` do Control Plane e exige `existing_project_baseline` de avaliacao separada, mesmo run e SHA exato, com inventario de repositorio, divida herdada e jornadas criticas executados. Sem evidencia duravel, `product_complete=false` e gate humano de merge inalterado.
- Este commit trata apenas a fronteira de leitura e validação; nao cria avaliacao ficticia, nao executa scan privado do CRM, nao altera Supabase/Console e nao declara Factory globalmente pronta. Necessario CI e merge humano; Preview N/A.

## 2026-10-15 — Reconciliacao real de producao e gate funcional OIDC v2 (#822)

- `main` reconciliada em `0c206195a8b0a46105be97d64358bb5de3315642` (PR #823 mergeado por humano); `validate` de push #38667957627 SUCCESS. Vercel Console previamente READY no SHA especifico `34c614be92a544bb52c1b2634fc6c82b1be6d25e` (#811); nao atribuir nova imagem Console a merge posterior que apenas alterou Python/workflow.
- Auditoria autenticada **pre-broker-v2** #38667957692 SUCCESS: 14 telas internas, `/configuration` 390px/390px sem overflow, 0 page/console/resource errors, artefato cifrado `authenticated-console-38667957692`, registry `captured` e 1 operador restante apos limpeza. Esse run terminou antes da publicacao do broker v2, e **nao valida** o OIDC pos-deploy.
- Edge Function `factory-visual-evidence-broker` no projeto Supabase `fjplmxfcshhbmzgvyqlm` implantada separadamente com autorizacao humana: v2 ACTIVE, SHA bundle `bbcab5567036b1d883bc5362d530b3204762dfed271dc3b8a0fd243676920987`; `index.ts` remoto identico ao versionado, `verify_jwt=false` preservado por verificacao GitHub OIDC explicita. A issue #822 continua aberta ate novo teste funcional contra **v2**.
- Inventario read-only: 3 projetos, 0 runs ativos, 0 gates humanos pendentes, 10 subtarefas `queued` historicas (5 Factory, 5 CRM), nenhuma root `queued`; elas sao somente diagnostico de reconciliacao, nao despacho autorizado. Nao executar tarefas antigas nem benchmark 63.
- Este candidato de auditoria atualiza **somente o target autenticado versionado, contrato de testes e documentacao** para disparar *um novo run* pelo `push main` apos merge humano (sem Preview Console, sem nova quota Vercel, sem alteracao de policy OIDC). Confirmar status do run e do broker v2, `captured`, browser mobile e cleanup antes de fechar #822. Se qualquer passo falhar, manter aberto e corrigir o erro real. Nao marcar `product_ready` (#713).

## 2026-10-15 — Hardening da auditoria autenticada (issue #822, candidato sem deploy)

- **Observado:** `main=0a3e973f`, PR #819 mergeado com CI verde, scheduler schedule #38666112093 sucesso, sem PR aberto na reconciliacao. O Console em producao teve Vercel READY no SHA `34c614be92a544bb52c1b2634fc6c82b1be6d25e` (#811); o PR #819 nao reconstruiu Console.
- Audit run `38658173777` tentativa 1: captura autenticada chegou ao `/runs`, mas CSS `/_next/static/css/31f2df1d08145dce.css` retornou HTTP 404 e a auditoria falhou. Tentativa 2: 403 durante criacao de operador. No Supabase, `factory_visual_evidence_runs.workflow_run_id` e UNIQUE e o mesmo ID do rerun ja existia com status `expired`. Broker atual converte erro interno em 403; duplicidade e explicacao forte mas nao confirmada por log interno.
- **Correcao candidata:** proibir reruns de mesmo run ID antes de mint de OIDC/credenciais; exigir `run_id` e `run_attempt` do JWT iguais ao corpo; preflight de duplicidade antes de criar operador; recusar conflitar/sobrescrever artefato; codes de erro seguros (sem corpo PostgREST/JWT); limpeza obrigatoria mesmo se gravacao do estado captured falhar; falha visual em qualquer HTTP >=400 nas rotas autenticadas, inclusive se o console nao emitir erro. Mantem allowlist imutavel de repository/ref/workflow/environment.
- A fonte de target de auditoria estava obsoleta no commit `6353ff`, apesar do deployment #811. Agora aponta para a ultima versao de Console realmente READY `34c614be92...`. Um merge humano deste PR dispara um **novo GitHub Actions run** por mudança em workflow/target/script e portanto produz identificador novo para testar producao sem novo deployment Console. Validar logs/manifest/limpeza e mobile /configuration 390px; nao presumir sucesso.
- A Edge Function de producao tem versao 1: codigo deste candidato **nao e implantado** automaticamente na Supabase apenas por merge GitHub. Sua publicacao e gate de producao separado; comparar SHA do deploy e verificar antes de relatar backend atualizado. Sem migrations, tokens, modelo pago, auto-merge ou Preview extra.

## 2026-10-14 — candidato consolidado, scheduler nativo recuperado e UX de continuacao (reconciliacao atual)

- A `main` verificada permanece em `9eca021e3479458fb4560f35a2de5d045cc726a8` (merge humano #817). Unico PR aberto: #811; os PRs #786 e #789 foram encerrados sem merge porque seus arquivos foram consolidados em #811. O candidate anterior `eb295cd8d39d3eec6ea81c6d845fcef6d1fd517d` tinha `test`, `factory-acceptance`, `postgres-continuation` e `validate` verdes; cada novo HEAD exige novo CI exato.
- Control Plane: migration de continuation ja instalada sob `20261014192321`; `factory_enqueue_project_continuation(text,text,uuid,integer)` existe e as RPCs sao `SECURITY INVOKER`. **Nao reaplicar** migration. Nenhum job sintetico, dispatch historico, modelo pago, saldo ou permissao foram acionados nesta reconciliacao.
- GitHub Actions: duas execucoes reais consecutivas de `schedule` (#38646888441 em 22:19 UTC e #38649321800 em 22:41 UTC) concluidas com `success`, inclusive `schedule-probe` e `alerts`. As lanes de dispatch foram `skipped` porque nao houve trabalho elegivel; isto verifica o scheduler nativo, **nao** uma execucao funcional ponta a ponta. Issues #809 e #818 estao encerradas.
- Console #811: a acao `Pedir alteracao` nao deve ficar oculta devido a descendentes historicos `queued` de pais terminais. O formulario pode ser acessado; a RPC transacional continua bloqueando um novo ciclo quando ha trabalho realmente ativo. Regressao estatico-deterministica impede retornar a guarda visual por contagem bruta de tasks.
- **Gate aberto**: ainda nao existe `preview/pr-811` nem Vercel READY + Playwright autenticado no SHA candidato. Rate limit relatado em 14/10 19:42:26 UTC com pedido de retry em 24 horas; evitar tentativas repetidas. A correção do overflow mobile de `/configuration` ainda precisa de teste em browser no candidato. Nao realizar merge de producao automaticamente e nao inferir `product_ready` (#713).

## 2026-10-14 20:12 UTC — reconciliacao pos-merge #807 (estado verificado)

- `main`: `10016635fdd09a87e598220df1b7ecf733fd4d71`, merge humano #807 (issue #804 encerrada). CI de push `38629927087` = SUCCESS; sem Preview porque somente nucleo Python, testes e docs mudaram.
- #806 mergeado em `2c604bec9a98d8f3d4c386fbc9897635da66586b`. Apos merge, comando de alertas via issue #804 levou ao workflow `38628800312`, resultado SUCCESS, abrindo automaticamente issue #809 `scheduler_pipeline` por ultimo run nativo #38619635786 FAILURE. Isso valida o observador, nao o scheduler end-to-end; alerta #809 permanece aberto ate duas execucoes nativas consecutivas bem-sucedidas.
- Supabase Control Plane (read-only): 81 runs historicos; 10 tarefas `queued` (5 Factory, 5 CRM), nenhuma fila de execucao automaticamente autorizada so por essa contagem. O pager #807 protege falhas mais antigas que 200 registros, sem mudar semantica de recovered incidents.
- PR #786: head `683073dbb792aa0a0a7ccf78c2bd8e3f3f6deaa2`, CI de validacao/acceptance/concurrency verde; migration `atomic_project_continuation` ja aplicada no Supabase, registrada sob versao `20261014192321` (filename no PR `20261014160500_atomic_project_continuation.sql`). Funcao RPC confirmada; **nao reaplicar** migration. O head atual nao possui Preview SHA-exato: Vercel registrou novo `Deployment rate limited - retry in 24 hours` 2026-10-14 19:42:26Z. PR fica aberto; release gate humano permanece.
- #789: o Vercel publicou Preview READY e browser evidence no SHA antigo `a87cbb38ef2be845c51588c40c79554f098c328a`, nao no head atual `280ef04268d58ded4c399088bd44cdb5c1402fec`. Nao transferir evidence entre commits.
- PRs abertos em 20:12Z: #786, #789, #795, #798 e Dependabot #808. Auditoria global #713 segue aberta, Codex/OpenAI WIF #240/#250 dependem de integracao externa. Nenhum merge automatico nem autorizacao de producao inferido destes status.
- As notas historicas abaixo sao snapshots do instante em que foram escritas, **nao** refletem necessariamente o HEAD/CI/migrations correntes.

## 2026-10-14 — Preview #789 verified, release ordering and native scheduler alert (verified)
- Main at start of this reconciliation: `0aaac12fa82cba3b30983d004e006340c20fe350` after the **docs-only** PR #788 merged. This is not a whole-product release claim.
- PR #787 (`6c2f52b97c1b3abef6e98046b2e15c3d9a11dc5b`) fixes the manual Preview promotion eligibility bypass. `validate` passed; no Console app file changed, so Preview is not applicable. Its GitHub workflow takes effect in main only after a **human production merge**.
- PR #789 (`a87cbb38ef2be845c51588c40c79554f098c328a`) fixes Vercel's multi-commit Preview diff by extracting the ignored build decision into `apps/console/vercel-ignore-build.sh`. `validate` and `Console validation` passed; exact Vercel status and `Factory Preview browser evidence` are **success**. Actions runs: promotion 38599296055, exact verifier 38599348025, trusted browser 38599570503. PR #789 deliberately stays **draft** until #787 is human-merged; neither PR has been automatically merged.
- PR #786 (`9e9b073797188e6cafb2d4cca44e21522a0adc9c`) already passed isolated PostgreSQL concurrency, CI, Console validation and exact browser Preview but **must remain draft**: read-only Supabase verification at 16:37 UTC still showed that `factory_enqueue_project_continuation(text,text,uuid,integer)` is not installed. Production migration `20261014160500_atomic_project_continuation.sql` requires the separate human schema gate before any #786 merge.
- True native GitHub `schedule` heartbeats were recorded at 13:47 and 14:05 UTC (14 Oct). As of the subsequent 16:29 UTC review no newer native heartbeat was present and liveness warned: the alerts-only reconciler opened **#790 `scheduler_gap`**. This is not proof of healthy automatic execution. GitHub native scheduling is best-effort; manual/backup issue comments do not satisfy native liveness.
- #692 Console feedback code was merged previously, but the authenticated slow migration button remains unverified by a real operator action; do not infer operator experience solely from CI or unauthenticated browser tests. #713 whole-product readiness audit remains open.
- This note records durable evidence only; no credit purchases, WIF secret changes, database writes, paid model calls, production deployments or auto-merge.

## 2026-10-14 — Atomic continuation rollout is prepared, NOT deployed (verified)
- Main checked after #784: `bf586c51662030677b4846ddd0bec64833f54c5c`. PR #786 head `9e9b073797188e6cafb2d4cca44e21522a0adc9c` remains **draft** and unmerged. This is intentional: Console code uses a new Postgres RPC not yet installed in production.
- Candidate #786 passed `validate`, `Console validation`, and isolated PostgreSQL concurrency workflow. Exact candidate Preview reached Vercel success and `Factory Preview browser evidence=success`, via workflow runs 38596520680, 38596584976 and 38596744431. These checks prove code/Preview only, not production DB migration.
- Production Supabase read-only query at 16:18 UTC: `to_regprocedure('public.factory_enqueue_project_continuation(text,text,uuid,integer)') is not null=false`; old `factory_enqueue_project_bootstrap` does not yet contain `FOR UPDATE`. Applying migration `20261014160500_atomic_project_continuation.sql` is a **separate explicit human production gate**, then verify function signature and ACL before marking #786 ready for merge.
- New continuation now uses one transactional RPC with `request_id` idempotency and project lock, preserving historical queued children without treating them as active. The console holds private uploads on ambiguous HTTP responses to avoid deleting attachments after a possible committed request; unresolved orphan cleanup must follow verified ownership, never timeout inference.
- Independent PR #787 `6c2f52b97c1b3abef6e98046b2e15c3d9a11dc5b` has green `validate`, and prevents manual Preview promotion from bypassing the automated checks for the exact PR head and changed Console files. #787 also targets main and must respect the human release gate. Factory product readiness remains under audit #713; no whole-product completion inferred.

## 2026-10-14 - Prove two consecutive native wakes before clearing scheduler_gap (candidate)
- Factory main `db42fb7b`, CI green. A real native GitHub `schedule` run [38574669505](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/38574669505) completed at 13:47 UTC and persisted the **first** `schedule_probe.native_observed` audit event at 13:47:01 UTC. Owner-triggered manual wake at 13:45 UTC persisted only legacy `schedule_probe.observed`, as intended.
- The `scheduler_gap` alert issue #772 was automatically closed at 13:47:10 UTC despite only a single new native sample. Root cause: `evaluate_scheduler_liveness` returned no alerts whenever the latest native heartbeat was fresh and there was no `previous` sample.
- Candidate retains `scheduler_gap` until **two consecutive native observations** have been persisted with interval below the existing two-hour threshold and a fresh latest heartbeat. Absent evidence, a single sample, stale latest and a large inter-sample gap remain warning states. Legacy/manual/backup heartbeats are not valid evidence.
- Regression covers exact post-outage scenario, single recent/stale samples, valid consecutive pair, and two samples separated by a prolonged gap. No schema migration, extra cron, paid models, Preview or auto-merge; #772 historical closure must not be taken as verified restoration.
- Still needed after human merge: run the isolated alert reconciler so that a current warning reopens *as a new alert issue* (the existing alert adapter only deduplicates open issues), then observe two genuine scheduled native heartbeats in the Control Plane before declaring regularity.

## 2026-10-14 - Native scheduler provenance vs fallback (candidate)
- PR #778 merged at cc06728f with CI green; native schedule heartbeat still stale at 08:03 UTC.
- Existing backup workflow_run could emit schedule_probe.observed and clear scheduler_gap even with broken native GitHub cron. Fix writes schedule_probe.native_observed only for actual schedule events and makes native telemetry persistence mandatory, while other wake types retain the generic event.
- Liveness now reads only native evidence; tests cover native, backup, missing persistence, and source filtering. No migration, model, Preview or auto-merge.

## 2026-10-14 - Mandatory CI proof and human-only DoD identity (candidate)
- PR #776 was merged at a3504ffe and validated on main. Control Plane shows zero active Work Units/gates; scheduler-gap issue #772 remains open, with last observed scheduler probe 08:03 UTC. Factory had zero open PRs before this candidate.
- Follow-up audit proved an authorization bypass remained: a caller could mark missing `qa`, `github_ci` or any other nonhuman gate with literal `human_only: true` and the DoD evaluator would waive it. A perfectly typed empty `satisfied=[]/missing=[]` report also reached release readiness with no evidence of CI.
- Candidate whitelists the **single** human-only check `human_release` and requires `github_ci` in satisfied DoD evidence; unauthorized waiver attempts always block. All pre-existing type guards and production human merge/release gates remain.
- Six deterministic regressions cover CI spoof, review/Preview/rollback waivers, empty lists, legitimate candidate and preserved human gate. No migration, model credit, Preview, fake Control Plane tasks or auto-merge.

## 2026-10-14 - Definition of Done fail-closed input validation (candidate)
- PR #775 merged at bc42b05c with green post-merge CI. CRM #56 still has no verified candidate Preview, while scheduler-gap issue #772 remains open and no durable Factory scheduler heartbeat newer than 08:03 UTC was observed in the reconciled Control Plane.
- Another deterministic release gate bypass existed: `_missing_nonhuman` used `bool(row.get('human_only'))`, so JSON strings including `"false"` were truthy and waived mandatory missing CI/E2E checks. It also skipped malformed records and silently interpreted a missing DoD as no missing work.
- Candidate requires structured `satisfied`/`missing` lists, rejects missing/duplicate/conflicting or malformed keys, and permits only literal `human_only: true` to exempt a check from **nonhuman** gates. Malformed satisfaction evidence blocks release and cannot prove rollback. Existing literal human-only release gate semantics stay unchanged.
- Eight additional release policy regressions prove wrong types, missing payload, conflict, duplicate and migrations fail closed. No migration, model usage, Preview, gate bypass or auto-merge.

## 2026-10-14 - Enforce mandatory readiness domains and typed evidence (candidate)
- PR #774 merged into main at 9548c7ca; post-merge CI passed. No Factory PRs were open when this candidate began. CRM candidate #56 stays open and preview-unverified; scheduler_gap issue #772 stays open with latest durable scheduler probe at 08:03 UTC.
- Further audit exposed two bypasses in the underlying full-product assessment: all six domains could claim `not_applicable` with plausible reasons/evidence and become ready; evidence list items were coerced with `str()`, so malformed objects, booleans and numbers could appear as accepted evidence. A single malformed coverage entry could also be ignored while other keys made the coverage set pass.
- This patch requires five always-applicable domains (security, observability/operations, test strategy, documentation, functional completeness) to be passed with evidence; only headless product experience may be `not_applicable`. Evidence and coverage containers/items must be actual lists of strings. Invalid identities fail closed.
- Adds direct evaluator and release-report regression scenarios to prove impossible all-N/A product completion and reject malformed evidence; preserves valid headless exception and separate human merge gate. No migrations, paid model calls, Preview or auto-merge.

## 2026-10-14 - Exact-candidate whole-product audit enforcement in release reports (candidate)
- Reconciled Factory PR #773 merged at ca8b4e51 with green main validation and OIDC preflight on push. The contingency is installed, but its new scheduled conditional has not yet been verified in a scheduled GitHub Actions run; #772 remains open. No Factory PRs existed before this candidate.
- Found a deterministically reproducible completeness bypass: `build_release_assessment` trusted a summary `product_readiness.ready=true/status=passed` with matching SHA and no six-domain evidence. This contradicts PRODUCT_READINESS.md and can falsely label the CRM or any incomplete application as `product_complete=true`.
- Candidate validates the entire product assessment using the existing `assess_product_readiness` (domains, coverage, evidence, verification state and blockers) before setting the global completion flag. Missing/malformed records, omitted essential coverage and false baseline_ref aliases fail closed; existing passing complete assessments retain true.
- Candidate preserves release-policy/human-production gates unchanged: passing product-readiness does NOT authorize merge or Preview exceptions. Deterministic regression tests cover forged summaries, gaps, blockers, stale candidates and legitimate full assessments. No DB migrations, model usage, preview deployments or auto-merge.

## 2026-10-14 - Scheduled OIDC preflight as conditional alert-only fallback (candidate)
- Latest merged main: PR #771 at 05254efb, CI successful; issue #754 was closed by the official owner-triggered alerts job, and issue #772 opened with a genuine scheduler_gap. Live runner `schedule` runs succeeded when delivered, but the cadence was irregular; GitHub's official docs state scheduled events may be delayed or dropped. Repository is public, active, default branch main, and existing Cron is already offset at minutes 17/47.
- Supabase `pg_cron`/`pg_net` extensions and `cron.job` are not installed, so no external scheduler was silently provisioned. An actual independent wake for full execution would require a separate trusted runner/provider and explicit GitHub authorization; do not insert production credentials or expand access without a real gate.
- Existing `Control Plane OIDC preflight` has a separate six-hour `schedule` and can authenticate with OIDC. This candidate adds a read-only durable heartbeat check to that **existing job**, and adds a least-privilege alerts-only job **only when** the last heartbeat is stale/gapped, avoiding any extra Cron entries or charged idle backup runners. Scheduled preflight job continues testing its normal read.
- Fallback uses normal authenticated `runtime_cli --mode alerts`, remains dependent on GitHub scheduling, and has no model/Codex, lease recovery, dispatch, Preview or release capacity. It is a backup notifier, not proof of a reliable autonomous scheduler.
- CI contract tests check the exact six-hour Cron, conditional gate, token scopes and absence of model/worker capabilities. No migrations, paid service, quota purchase, deployment or auto-merge. Merge to production requires human gate.

## 2026-10-14 - Owner-only issue-comment operational alert wake (candidate)
- Reconciled PR #770 merged at 56efb554, green main CI; zero open Factory PRs, issue #754 still open. Durable scheduler telemetry has not advanced beyond 08:03 UTC despite expected best-effort wakes, so an in-run liveness detector cannot independently fire.
- The current `/factory-wake` issue-comment command can trigger general scheduler and execution lanes; using it to reconcile a stale alert risks unrelated work. Candidate adds exact owner-only `/factory-alerts` command on GitHub **issues** (not PRs) routed to a standalone, least-privilege `alerts-owner-comment` Actions job with protected Control Plane OIDC and explicit fail-closed readiness check.
- The new job runs only `runtime_cli --mode alerts`: no recovery, probe, backlog dispatch, Primary/Codex, CI, Preview, or release. The previous schedule and workflow_dispatch paths remain unchanged; offline graph/guard tests verify all other jobs are dependent on a schedule-probe that excludes this command.
- After human merge, issue #754 may receive one trusted `/factory-alerts` comment via the connected GitHub account, then verify the exact Actions run, issue lifecycle, and Control Plane evidence. This is an operator recovery hook, **not** an independent uptime SLA or guaranteed background service; the GitHub Actions platform remains a dependency. No paid calls, fake jobs, new migrations or auto-merge.

## 2026-10-14 - Durable scheduler wake-gap monitoring (candidate)
- The Control Plane observed scheduler probes at 07:42 and 08:03 UTC, then none before reconciliation at 11:08 UTC. Prior to that, probes had a 5.5-hour gap. The GitHub schedule is explicitly best-effort, and CI passing does not prove continuous autonomous operation.
- This candidate reads at most the newest two persisted `schedule_probe.observed` event timestamps. It warns on a latest observation older than two hours, a prior inter-probe gap of two hours or more, or zero evidence. Reads require consistent timestamps/timezones and fail closed if malformed.
- The warning is a deduplicated `scheduler_gap` operational GitHub Issue, evaluated along with other alerts; it neither changes the scheduler nor enables extra wakeups. Importantly, it **cannot notify while the runner itself is not executing**: detection happens only on the next successful alert evaluation or separately initiated alerts-only wake.
- Tests cover expected cadence, stale last wake, recovered gap, cold-start, malformed/future timestamps, issue lifecycle and read-only GET. No paid calls, migration, preview, storage changes, or auto-merge.

## 2026-10-14 - Read-only reconciliation of queued task records (candidate)
- Live Control Plane inspection: 10 `factory_tasks.status=queued` (Factory 5, CRM 5); all have terminal completed parents and zero active Work Units. All current Change Sets are completed or superseded; scheduler's authoritative runnable signals remain false.
- New bounded read-only backlog audit distinguishes old queued descendants without active units, queued tasks with active units and other queued entries. It never treats an inventory row as dispatch approval, does not reactivate historical tasks and fails closed on truncated/malformed data.
- CLI `--mode backlog-audit` can be run independently; the scheduled runner logs the audit only when its normal work probe detects no active work. An audit failure cannot suppress normal scheduler/alerts processing.
- Regression covers existing history shape, empty inventory, real active unit, ambiguous root, parent missing/cross-project, duplication and 100-row boundary. No Supabase DDL, Primary/Codex calls, synthetic work, Preview or production merge.

## 2026-10-14 - False stale-preview alert from historical CRM audit runs (candidate)
- Factory main 33123604 / Supabase reconciled: two aged `preview_ready` records for CRM exist with completed tasks and `source=dogfood_manual_audit`, not delivery Preview runs. Issue #754 arose because OperationalHealth counted these audit rows despite the Preview queue filtering them out.
- Health now uses the same delivery provenance predicate, scans a separate oldest-first `preview_ready` status partition, refuses >200 rows and invalid delivery timestamps, and leaves genuine overdue deliveries actionable.
- Regression covers real audit provenance, old/fresh deliveries, newest-history starvation, overflow and missing timestamps. Read-only; no synthetic work, Preview, migration, model spend or historical run mutation.
- Issue #754 is not closed by this PR. Let the existing alerts observer verify the Control Plane after human merge and reconcile the marker safely.

## 2026-10-14 - Cross-agent hierarchical scope claim race (candidate)
- #765 merged at 1fb5fde8 with both validate and PostgreSQL claims workflows green after merge. No active runs, Work Units or pending human gates in the Control Plane. Previous Codex migrations are recorded.
- Inspection of the versioned and installed allocator found a cross-agent race: agent row locks serialize a single agent, but two agents can independently observe zero scope conflicts for overlapping project paths and both insert before either commits. A unique constraint on an exact key cannot cover hierarchical path overlap.
- Candidate updates factory_claim_agent_slot to hold a transaction-scoped advisory lock derived from project ID only for nonempty scope arrays, before the conflict-read/insert. Existing scope, capacity, agent and role policies stay intact; advisory hash collisions only over-serialize and cannot grant access.
- PostgreSQL CI replaces the simulated allocator with the two real versioned allocator RPC definitions; expands coverage for cross-agent overlapping scope contention, allowed sibling scopes, agent concurrency and invalid-scope rollback. No production migration applied yet; no synthetic Control Plane work, model, Preview, paid auth or automatic merge.
- Remaining limitation: the test database is an explicit minimal schema fixture, not a copy of production. Full product lifecycle readiness is not implied.

## 2026-10-14 - Isolated PostgreSQL Codex claim concurrency CI (candidate)
- PR #764 merged at c4df4609; post-merge CI succeeded, and Supabase migration codex_claim_agent_hardening was applied and verified (three service-role-only RPCs; no queued Codex runs). No Factory PR was open before this candidate.
- The earlier SQL string-contract tests did not execute two simultaneous database transactions. This candidate adds an isolated PostgreSQL 16 GitHub Actions workflow running the actual current manual and automatic claim functions, automatic scheduler, and work-matrix SQL (no production Control Plane writes).
- Coverage: competing auto/auto and manual/manual transactions with held row locks; manual vs automatic separation; untagged legacy and wrong-route rejection; exact agent, active project, required tools/capabilities, queued Work Unit; work-matrix eligibility; RPC execute ACLs. A clearly labeled fixture replaces the generic allocator, so tests do not prove production allocator scope-lock behavior.
- Guard: script refuses non-local host, wrong database name or missing isolated opt-in; workflow runs on relevant files only. No migration, model credit, Codex auth, production job, Preview or auto-merge is changed.
- Results must come from exact PR CI; green text checks alone are not concurrency evidence.

## 2026-10-14 - Codex automatic claim agent identity/capabilities (candidate)
- Reconciled main `eb043896`, green post-merge CI, zero active Work Units, runs, assignments and gates. Supabase migration `codex_atomic_mode_isolation` was applied and audited: seven route RPC signatures/ACLs validated, old dispatch revoked from service_role, queue signals all false.
- Follow-up hardens automatic Codex at three SQL boundaries: scheduler requires both `codex` and `github_write` and checks the allocator's exact agent; claimer re-checks agent tools, task capabilities, active project, and matching agent key under row locks; work matrix only advertises eligible Codex assignments. Client guards reject unexpected run/agent IDs.
- Migration `20261014032600_codex_claim_agent_hardening.sql` is **not applied**, pending human PR merge. SQL contracts and mocked client tests do not claim true concurrency validation. No paid calls, fake production tasks, Preview deployments or automatic merges.

## 2026-10-14 - Mode-aware Codex scheduling candidate
- #761 merged; candidate adds atomic mode stamp, separates competing manual/automatic claims, schedules automatic Codex by exact run and independently guards cost. Database migration unapplied; no paid call, credential activation or production release performed.

## 2026-10-14 - Codex competing-claimer guard (candidate)
- #760 merged as 3d136da7 with green main CI. No active/queued Codex
  runs or agent slots in the live Control Plane.
- Post-merge audit found a safety defect: the legacy manual Codex RPC
  accepts all queued Codex runs, while the new automatic Codex path has no
  agent assignment. The two modes are not durably isolated.
- Candidate refuses new automatic Codex claims until both claimers use
  an atomic execution-mode discriminator. Official Codex WIF/token
  readiness improvements remain, and existing manual handoffs remain.
- No migrations, paid-model calls, fabricated work or automatic merge.
- Follow-up needed: atomic SQL split for claim modes + route-specific
  agent scheduling with offline concurrency tests.

## 2026-10-14 - Codex route and auth parity (candidate)
- Factory main bff9c298, post-merge CI green; 9 SQL scheduler signals
  installed and reporting no active Control Plane work.
- Discovered automatic Codex would never dispatch if Primary was disabled:
  the preclaim allowed only Direct or the manual fallback, not automatically
  authenticated Codex. Separately the Codex CLI producer supported the
  official access-token fallback, but the runtime rejected it before claim.
- Candidate adds a protected no-model configuration preflight in
  openai-codex, outputs only a boolean to dispatch, permits exact Codex route
  independently of Primary, and aligns runtime WIF/official access-token
  checks (partial WIF fails closed).
- Neither WIF nor token is auto-enabled or verified by a paid call here.
  Actual authentication remains subject to an independent operator preflight
  before Codex activation. No production merge or deployment was performed.

## 2026-10-14 - Downstream wakeup signals (candidate)
- #758 merged at c5a882c9 with post-merge CI green and
  `factory_scheduler_queue_signals` installed as 20261014000254.
- Integration, CI, specialists and release remained vulnerable to bounded
  REST sampling of long queues. Candidate extends the same read-only RPC
  to nine signals, with strict runtime validation, regression fixtures and
  no changes to Preview or production merge gates.
- Migration not yet applied; no paid model call or fake product job.

## 2026-10-13 - Indexed PostgreSQL scheduler signals (candidate)
- PR #757 merged as 88bf8c54; CI post-merge green. Read-only Control
  Plane returned no active Work Units, runs, agent slots or gates.
- Even two bounded oldest/newest 200-row windows can miss a runnable
  middle-of-queue run. This patch moves product/routed/manual Codex queue
  existence predicates to a service-only, read-only PostgreSQL RPC,
  leaving REST windows for diagnostics only.
- Migration must be applied after CI + human merge; until then the
  probe fails closed and intentionally does not wake workers. Tests use
  over 400 queued historical run fixtures, no model call or real task.
- No quota change, new credentials, Preview, data deletion or auto-merge.

## 2026-10-13 - Bounded newest/oldest wake and linked task lookup (candidate)
- PR #756 merged at 0d7f6acc; post-merge CI green. No pending runs,
  Work Units or human gates in the Control Plane.
- Status partitions fixed cross-status starvation but still sampled only
  the oldest 200 rows per state. A queue with 200 manual Preview audits
  could hide the newest delivery Preview. Also, independently capped
  queued_execution tasks could obscure a selected queued Direct run's task.
- Candidate adds bounded newest-run sampling on capped partitions, read-only
  task-ID join completion, strict validation, and truncation telemetry.
  Regression fixtures cover both blindspots and malformed responses.
- No paid models, migrations, new tasks or production merge were performed.

## 2026-10-13 - Status-partitioned scheduler work detection (candidate)
- PR #755 merged as aad8d484, post-merge CI green. Supabase still has zero
  pending Work Units, active runs/gates and assigned agent slots.
- Found a scheduler liveness bug: the oldest 200 runs across all statuses could
  consist of manual Preview audits, hiding a newer queued Direct run. Likewise,
  200 queued historical tasks could obscure a queued_execution task.
- Candidate queries each status under its own cap, deduplicates transient ID
  status transitions and reports capped partitions in sanitized telemetry.
  The work eligibility/Preview policy, Primary ledger, and production gate
  are unchanged. Regression tests use 200 historical Preview and queued tasks
  without any paid call, migration or production write.

## 2026-10-13 - Route-isolated recovery candidate
- Read-only audit: no pending Work Units, active runs, gates or agent slots. Last Direct scheduling migration is applied.
- Legacy recovery performed unscoped `schedule_next()` for Direct or Codex without executor readiness, potentially reserving Codex manual slots. Unscoped Direct/Codex workers could do the same.
- Candidate removes all assignment side effects from recovery, isolates each optional worker to existing route-specific assigned work, and leaves allocation of Direct work to the Primary/ledger-gated dispatch path. No Primary, Codex or paid-model activation; no database migration.
- Validate CI and acceptance before human merge. No full E2E delivery is asserted.

## 2026-10-13 - PR #753 expanded to cover approved Direct resumption
- PR #753 was open/CI-green on `27594509`, but further review found a
  possible agent slot reservation before human gate approval and a lack of
  route-safe resumption after an approval or capacity recovery.
- The candidate adds a new fail-closed `security invoker`, service-role-only
  Direct scheduling RPC with exact ID or eligible queued fallback. The
  dispatcher uses it for initial Direct assignment and bounded safe recovery.
- No manual Codex agent is reserved, and owner-comment wake now covers
  Codex manual preparation. Full E2E remains unproven.
- SQL migration not yet applied. No paid calls, secret changes, Preview or
  production merge were performed; re-run CI before human gate.

## 2026-10-13 - Exact-run scheduling and unstaffed manual Codex (candidate)
- PR #752 merged at 27a13e1c with green post-merge CI.
- The dispatch worker still called `factory_schedule_next_unassigned_run` globally
  after each atomic claim. That could reserve an agent for a different queued
  run (including a new manual Codex handoff), leaving the claimed Direct
  implementation unassigned and consuming slot capacity while waiting for
  manual work.
- Candidate propagates the atomic run ID in DispatchDecision, schedules Direct
  only via the exact run ID, and skips assignment for manual Codex. Dispatch
  wakes manual Codex via the newly claimed route rather than the work matrix.
- No database schema changes, model calls, credentials or automatic merge.

## 2026-10-13 - Codex manual fallback consistent default-off (candidate)
- Confirmed the production route-aware migration at version 20261013222158; the read-only peek returns no eligible Factory/CRM Work Units. No new runs or gates were created.
- Found split readiness: dispatcher required exact `FACTORY_CODEX_MANUAL_FALLBACK_ENABLED=true`, but manual handoff preparation defaulted unset configuration to enabled and GitHub Actions used `!=false`.
- Candidate makes preparation default-off in both Python and workflow while leaving followup of existing handoffs independent; validates Issue run marker and bound Issue number before transitioning state. Added offline regression tests.
- This does not enable Codex WIF, spend Primary credits, apply migrations, open new product tasks, or authorize a production merge.

## 2026-10-13 - Fix malformed but unapplied route-aware SQL
- PR #750 was merged with green CI, but subsequent source review found an unterminated fingerprint regex plus orphan SQL copied outside the function. The migration was **not** installed in production.
- This patch repairs the SQL without changing its original versioned filename, and adds structural tests for exact PL/pgSQL body boundaries and matched quotes. CI must pass before a new human production merge; only then apply and verify the versioned migration.
- The Factory still has zero pending Work Units; no historical job has been reactivated and no paid model was called.

## Reconciliation 2026-10-13 - Atomic route-aware Codex preclaim (candidate)
- PR #749 merged at eddc9bf4; candidate CI passed. The prior preclaim guard
  blocked ALL new planned dispatch when Primary was off, including Codex-only
  work, because the route was selected only after a database claim.
- This PR adds read-only Work Unit preflight and an exact-fingerprint atomic
  commit with a route decision; it revokes service_role access to the blind
  legacy dispatcher. No stale task or duplicate Work Unit may be claimed.
- Direct readiness still needs Primary API authentication and known cost.
  The independent Codex path is limited to explicitly enabled zero-model
  manual handoff while automated Codex is off. It never invents WIF values,
  skips production merge gates, or grants new public database permissions.
- This is an un-applied migration candidate, not proof of live autonomy.
## Reconciliation 2026-10-13 - dispatch executor preclaim (candidate)
- PR #748 merged at c7af3f32 with green CI; schedule now requires real Work Units.
- Previously the dispatch RPC could claim tasks before verifying that an executor
  was ready. A disabled paid Direct worker then left routed runs stranded.
- Candidate: product-stage preflight in protected environment also covers
  dispatch-only work without calling the model. Dispatch receives only a boolean,
  checks the explicit Primary flag and real known-cost ledger budget before claim.
  No model credentials enter the dispatch job. Blocked readiness yields no claim.
- Already-routed Codex/manual handoff is unchanged. Route-safe new Codex dispatch
  while Primary is disabled requires a future transactional preclaim capability.
- No paid calls, credential changes, Preview, auto-merge, migration, or production
  deployment occurred. CI and human production merge remain required.
## Reconciliation 2026-10-13 - Same-run product-to-dispatch signal (candidate)

- PR #747 merged at `cc466d68`; CI post-merge passed. The Primary enable flag remains explicit/default-off; no paid model request or GitHub variable activation was performed.
- Found workflow race/false wake: `dispatch` was triggered on the **initial** `product_work` signal even when product execution was blocked, skipped, or produced no runnable Change Set. A successful product-stage job is not durable work evidence.
- Candidate introduces a strict claimed+completed product result and a second read-only queue probe only after actual product completion; dispatch then wakes solely on actionable `dispatch_work` from the initial or freshly observed state. Supports same-run planning -> execution without reintroducing phantom work. Adds static and dynamic unit coverage; preview/release boundaries unchanged.
- This workflow correction is **not** end-to-end autonomous delivery proof and does not turn on Primary, Codex, Vercel Preview, or auto-merge.

## Reconciliation 2026-10-13 - Primary-model activation wiring (candidate)

- Post-#746 Control Plane read confirms the corrected portfolio RPC returns `[]` with zero active Change Sets and no pending Work Units; the historical CRM PR #19 was durably reconciled. No new autonomous work should be manufactured.
- The production autonomous-runner workflow still hard-coded `FACTORY_PRIMARY_MODEL_ENABLED: "false"` in both `product-stage` and `direct`, which prevented any new Primary-dependent intake/implementation regardless of documentation stating earlier API budget approval. This PR makes the flag explicitly controlled by an admin-owned GitHub variable with **default off**; it does not set the variable.
- Fixed per-job US$ 4.00 budget and US$ 0.50 reservation, server-side ledger/unknown-cost preflight, API auth, GitHub App isolation and all release/Preview gates remain intact. No model call or paid test was performed. The real Primary execution state remains **unverified** until the variable/configuration is audited and a genuine bounded run finishes.
- An in-memory planning -> team plan -> materialization -> Definition-of-Done contract regression exercises the deterministic segments without calling an external model, opening PRs, or deploying.

## Reconciliation 2026-10-13 - Portfolio dispatch truth (candidate)

- Read-only production check after #745 migrations: `factory_portfolio_candidates(20)` still returned both Factory and CRM even though zero pending Work Units and zero active/planned Change Sets existed. Historical `plan-*` queued task titles were the sole eligibility cause.
- Candidate migration `20261013212000_align_portfolio_with_dispatcher.sql` removes historical queued-task eligibility and requires exactly the dispatcher claim guards: latest ready team plan, planned/building Change Set, current-wave pending unit, queued task, no prior execution and no duplicate consumed unit. Keeps P0 incident priority, paused project and worker capacity policies.
- Manual product-audit `preview_ready` rows no longer count against the dispatch concurrency budget. Scheduler wakeup now needs both pending unit hint **and** a portfolio-eligible project; already-routed work remains independent. Adds no-cost regressions and bounded diagnostics.
- **This migration is a proposal**: production application requires a human gate and verified CI; do not infer end-to-end autonomous delivery from a clean queue.

## Reconciliation 2026-10-13 - Closed PR durable terminal transition (candidate)

- Live evidence: CRM PR #19 was closed unmerged on 2026-10-07; run d8ed0c24 remains preview_ready and Change Set a9d67bad remains ci_pending, with two already integrated Work Units. Those Work Units and the completed root task are immutable in this correction. Manual dogfood product-readiness audit rows are intentionally excluded from delivery.
- PR candidate adds a service-role-only transactional RPC that requires matching run, source, candidate SHA, PR number, latest durable PR evidence and exact Change Set binding; refuses pending human gate, released report, merged PR and state races; on verified closure records cancelled run + superseded Change Set with durable audit and idempotence.
- Runtime Preview probe marks a verified closed/unmerged candidate as reconciliation-only, without installing browser or initiating Vercel Preview. Executor does only the audited RPC, with no release merge capability.
- This migration remains **unapplied** until explicit production migration gate. The 24-hour quota cooldown still suppresses scheduled selection until its expiry; no attempt is made to bypass Preview quota, and no E2E recovery is claimed.

## Reconciliation 2026-10-13 - Preview queue eligibility (candidate)
- CRM PR #19 closed without merging on 2026-10-07 as superseded; its historical Preview run still held a 2026-10-13 quota-blocked deployment. Two additional Preview-ready records were manual dogfood product-readiness audits, not delivery PRs.
- Bounded Preview queue selection now skips manual audit-only runs and applies 24-hour quota cooldown to exact run+candidate SHA, avoiding oldest-run starvation. Schedule probe uses the same eligibility predicate. Closed/merged PRs never pass Preview probe or deploy execution.
- No database rows have been rewritten and no historical PR was reopened; durable terminal-state reconciliation remains separate. Preview and human release gates remain fail-closed.

## Reconciliation 2026-10-08 - stale Preview target hardening
- Console browser evidence #65 proved that the GitHub-hosted Chrome path works, but the verifier consumed the historical `.github/preview-target.json` from PR #434 and received HTTP 410 GONE.
- The trusted verifier is now manual-only and requires an explicit current Vercel URL; the stale source-controlled target file is removed.
- Exact Preview and cross-repo workflows remain responsible for resolving the URL from current GitHub/Vercel evidence before dispatching the trusted verifier.
- Regression tests prohibit reintroducing a static Preview target or an automatic push trigger on the trusted verifier. HTTP 410 remains a failure and the browser gate stays fail-closed.

## Reconciliation 2026-10-08 - browser runner hardening
- Autonomous runner #203 was cancelled while `playwright install --with-deps chromium` spent the job window downloading Ubuntu packages; schedule probe and Control Plane claim had succeeded before that point.
- GitHub-hosted Ubuntu 24 already provides Google Chrome. The candidate browser hardening reuses `/usr/bin/google-chrome`, keeps Playwright pinned, skips browser download, and fails closed if the executable is unavailable.
- The same browser runtime contract is applied to the scheduled Preview worker and the trusted Console browser verifier.
- This does not weaken Preview applicability, exact-SHA evidence, Trusted OIDC, or the human production merge gate.

## Reconciliation 2026-10-07 - Preview usage dogfood
- Dogfood with a non-Console `preview/**` branch exposed an unnecessary Exact Preview/browser run even though Factory policy requires Preview only for `apps/console/**` changes.
- The corrective candidate scopes automatic `exact-preview-browser-evidence.yml` pushes to `apps/console/**` and aligns `apps/console/vercel.json` so Preview branches with no Console diff are ignored.
- Explicit manual exact-Preview verification remains available; production `main` keeps release-policy-file awareness.
- This is a usage/cost hardening only. It does not relax fail-closed Preview semantics when Preview is actually applicable and does not alter the human production merge gate.

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

## Reconciliation 2026-10-13 - planning-to-dispatch safety candidate

- Read-only SQL inspection: CRM Change Set a9d67bad-99fc-4d42-b63b-ef3d02c45753 has two integrated work units and remains ci_pending. Factory historical sets are completed/superseded. Historical queued plan-* tasks do not imply runnable work.
- Migration 20261013203000 guards repeated materialization, already executed tasks and stale plan dispatch. It is a **candidate** only: a production database migration requires the human gate.
- GitHub App HTTP 403 diagnostics are bounded and fail-closed; PAT fallback remains prohibited for blocked App access. Edge Function changes require an explicit controlled deployment.
- Verify a real fresh team plan -> Change Set -> Work Units -> CI/Preview -> release gate before calling the autonomous loop recovered.
