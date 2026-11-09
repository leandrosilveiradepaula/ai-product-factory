# Certificação conservadora durável da Factory por SHA atual

## Contrato

Após o `validate` de um `push` em `main` terminar com **SUCCESS**, a
`Factory autonomous runner` executa o job separado
`product-readiness-certification-post-ci`. O job só prossegue se a identidade
do `workflow_run`, repositório, branch, evento e conclusão forem válidos.

1. O checkout usa o SHA imutável do evento, sem persistir token.
2. `build_readiness_evidence_manifest.py` consulta GitHub e gera o envelope
   conservador dos 19 critérios. Atesta `unit_integration` apenas depois
   de confirmar um `validate` de `push` no **HEAD vigente**, com jobs
   `test` e `factory-acceptance` aprovados no mesmo SHA.
3. A credencial de acesso ao Control Plane é um token OIDC efêmero do
   GitHub obtido pelo broker já existente; nenhum novo token do Supabase
   é criado, impresso ou armazenado.
4. `certify_product_readiness.py --require-verified-baseline` revalida
   de forma independente a identidade, a evidência, o digest, o resultado
   conservador e a permanência do SHA como `main` HEAD **antes** de
   `factory_begin_product_readiness_certification_v1` e
   `factory_persist_product_readiness_certification_v1`.
5. O atestado, avaliação, run e auditoria são persistidos pelas RPCs já
   instaladas, privilegiadas e idempotentes por digest.

O job não inicia Start, não reclama filas, não despacha tarefas, não faz
deploy, não chama modelos pagos e nunca aprova merge ou produção. A rotina
`global-readiness-post-ci` permanece **somente leitura**, independente.

## Escopo do atestado

Esta fonte verifica **somente um dos 19 critérios**: Test Strategy /
`unit_integration` pelo CI nativo. `regression_gates` continua
`partial`. Os outros 17 critérios sem verificador independente continuam
`missing` (total: 18 não aprovados). Nenhum dos seis domínios recebe
`passed` apenas por esses fatos, e `product_ready=false` é obrigatório.

Provas recentes úteis, mas **não automaticamente certificadas** aqui:

- Jornada CRM #209: `run=integrated`, Change Set `completed`, Preview
  verificado, merge humano não produtivo observado no SHA `d84f4193`.
- VPS Linux: `workflow_dispatch` às 03:34, 03:45 e 04:00 UTC de
  05/11/2026, os três no SHA `08d3a409`, concluídos com sucesso.
- 58/58 tabelas `factory_*` com RLS, sem políticas `PUBLIC`; requer
  auditoria independente de autorização e de todas as superfícies.
- Console Vercel: deployment atual preservado em commits sem
  `apps/console/**`; não equivale a nova auditoria autenticada de UX.

Uma captura autenticada manual posterior ao `validate` pode gerar uma nova
avaliação durável no mesmo SHA somente pelo fluxo descrito em
[`POST_VISUAL_CERTIFICATION_RECONCILIATION.md`](POST_VISUAL_CERTIFICATION_RECONCILIATION.md).
Ela preserva três critérios de UX como `partial`, nunca como `passed`, e não
altera o estado de produto.

Os critérios restantes exigem verificadores próprios com provas de
execução e identidade, ou ficam explicitamente `missing`,
`partial` ou `external_gate`. Um greenfield legítimo, autorizado e não
descartável segue pendente; o Service Desk independente está aposentado.
Codex/WIF não deve ser inventado ou pago para obter um PASS.

## Verificação e recuperação

- Em GitHub Actions, localizar `Factory autonomous runner` com
  `event=workflow_run` do `validate` de push em `main`. A execução
  independente `product-readiness-certification-post-ci` deve concluir
  `success`, com artefato `factory-readiness-certification-<run-id>`.
- Confirmar no Supabase `factory_product_readiness_certifications` uma
  linha `is_current=true` em `assessed_commit=main HEAD` e estado de
  avaliação `not_ready`, acompanhada dos registros de avaliação,
  run e auditoria do certifier.
- Não confundir **job success** com **produto certificado**.
  Se o SHA mudou durante a avaliação, a etapa falha fechada antes da
  primeira RPC. A próxima execução de CI produzirá o atestado correto.
- Se o broker OIDC ou a RPC negar, verificar a identidade e as
  permissões server-side. **Não** ampliar ACLs públicas, desabilitar
  RLS ou instalar um segredo privilegiado na VPS para contornar isso.
- Não tentar reexecutar um evento antigo artificialmente para gerar
  certificado no SHA atual: cada registro deve estar vinculado à sua
  prova original.
- Rollback: reverter a PR que adiciona somente esse job, mantendo as
  RPCs e históricos; isso não afeta o scheduler da VPS nem o gate humano
  de release. Nenhuma migration é necessária.

Referências: `docs/FINALIZATION_EXECUTION_CONTRACT.md`,
`docs/FINAL_CERTIFICATION_MATRIX_20261026.md` e issue [#713](https://github.com/leandrosilveiradepaula/ai-product-factory/issues/713).
