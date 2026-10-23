# J4 — CI nativa same-repo: continuidade e permissões

Estado: **candidato para revisão humana**, não evidência de uma PR greenfield E2E da própria Factory.

## Bloqueio observado em código (23/10/2026)

A rota `run_ci_once` já faz o handoff de um Change Set da Factory para o
workflow nativo `validate.yml` quando a PR foi aberta por automação e a
consulta SHA-exata não encontra CI em execução. Porém o job `ci-followup`
em `.github/workflows/autonomous-runner.yml` tinha `actions: read`. O endpoint
`POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches`
exige permissão de repositório **Actions: write**.

Fonte: https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event

O `GITHUB_TOKEN` pode iniciar `workflow_dispatch` mesmo quando outros eventos
gerados por ele não iniciam CI automaticamente:
https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow

Isso era uma **falha de contrato detectada por leitura de código e documentação**,
não um HTTP 403 reproduzido com token real. Não foi criada uma execução paga
para demonstrar o erro.

## Cinco fronteiras verificadas

1. **Permissão localizada:** somente o job `ci-followup` recebe
   `actions: write`, mantendo `contents: read`, `pull-requests: read`,
   `checks: read` e `statuses: read`. O workflow `validate.yml` roda com
   `contents: read`. Não se concede `actions: write` aos especialistas,
   Preview, Console, nem ao token cross-repo por esta mudança. O merge que
   ativa essa ampliação em produção continua humano.
2. **Admissão de candidato:** o item `ci_pending` já precisa passar pelo gate
   de controle de projeto, PR e candidate SHA inicial; token de mesmo repo só
   funciona quando `item.repository == GITHUB_REPOSITORY`. Nenhum fallback
   cross-repo é adicionado.
3. **Prevenção de drift no momento do dispatch:** depois do recibo de
   idempotência e do checkpoint de execução, consultar novamente a PR,
   exigindo PR aberta, não-draft, head repository e ref corretos, base `main`,
   e SHA exato. Consultar também o ref da branch e recusar divergência antes
   do POST. Isso reduz a janela TOCTOU; **não torna uma referência GitHub
   mutável atomicamente fixada** — o CI e o quality gate continuam exigindo
   evidência SHA-exata.
4. **Falha de autenticação auditada sem falso êxito:** HTTP 401/403 no
   dispatch registra `ci.same_repo_dispatch_permission_denied` com apenas
   run/PR/SHA e código HTTP, retorna `ci_dispatch_permission_blocked` e
   **não** grava `dispatch_ci`, `ci_triggered`, CI verde ou Preview.
   Outras respostas de erro ainda falham visivelmente; nenhuma credencial
   aparece nos recibos.
5. **Regressões gratuitas:** `tests/test_ci_dispatch_boundary.py` executa
   o caminho `run_ci_once` sem rede, modelo nem banco real, exercitando
   dispatch exato, drift entre duas leituras, ref movida, origem/estado de PR
   divergentes, 403, erro 500 e contrato de permissão no YAML. A suite
   original de CLI preserva a prova de dispatch único, idempotência por
   receipt e cross-repo sem dispatch nativo.

## Como observar uma jornada real, sem fingir certificação

- Disponibilizar um candidato **legítimo** `ci_pending` com projeto `running`,
  geração atual, orçamento/custos válidos, origem autorizada e PR aberta no
  mesmo repositório; não criar incidentes artificiais nem ressuscitar runs.
- O scheduler poderá executar a lane de CI e, somente se não houver CI nativa
  observável nem recibo de dispatch, iniciar `validate.yml` no ref verificado.
- Registrar `run_id`, `candidate_commit`, `pr_number`, `head_ref`,
  `GitHub Actions run_id`, job, tentativa, conclusão e eventos/usage do
  Control Plane. Um `workflow_dispatch` aceito não prova que a execução
  concluiu nem que o SHA permaneceu inalterado.
- CI e especialistas SHA-exatos, Preview real ou N/A durável e
  `awaiting_release` continuam necessários. Se o merge publicar produção,
  parar no gate humano; **nunca** auto-merge.
- Se os checks falharem, usar o reparo bounded existente; não transformar
  erro de permissão, quota, infra ou desconhecido em mudança de código.
- Sem projeto/sandbox autorizado, reportar `blocked_sandbox_not_authorized`,
  não `product_ready` ou `E2E PASS`.

## Limites e autorização

O patch não amplia `FACTORY_PRIMARY_MODEL_ENABLED`, não altera orçamento
de modelo, SQL, RLS, Supabase, Vercel, pilotos ou interface. Não há merge de
produção nem criação de recurso pago. **A ampliação `actions:write` exige
aprovação humana para entrar na `main`.**
