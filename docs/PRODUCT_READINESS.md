## 2026-10-15 — CRM pinned GitHub tree inventory (#713)

A new read-only GitHub API collector checks repository identity, open CRM PR #56, exact head SHA and complete commit tree, then emits only count-based `inventory_only` evidence. It runs as an added step within the **already broker-allowlisted** `crm-cross-repo-preflight.yml` in trusted Factory `main`, after a human merge or explicit workflow dispatch, using the same existing OIDC/GitHub App credential. A separately created workflow was rejected during security review because it would have received HTTP 403 from the broker OIDC workflow allowlist; this design does not expand that allowlist or deploy a new Edge Function. The artifact contains no source contents or tokens; the job fails closed on stale PR, truncated tree, unsupported symlink/submodule or missing cross-repo authorization. It never records a passing `factory_evaluations` baseline or changes the CRM database.

The GitHub API preflight found 961 tracked files, 558 sources, 136 test files, 79 migrations, one workflow and 52 route files at `f5f7d91f8e98cfaf482cca72c974abb7a82f6a5e`. These are inventory counts, not evidence of inherited debt review, tenant RLS, remote E2E or product readiness. The CRM database remains unavailable in the connected Supabase account. Further E2E and target database checks are still required.

## 2026-10-15 — Coletor de inventario existente sem falsa aprovacao (#713)

O comando `python -m ai_product_factory.existing_project_inventory --repo-path /checkout --candidate-sha <40-hex-sha> --repository owner/name` faz uma leitura **apenas da arvore Git commitada** na HEAD local. O SHA deve coincidir exatamente; repositorio ausente, diretório aninhado, identificadores malformados, arvore grande ou caminhos inseguros falham fechado. Relata **somente contagens** de fontes/testes/migrations/workflows/rotas e presenca de runbook de dívida, sem ler conteudo/secret de arquivos.

A saida JSON carrega `status=not_assessed`, `verification_state=inventory_only`, `coverage=["repository_inventory"]` e blockers explicitos para divida herdada, journeys autenticados, identidade remota GitHub e schema/RLS de producao. **Nao** escreve `factory_evaluations`, nao afirma `existing_project_baseline=passed`, nao prova que os dados do CRM estão corretos e nao autoriza release. Mesmo forçando indevidamente `evaluation_status=passed` ao consumir a saida, o verificador de prontidao continua a rejeita-la por ausencia de `verification_state=executed` e evidencias complementares. Testes exercitam checkout fixture real, SHA incorreto, paths nao confiaveis, comando e redacao.

A proxima fase exige checkout autorizado do repo existente em executor confiavel, auditoria separada da divida herdada, validação RLS/migrations no banco real CRM (nao presente no conector atual), E2E autenticado do Preview no SHA exato e uma avaliacao duravel ligada ao run que passou os gates. O coletor nao requer chaves, serviços novos, modelos pagos ou Preview Vercel.

## 2026-10-15 — Existing-project whole-repository baseline is independent (#713)

The trusted release reader now loads `factory_projects.project_kind` using the `project_id` returned by the Control Plane RPC, not from an evaluator's `result` JSON. Missing/ambiguous project identity prevents a full-product `product_complete=true` claim. Delivery and the human release gate are unchanged.

For `project_kind=existing`, a six-domain passing `product_readiness` row alone is **not** a full-product sign-off. The same run must also contain a separately recorded `factory_evaluations` row with `eval_type=existing_project_baseline`. The independently selected columns must include `status=passed` and `baseline_ref` equal to the exact candidate SHA. The row's `result` requires `assessed_commit` matching that SHA, `verification_state=executed`, a **real empty array** of `blockers`, non-empty text `evidence`, and coverage keys `repository_inventory`, `inherited_debt` and `critical_journeys`. Self-declared baseline fields inside the normal product-readiness payload cannot substitute for this independent row.

This is a conservative **evidence acceptance boundary**, not an automatic baseline generator or proof that a cited audit actually ran. Assessment producers must perform and store the complete repository scan separately; no fabricated synthetic passing record is written to the Control Plane. In particular, the existing CRM's recorded product-readiness evaluations remain `failed`, and the Factory's global product readiness stays unproven. A later GitHub identity/HEAD verification is still needed before calling an assessment current.

Only Python core, read-only Supabase release facts, deterministic tests and docs change in this patch. No schema migration, policy relaxation, paid-model invocation, new Vercel Preview, or production auto-merge.

## Release report: durable evaluation row is authoritative (2026-10-14 #713)

A release report that says `product_complete` must corroborate the six-domain assessment against the *durable* `factory_evaluations` row. A `result` JSON containing `ready:true`/`status:passed` does **not** override a row with `status:failed`, an absent row, or a mismatched `baseline_ref`. The read boundary `SupabaseReleasePolicyStore.facts` supplies `evaluation_status` and `baseline_ref` from separate selected columns, and the deterministic `_verified_product_assessment` requires `evaluation_status == 'passed'` and `baseline_ref == candidate_commit` in addition to exact `assessed_commit` and all six domain proofs. Missing or malformed provenance is fail-closed. This never changes the independent human production release gate.

This is **not** an authoritative check of the repository's current HEAD: `candidate_commit` is the release candidate supplied by the trusted release workflow, whereas a separate GitHub identity/read is needed to assert that it is the current repo HEAD. Do not promote the scope of this report to global product readiness. No migration, credential expansion, model call or Vercel Preview is needed for this Python-core guard.

## Exact commit evidence for product readiness (14/10/2026)
The deterministic core rejects a passing `product_ready` assessment when `assessed_commit` is missing or is a branch name, abbreviated SHA, malformed hash or padded value. It accepts a canonical full 40-character Git SHA-1 commit and normalizes uppercase hex to lowercase for evidence. An invalid, nonempty string yields a `not_ready` result with an explicit blocker instead of crashing release intelligence, so no release policy can infer whole-product completion from ambiguous identity. Empty/non-string commit identities remain invalid inputs.
This is **only a format check**, not proof that the commit exists remotely, belongs to the project's repository, or is its current HEAD. That requires separate trusted GitHub identity and exact-head verification; it does not replace verified CI, Preview/browser evidence, production human release gate or a global audit. No Supabase migration, provider call or Vercel deployment is required for this Python-core regression.

# Product Readiness Contract

Last updated: 2026-10-07.

## Why this exists

The Factory previously had an ambiguity: a green task/release path could be described conversationally as if the entire product were complete. That is unsafe for an app factory because local delivery evidence does not prove global product readiness.

This contract makes the scope explicit and fail-closed.

## Readiness scopes

| Scope | Meaning | What it does NOT mean |
| --- | --- | --- |
| `work_item_complete` | The current task/change set satisfied its acceptance criteria and evidence. | The app is complete. |
| `release_candidate_ready` | The exact candidate SHA passed the applicable release gates and can wait for human production release. | The product was globally audited. |
| `release_completed` | A human production release was observed and reconciled. | The whole product is secure, operable and finished. |
| `product_ready` | A current full-product audit passed all required product readiness domains with no critical blockers. | Permanent perfection; future changes can invalidate readiness. |

The Factory must never infer `product_ready` from CI, Preview, a merged PR, a completed task, zero pending gates, zero open issues, or a successful release alone.

## Required evidence for product_ready

A product can be called ready only when a full-product assessment has current evidence for all applicable domains:

1. **security** — authn/authz, tenant/data access boundaries, secrets and dependency/supply-chain boundaries;
2. **observability_operations** — health/readiness, traceability, recovery and alerting;
3. **test_strategy** — representative unit/integration coverage, critical E2E and regression gates;
4. **product_experience** — full surface inventory, responsive coverage, accessibility and loading/error/empty states for products with a user interface;
5. **documentation** — setup/configuration, operations and release/rollback guidance;
6. **functional_completeness** — requirements inventory, mock/no-op/demo inventory and critical journeys.

A domain marked `passed` must provide all of:
- at least one non-empty evidence reference;
- explicit `coverage` entries for every required dimension of that domain; and
- an explicit `verification_state` proving how that evidence was validated.

Allowed verification states are domain-specific:
- `security`: `executed` or `reviewed`;
- `observability_operations`: `executed` or `observed`;
- `test_strategy`: `executed` only;
- `product_experience`: `observed` or `reviewed`;
- `documentation`: `reviewed`;
- `functional_completeness`: `executed`, `observed`, or `reviewed`.

For `test_strategy`, a configured workflow that did not execute for the assessed SHA is not evidence. A `not_applicable` domain also requires an allowed verification state and non-empty evidence.

This is deliberate. Evidence such as "reviewed", one screenshot, one green PR or one manually inspected screen is not sufficient to prove a whole-product domain. The coverage contract forces the assessment to say what was actually checked.

Only the **product_experience** domain may be marked `not_applicable`, and only when a product genuinely has no user interface, with reason, evidence and an allowed verification state. Security, operations, test strategy, documentation and functional completeness cannot be waived as entire domains. For example, a headless service still requires real security and test evidence.

Evidence and coverage entries must be strings; non-text values or malformed containers never count as verified evidence. Claiming a `ready=true` summary cannot override those deterministic checks.

If a domain is genuinely not applicable, that non-applicability must be explicit and evidenced with a reason; silence is not a pass.

## Coverage keys

| Domain | Required coverage |
| --- | --- |
| security | `authn_authz`, `data_access_boundaries`, `secrets_dependencies` |
| observability_operations | `health`, `traceability`, `recovery_alerting` |
| test_strategy | `unit_integration`, `critical_e2e`, `regression_gates` |
| product_experience | `surface_inventory`, `responsive`, `accessibility`, `states` |
| documentation | `setup_configuration`, `operations`, `release_rollback` |
| functional_completeness | `requirements_inventory`, `mock_noop_demo_inventory`, `critical_journeys` |

Project-specific automated audits are encouraged as evidence but are not universally hardcoded. A headless service may mark product experience not applicable with explicit rationale; a UI product cannot skip responsive/accessibility/state coverage just because CI is green.

## Existing-project rule

Imported/existing projects require a baseline audit before the Factory may make a global completion claim. The audit must look beyond the current change scope because inherited debt can exist outside changed files.

The CRM dogfood demonstrated why: multiple manual UI passes still left hundreds of mechanically detectable surface issues until the repository was scanned globally. Readiness evidence therefore needs coverage, not merely a positive assertion.

## Release report proof boundary (14/10/2026)

A release report must re-run the deterministic six-domain evaluator against the
complete product audit payload for the **exact** `candidate_commit`. Merely
supplying `product_readiness.ready=true`, `status=passed`, `baseline_ref`, or
a matching SHA without domains, coverage and verification evidence cannot set
`product_complete=true`. Declared critical blockers must also be checked.
Malformed/missing evidence produces `product_readiness.status=not_ready`, while
a mismatched `assessed_commit` produces `stale`.

Product completeness is orthogonal to the production release policy. Even a
fully passing whole-product audit never authorizes auto-merge or a production
deployment. Conversely, a release candidate can pass its separate delivery
gates while the global product remains `not_ready`.


## Definition of Done input safety

The production release policy must treat an absent or malformed
`definition_of_done` payload as an incomplete release candidate, not as
an empty list of checks. It requires `satisfied` and `missing` arrays.
Each missing check has a non-empty text `key`, with `human_only`
being a real JSON boolean. **Only** `human_only: true` on the
`human_release` key can defer that one check to the manual production-release
gate. Relabeling `github_ci`, `qa`, `preview`, `browser_evidence`,
`rollback_analysis` or any other check as human-only is rejected. The
`github_ci` key must explicitly be in the satisfied list to allow release
readiness; empty but well-typed lists cannot prove CI. Strings such as
`"false"` or `"true"`, numeric values and null cannot waive it.
Duplicate missing keys and checks simultaneously marked satisfied
and missing are invalid and block. Malformed items cannot silently
disappear while promoting a release candidate.

These rules do not alter the production human release requirement,
cost gates, Preview requirements or the independent full-product
readiness assessment.

## Release report semantics

Release reports describe the **candidate/release**, not the entire product. They must carry `readiness_scope=release_candidate` and must not set `product_complete=true` unless a separate full-product readiness assessment is present and passing.

## Human-facing language

Allowed without a product audit:

- "this task is complete";
- "this candidate is ready for human release";
- "the release completed";
- "the core architecture is implemented, with these remaining blockers".

Disallowed without a passing product audit:

- "the app is ready";
- "the product is complete";
- "100% finished";
- "only external credential X remains" when other readiness domains have not been globally assessed.


## Handoff pós-release: evidência ≠ tarefa ≠ produto pronto (20/10/2026)

Um release reconciliado em `operations` pode manter `product_ready=false`. A fonte mais próxima é o relatório durável `factory_release_reports` associado ao run de release e merge SHA observado. `src/ai_product_factory/post_release_readiness.py` sintetiza somente campos controlados: status `not_assessed`, `not_ready`, `candidate_only` ou `unknown`; lista dos seis domínios exigidos; IDs, SHA e estado de verificação do recibo. Nenhum `ready=true` é gerado a partir desse recibo: mesmo uma avaliação de candidato `passed` pode ficar obsoleta após o merge.

O reconciliador escreve um snapshot `operations` com as **obrigações de auditoria** e guarda um handoff sanitizado em `manifest.product_readiness_followup`. Novas reconciliações podem herdar esses fatos, sem propagação de prompts, dados de negócio nem alegações de avaliação executada. O runtime não cria nova run por um relatório incompleto: continuar desenvolvimento exige autorização operacional vigente, pedido válido, custos/gates preservados e evidência concreta de trabalho. Um auditor global independente continua necessário para promover `product_ready`.

Cobertura negativa offline: recibo ausente/trocado/duplicado, SHA não correspondente, status antigo `ready_for_human_release`, payload malformado, report indisponível e tentativa de forjar `ready=true` nunca passam a prontidão. CI verde valida o contrato, não equivale a auditoria global.


## Evidência global em HEAD atual (candidato 20/10/2026)

`global_readiness_evidence.observe_current_product` reutiliza
`release_intelligence._verified_product_assessment` ao aceitar uma
avaliação durável `product_readiness` de seis domínios no SHA atual,
com `evaluation_status` separado do corpo JSON e run/task vinculada ao
projeto. Um projeto `existing` exige também um `existing_project_baseline`
independente no mesmo SHA. Sem isso, o relatório é
`product_ready=false` com gaps de evidência por domínio.

O observador `workflow_run` **não é produtor** de avaliações de segurança,
a11y, RLS nem browser. Contar arquivos ou citar um CI do HEAD não satisfaz
uma avaliação inteira. O relatório é um inventory e plano de trabalho para
que avaliações independentes sejam realmente executadas e registradas
conforme o contrato de seis domínios, sem faturamento de modelos.


## 20/10/2026 — Operabilidade como parte da auditoria global

`operations` representa o estágio de ciclo de vida, não uma avaliação
`product_ready`. O Console expõe os seis domínios obrigatórios da Factory,
mesmo sem qualquer `factory_evaluations` do tipo `product_readiness`.
Status de candidato histórico permanece escopado ao SHA avaliado; UI não
autoriza promoção por contadores de tarefas, release observado ou checks.

Para produtos com interface, `product_experience` só pode receber avaliação
real com cobertura de surface inventory, responsive, accessibility e states.
O teste Playwright autenticado valida telas móveis em 390px, controles de
execução somente leitura, menu completo, overflow, fonte mínima, áreas
interativas e salto de teclado, além dos seis domínios exibidos. A mera
existência desses testes no repositório não é prova: o recibo do navegador
precisa corresponder ao deployment e candidato exatos.

A emissão de uma avaliação `passed` de produto inteiro continua fora do
escopo deste ajuste UX. Isso preserva `product_ready=false` até provas
de segurança, operação, critical E2E, documentação e funcionalidade.

## Post-visual evidence is not a product certificate (20/10/2026)

The main-push CI global observer may run before the authenticated browser
workflow finishes. A second read-only report now follows the completed
trusted visual workflow; successful CI, successful capture with same-SHA
encrypted artifact, and Vercel provider status are separately displayed
as **executed operational signals**.

They do not by themselves satisfy security, full product experience,
critical E2E across supported project types, recovery/rollback or
documentation review. `factory_evaluations.product_readiness` and
`release_intelligence` remain the only authority for product-level
`ready`; if same-SHA provider or browser subsequently fails, block
promotion despite an older evaluation. No paid call or new Factory run
is permitted for observational collection.

## Independent durable certification producer (30/10/2026 — candidate)

`global-readiness-post-ci` remains a read-only observer. The separate,
model-free producer is `scripts/certify_product_readiness.py`: it verifies the
repository default branch, exact 40-character HEAD, one successful `validate`
push run, and its executed `test` plus `factory-acceptance` jobs before it
evaluates all 19 criteria. CI is source evidence only; it never fills an
omitted domain criterion.

Run it with an independently gathered evidence manifest:

```powershell
$env:GITHUB_TOKEN = '<read-only GitHub token>'
python scripts/certify_product_readiness.py --project-key <key> --repository owner/repo --assessed-commit <40-char-sha> --evidence-file evidence.json
```

Every criterion records `passed`, `partial`, `missing`, `failed`, or
`external_gate`, SHA-bound evidence and a domain-allowed verification state.
Anything other than `passed` remains a named durable `not_ready` blocker. The
producer has no model, scheduler, merge, deployment or release authority. A
new HEAD always needs a new assessment because the observer requires exact
`baseline_ref` plus project/run/task lineage.


## 30/10/2026 — Positive criterion attestation must be externally verified

**Reproduced false-positive defect:** the former producer accepted 19 purported
`passed` criteria when each contained only the right SHA in fabricated text
(e.g. `github:owner/repo@<sha>:security/authn_authz`). That is format validation,
not proof that authorization, E2E, recovery or accessibility actually ran.

The certifier now treats a user-supplied `status=passed` as an **untrusted
assertion** until a criterion-specific verifier independently authenticates
the source and scope. The first implemented provider,
`github_exact_sha_validate`, can attest **only**
`test_strategy/unit_integration`: it is derived from the successful exact-HEAD
`validate` push workflow and its executed `test` and `factory-acceptance`
jobs, verified directly against GitHub. That provider is invalid for security,
UX, operations, documentation, regression completeness or critical journeys.
A SHA inside an evidence string alone **never** grants a PASS.

The read-only collector `scripts/build_readiness_evidence_manifest.py` runs
inside the existing trusted `global-readiness-post-ci` identity. Its second
artifact, `factory-verified-readiness-baseline.json`, lists all 19 criteria
with one independently verified unit/integration result, the partial CI
regression signal and explicit missing external verification elsewhere.
It produces a reusable input manifesto but **does not write evaluations,
release, create Starts, call paid models or require a new broker allowlist**.

The previous durable assessment on merge SHA
`7a9f74876aa5a35a91cb35602c576ffe53a7b3dd` remains a valid,
conservative historical `not_ready` result. The global read-only observer
recognized it in run #41042177251 attempt 2
(`independent_evaluation_recorded=true`, `product_ready=false`).
Do not re-label it `passed` after changing source code; a new human merge
requires new HEAD-bound evidence.

**Extension rule:** any future positive provider must have a pinned,
independent source of execution (workflow/run/artifact, verified service-side
read, or other authenticated review), verify repository/project/SHA and
criterion scope, and include adversarial tests. A reusable provider must
not turn a green CI check into a blanket six-domain certificate.
