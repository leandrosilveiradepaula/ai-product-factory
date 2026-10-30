# AI Product Factory — six-domain certification evidence matrix

## Reconciliação 27/10/2026 — decisão de arquitetura e escopo das evidências

O Service Desk **não** é mais alvo greenfield: foi integrado como módulo do CRM por PR #201, com migrations no Supabase do CRM. O projeto Factory `infodive-service-desk` está `stopped` desde `2026-10-27T17:59:48Z`, sem tarefas ativas. O F6 antigo e a PR independente #10 são históricos **não certificados** e não devem ser retomados. O browser E2E do CRM em `c9aaacd28140c9f132a5d8ae2ff250afc823c75c` verificou somente login público (runs [40551449688](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/40551449688) e [40551487676](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/40551487676)), sem autenticação ou CRUD do módulo. O alvo greenfield legítimo ainda precisa ser identificado e autorizado; **nenhum domínio recebe PASS por esta reconciliação**.

O Control Plane tem avaliações históricas `product_readiness=failed` (3), `browser_e2e` 6 success/5 failure, e avaliações de especialistas aprovadas em outros runs. São inventário de evidência, não atestados atuais. Manter seis domínios pendentes até avaliações independentes, duráveis e ligadas ao SHA corrente. Priorizar verificações offline/sem custo de Security, Operations, Test Strategy, UX e Documentation, sem repetir Provas 1/2 e sem fingir release. Ver [contrato atualizado](FINALIZATION_EXECUTION_CONTRACT.md).

---

> **Ordem de execução após o merge #1117:** seguir o [Contrato de finalização](FINALIZATION_EXECUTION_CONTRACT.md). Esta matriz **não** autoriza uma nova rodada de PRs para cada célula; primeiro reutilizar provas atuais por SHA, fechar o Preview real do greenfield e testar somente lacunas bloqueantes. No observador de 26/10/2026 [#40382212270](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/40382212270), `product_ready=false` e seis domínios permanecem sem atestado independente no SHA `50c9814cf03aa00799b87619665eaa6df20c3d8f`.


As of 26 October 2026, the Factory is **not globally product-ready**.
This inventory distinguishes a verified fact from an outstanding criterion;
it is not a substitute for the exact-SHA durable `product_readiness`
evaluation or a new workflow/paid test. Source of truth:
[`#713`](https://github.com/leandrosilveiradepaula/ai-product-factory/issues/713).

| Domain | Existing independent evidence | What remains unverified | Safe next action / gate |
| --- | --- | --- | --- |
| Security | #1104 fixes authenticated Console origin; #1105 production RPC uses service-role-only `SECURITY INVOKER`; negative CI tests | Cross-surface authorization, tenant boundaries, secret exposure and full SHA-exact security assessment | Execute offline/adversarial verification; authenticated operator provisioning requires explicit access authorization |
| Observability / Operations | Real candidate repin reconciliation `updated` at 2026-10-26T00:26:07Z with generation 13/version 12; recovery exercises from Prova 3 | Incident alerting, recovery and rollback coverage on current Factory SHA; credible failure visibility | Confirm scheduler/health/alerts and rollback in read-only evidence; no fake deployments |
| Test Strategy | CRM #197 native CI + Playwright on nonproduction integration; Factory #1105 `validate` and PG16 CI passed on candidate | All required critical Factory journeys, current-SHA authenticated coverage and negative contracts | Run bounded offline CI and targeted read-only E2E; exact-SHA receipt required |
| Product Experience | Source-level Console feedback and navigation tests exist; issue #692 remains open | Independently observed mobile/a11y/keyboard/loading/error/success across all critical surfaces | Offline static tests first; production temporary operator requires separate explicit permission |
| Documentation | `AGENTS.md`, `PROJECT_PLAN.md`, `docs/STATUS.md`, `docs/OPERATIONS.md` and runbooks exist; this block reconciles prior #1105 status | Independent current-SHA architecture/setup/incident/release/rollback review | Verify contracts and runbooks with realistic recovery scenarios |
| Functional Completeness | Prova 2 independently certified nonproduction in #40211815474; Prova 3 resilience scenarios passed | Generalizable greenfield end-to-end, selective Codex capacity and full product-level coverage; no production release attested | Use a legitimate authorized target; no synthetic throwaway project, no unsolicited paid calls |

## Non-negotiable certification rules

- Prior **Prova 1** completion is recorded in project history.
  **Prova 2** PASS is explicitly limited to nonproduction Preview integration.
  **Prova 3** PASS applies to exercised resilience scenarios, not every possible failure.
- `product_ready=true` requires a linked current-SHA durable independent
  assessment with all six required domains and verified coverage; tests,
  a green scheduler, Vercel status or documentation cannot set this flag.
- No automatic merge to production, public RLS, unapproved production
  migrations, paid model probes, 63-question SQL benchmark or replay of
  the completed CRM Change Set.
- Preview for this code-only Factory change is **N/A** by existing
  `apps/console/**` policy; no deployment should be manufactured.

## 26/10/2026 — Audited provider signal versus effective deployment

The official Vercel API returned `CANCELED` (ignored-build-step) for
`dpl_9sXYWPdP5Lbxobt7uiGh8rCqJA8k` at the #1107 merge SHA,
while GitHub commit status said `Vercel: success`. The commit contained
no Console files. This is a proven signal mismatch, not a Console
deployment failure or a domain PASS. The global observer now requires
exact first-parent changed paths to label `not_applicable`, and for actual
Console changes it reports GitHub success only as **unverified provider
signal**, never verified READY. Independent UX, deployment and operations
evidence remain pending. Global `product_ready=false`.

## 26/10/2026 — Product Experience: false-positive success badge fix (candidate)

StatusPill previously used substring matching, incorrectly reporting green success for inactive, unhealthy and not_ready states. The proposed Console change explicitly enumerates success and failure/uncertain states, prevents caller tone override from masking failures, adds accessible labels for custom captions, and exercises actual transpiled TSX in unprivileged CI. This closes one reproducible UX defect only. It does **not** certify all mobile/a11y/keyboard/loading/error surfaces or establish full-product readiness. An exact-SHA Vercel Preview and browser receipt remain required before human production merge.

## 26/10/2026 — Console dependency critical security update (candidate)

During the first Console CI of the status-semantics candidate, production npm audit blocked `next@15.5.27` with a critical advisory. The Next.js maintainers' [October 14, 2026 security update](https://nextjs.org/blog/nextjs-security-update-october-14-2026) identifies patched Maintenance LTS `next@15.5.28` for two critical RCE issues and a high-severity Server Action DoS. The candidate updates the exact Next dependency and npm-generated lock graph (including @next compilers), retains the live `npm audit` gate without exceptions, and adds an offline version-floor regression. Version metadata came from an unprivileged GitHub Actions `npm install --package-lock-only --ignore-scripts`, not estimated hashes. The temporary metadata-extraction CI step is removed. Only a fully green final CI, typecheck, build and exact-SHA Preview/browser may authorize a future human merge; no production release is automatic.

## 26/10/2026 — Post-merge Console authenticated evidence incident

Factory #1109 post-merge main `d463a602...` passed native CI and deployed
Vercel production READY. Authenticated screenshot workflow #40327176953
was canceled by the GitHub 12-minute limit before provisioning any user:
`ubuntu-latest` used Ubuntu 26.04 and apt package mirror downloads for
Playwright `--with-deps` stalled. An earlier passing actual authenticated
run #39467414056 used Ubuntu 24.04 and the same pinned Playwright version.
A candidate pins the browser runner's OS, verifies its distribution, and
smoke-launches pinned Chromium offline **before** temporary operator creation.
This does **not** count as product-experience PASS. A new explicitly authorized
authenticated workflow run is needed after the human merge of the fix.

## 26/10/2026 — UX controlled migration feedback and audit integrity

Protected browser #40330808460 independently passed the exercised navigation/mobile/operator RBAC of the live Console; it did not perform the gate migration interaction. The Console candidate now correlates new migration-success audit records to the exact gate_id and independently verifies run, commit, name and exact SQL source integrity before success banners. Offline tests exercise the real compiled TSX and server reader with delayed completion, invalid audit, network failure and URL tampering. This narrows #692, but no production migration E2E or six-domain global product_ready assertion is claimed.

## 26/10/2026 — Authenticated accessibility evidence extension (candidate)

Protected production run #40336494210 verified Console navigation,
mobile/RBAC, artifact encryption and temporary-operator cleanup on the
published #1112 SHA. It did not verify every page's control naming and
keyboard focus sequence. A candidate extends the existing 14-page visual
capture to fail closed on unlabelled visible controls, missing image alt,
invalid landmarks/headings, duplicate IDs, positive tab-order overrides and
skip-link inaccessibility with real Tab/Enter. Numeric-only evidence is
unit-validated in unprivileged CI. This is actual browser-executable
verification after a separately authorized protected workflow dispatch;
it is not a new domain PASS or a whole-product readiness attestation.

## 29/10/2026 — Retenção do recibo autenticado sem prolongar capturas sensíveis

**Problema reproduzido:** o run confiável de navegador do Console
[#40612548468](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/40612548468)
executou 14 vistas e verificações de navegação, mobilidade e acessibilidade
no commit `5061e1ef54b49ce4867c9612c825ffea5d8d8373`. O upload criptografado
`authenticated-console-40612548468` teve sucesso. O artefato desapareceu
da listagem GitHub após sua retenção de **um dia** (intencional); o Control Plane
mantém a linha `factory_visual_evidence_runs` com esse run/SHA, artefato e
`status=captured`, embora o prazo do segredo temporário já tenha passado.
O auditor global anterior rejeitava o run histórico apenas porque a listagem
atual de artefatos estava vazia, incentivando repetição de prova autenticada.

**Critério implementado sem novas permissões:** após verificar o workflow exato
`push main`, tentativa 1, conclusão `success` e job `capture` concluído no SHA,
o auditor usa **somente quando o inventário GitHub é exatamente vazio** a linha
única `captured` do broker, comparando run, SHA e nome do artefato.
Consulta exclusivamente `workflow_run_id,source_commit,artifact_name,status`;
**nunca busca `encryption_key`**, imagens, contas ou credenciais. O resultado
é `verified_historical`, `artifact_available=false`, fonte durável
`github_exact_sha_workflow_and_control_plane_captured_registry`: comprova
execução passada, **não** permite reabrir screenshots, não é browser novo,
revisão completa de acessibilidade ou avaliação de prontidão UX. Registro
inválido, ausente/duplicado, artefato presente mas contraditório, reexecução
ou falha de job continuam **bloqueados**.

A prova autentica a integridade de um recibo histórico no SHA original.
A identidade do código do Console pode ser reutilizada ao comparar subtrees
Git entre o SHA servido e o HEAD, mas isso não transfere automaticamente
um `product_readiness=passed`. A avaliação de seis domínios independente e
atual, incluindo os controles não comprovados de UX e Operations, permanece
obrigatória. `product_ready=false` sem esse atestado. Esta alteração afeta
apenas Python, testes e documentação; Preview da Factory é N/A porque
`apps/console/**` não muda. Não modifica política de expiração, RLS, Auth,
modelo/custo ou release/merge de produção.


## 30/10/2026 — Plano executável de 19 critérios, com evidência e condição de saída

Fonte live: `main=7a9f74876aa5a35a91cb35602c576ffe53a7b3dd`;
`validate` #41042113608 e PostgreSQL QA #41042113773 `success`;
primeira certificação real `c53eaefa-c856-4a05-ae0e-fcaa3f38dba2`,
avaliação `6a98a598-5921-4540-8fe1-23496687353f`:
19 critérios não certificados, `status=not_ready`. Observador
[#41042177251, tentativa 2](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/41042177251)
reconheceu `independent_evaluation_recorded=true`. A tabela abaixo detalha
o **próximo teste efetivo** de cada critério, sem alterar fatos históricos.

| Domínio / critério | Evidência aproveitável (escopo) | Prova ainda exigida / condição de fechamento |
| --- | --- | --- |
| security/authn_authz | Auth+RBAC do Console em testes de CI e browser anteriores | Login autenticado, roles, tentativas negadas e integração do fluxo corrente com recibos atuais |
| security/data_access_boundaries | 55/55 tabelas `factory_*` com RLS, 0 escritas públicas; leitura excepcional de `factory_console_operators` limitada por `auth.uid()=user_id AND is_active` | Revisão independente dos limites entre backend, GitHub, Console e tenant CRM; teste adversarial e prova de resultado |
| security/secrets_dependencies | Workflows com ações pinadas e testes de isolamento de segredos | Inventário atual de credenciais, caminhos de exposição, dependências e scanners executados; nunca ler/expor valores secretos |
| observability_operations/health | Console `/api/health` 200 `status=ok`; Factory e CRM `running` | Correlacionar código efetivamente publicado, API, banco e indicadores de incidentes; registrar escopo e horário |
| observability_operations/traceability | Certificação → run → task → projeto → evento auditável e Change Set CRM histórico | Auditoria independente de uma jornada completa atual, incluindo owner, geração, CI, Preview e recibos por SHA |
| observability_operations/recovery_alerting | Recuperações específicas anteriormente comprovadas | Testar falha/retry/recovery/alerta/rollback representativos sem mutação destrutiva nem modelo pago |
| test_strategy/unit_integration | CI push SHA exato: `test` e `factory-acceptance` SUCCESS; PostgreSQL QA SUCCESS | Certificar positivamente **apenas esta célula** com verificador GitHub autenticado; não extrapolar |
| test_strategy/critical_e2e | Runs CRM e browser históricos; escopos limitados documentados | E2E autenticado crítico real no CRM existing e greenfield legítimo; Production gate humano |
| test_strategy/regression_gates | Ruleset `Protect main - human release` ativo, exige `test` e `factory-acceptance` | QA PostgreSQL de migrations não é check requerido no ruleset; completar política verificável e cobrir CI/Preview aplicáveis |
| product_experience/surface_inventory | 34 rotas identificadas, cobertura histórica de 14 telas | Classificar todas as superfícies e testar telas essenciais sem confundir inventário com inspeção |
| product_experience/responsive | Navegador autenticado histórico em mobile | Comparar subárvore Console publicada com HEAD e cobrir rotas ainda não testadas |
| product_experience/accessibility | Captura autenticada anterior e testes de teclado/landmarks | Auditoria independente de controles, foco, contraste, a11y em fluxos críticos e regressão |
| product_experience/states | Issue #692 descreve pending→sucesso de migration | Executar jornada real autorizada verificando loading, empty, error, pending→success e bloqueio de duplo clique |
| documentation/setup_configuration | `AGENTS.md`, README e runbooks existentes | Seguir instalação/configuração em ambiente isolado sem credenciais inventadas |
| documentation/operations | `docs/OPERATIONS.md` e `docs/STATUS.md` atuais e históricos | Revisar comandos executáveis, discrepâncias de versão e procedimento incidente/recovery |
| documentation/release_rollback | `docs/RELEASE_AUTONOMY.md` e gates | Provar procedimento e rollback em ambiente isolado; merge/rollback produtivo segue humano |
| functional_completeness/requirements_inventory | `PROJECT_PLAN.md` e contratos de finalização | Mapear requisitos a jornadas e evidências duráveis por versão, identificar produto ainda não entregue |
| functional_completeness/mock_noop_demo_inventory | Guards de Direct/Codex, mocks e flags existentes | Inventariar no-ops e modos de demonstração que ainda possam alcançar produto, com testes negativos |
| functional_completeness/critical_journeys | Integração CRM não produtiva comprovada; Factory faz roteamento/CI/Preview parciais | Caminho legítimo Start→implementação→gate→operação no CRM + greenfield real autorizado; não usar Service Desk standalone |

**Política anti-loop:** coletar evidências independentemente **antes** de promover
qualquer célula `passed`; cada prova deve ter SHA, ID do run, ambiente,
execução do teste, resultado e escopo. Onde existir apenas declaração textual,
reportar `partial` ou `missing`. A avaliação nova deve substituir a anterior
somente depois do fechamento de novas células. Cron, PR verde, status `running`
e 19 campos preenchidos não substituem certificação.
