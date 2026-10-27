# Preview backend unavailable — bounded delivery recovery

## Decisão vigente — 27/10/2026: recuperação histórica aposentada

**NÃO EXECUTAR o procedimento F6 legado para `infodive-service-desk`.**
A decisão vigente integra Service Desk como módulo do CRM Infodive; o projeto
independente está `stopped` e sua PR #10, run
`52998a8f-b478-46b3-9529-08bea72034f3` e Change Set
`60dd6b73-3e98-4da0-bc36-4be6d7562f45` são somente evidências
históricas **não certificadas**. Nenhum script de recovery, `--execute`,
configuração de backend ou restart deve ser usado para reviver essa linhagem.
A fonte atual é [Contrato de finalização](FINALIZATION_EXECUTION_CONTRACT.md)
e a [matriz de certificação](FINAL_CERTIFICATION_MATRIX_20261026.md).

O código genérico de recovery continua disponível somente para um incidente
**novo e legítimo**, com projeto ativo, identidade/epoch/PR/SHA reais,
preflight fresco e autorização humana para ações privilegiadas. A existência
desta capacidade não aprova nenhum incidente nem fornece um novo Start.


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
- Existing **historical failed runs remain failed**. The retired
  standalone Service Desk run is **not eligible for recovery** even if the
  former backend responds. Preserve its failure and evidence for audit.
  Only a different, genuinely authorized incident on an active project may
  use the bounded recovery path, without Product Stage replay.
- This capability itself cannot resolve the missing Service Desk Preview
  configuration; do not copy CRM credentials or assume its separate Vercel
  deployment represents the future Service Desk module within CRM.

Global certification remains `product_ready=false` until independent E2E
evidence completes the six domains.

## Ativação — procedimento histórico encerrado

A antiga sequência de ativação para o Service Desk independente está
**cancelada** pela decisão de 27/10/2026. Não executar a CLI com o project
key ou run ID históricos, não configurar secrets da Vercel standalone e
não reabrir a PR #10. A migration já instalada permanece como capacidade
do Control Plane, não como autorização para recuperar o caso aposentado.

Para um **incidente futuro autorizado** em projeto diferente, seguir esta
ordem, sem transpor evidências do caso antigo:

1. Confirmar projeto realmente ativo/running, Start legítimo, finalidade,
   run/task/Change Set, epoch, PR e deployment pertencentes ao mesmo alvo.
2. Confirmar política de Preview aplicável e o defeito específico de backend
   503; uma resposta de readiness nunca equivale a browser E2E aprovado.
3. Validar CI, especialistas, limites de tentativa, lease, orçamento e
   fronteira de acesso. Preflight é read-only; não usar permissões externas
   ou credenciais de outro projeto.
4. Somente um operador autorizado pode decidir eventual recuperação
   privilegiada, com prova nova e gatilho específico, nunca por cron
   especulativo ou comando de um projeto aposentado.
5. Exigir nova captura browser vinculada a SHA/URL/epoch e, se houver
   release de produção, gate humano de merge e observação posterior.

**Atenção:** nenhum passo acima constitui autorização para criar um alvo
greenfield sintético ou reativar o Service Desk standalone.

## Verification

- Offline: `PYTHONPATH=src python -m unittest tests.test_preview_backend_unavailable -v`.
- Real disposable PostgreSQL 16: `.github/workflows/preview-backend-recovery-postgres.yml`, guarded by `FACTORY_PREVIEW_BACKEND_TEST_ISOLATED=true` and exact local database identity.
- Negative cases: missing probe fields, malformed hostname, wrong PR/SHA/repository/branch, stale/future proof, 503/redirect/HTML, changed epoch/paused project, lease owner, pending specialist, missing CI, failed browser of another class, double dispatch, two-attempt limit.
- No credentials, production migration, real deploy, paid API or Service Desk mutation are used by those tests.

This is a **recovery capability**, not completion of greenfield certification. Six independent global domains remain subject to separate current-SHA evidence.
