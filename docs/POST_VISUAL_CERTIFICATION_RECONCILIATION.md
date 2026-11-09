# Reconciliação de captura autenticada pós-CI

## Problema corrigido

O `validate` de `main=d83a7095e18244c2833d626430cb3f575eb35130`
terminou antes da captura autenticada do Console
[#42439592059](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/42439592059).
O certificado persistido pelo gatilho de CI, portanto, não poderia conter esse
recibo posterior. A captura foi um `workflow_dispatch` autorizado, tentativa
1, com `capture` concluído e artefato criptografado não expirado
`authenticated-console-42439592059`.

## Fluxo após esta alteração

O job `product-readiness-certification-post-ci` também aceita a conclusão
**success** de uma captura autenticada por `workflow_dispatch`, mas somente se:

- o evento for do repositório e `main` corretos, no SHA que ainda é `HEAD`;
- a tentativa for exatamente `1`;
- o workflow, o job `capture` e o artefato criptografado forem únicos,
  concluídos, não expirados e ligados ao mesmo run/SHA;
- o `validate` de `push` no mesmo SHA ainda for verificável; e
- a mesma prova for reconsultada imediatamente antes das RPCs de persistência.

Falha, rerun, deriva de SHA, artefato expirado/ambíguo ou evidência divergente
interrompem a avaliação antes de qualquer escrita no Control Plane.

## Limite de escopo

Quando todos os vínculos são válidos, apenas `product_experience` /
`surface_inventory`, `responsive` e `accessibility` recebem estado
`partial` com o recibo GitHub. Eles **não** recebem `passed`.
`authn_authz`, `data_access_boundaries`, `critical_e2e`, `states`,
`critical_journeys` e `product_ready` continuam sem promoção por esta captura.
O artefato nunca é baixado ou descriptografado pelo certificador.

O job não inicia trabalho, não faz deploy, não chama modelo, não altera RLS e
não libera merge. A avaliação persistida segue `not_ready` até que cada um dos
19 critérios tenha prova independente adequada.

## Operação

Após merge humano desta alteração, uma nova captura autenticada legítima no
`main` atual produz uma reconciliação automática limitada. Não reexecute
capturas históricas apenas para atualizar a contagem: se o recibo expirou ou
o SHA mudou, o mecanismo falha fechado. Para observar o resultado, conferir o
artefato `factory-readiness-certification-<run-id>` e a avaliação corrente no
Control Plane; sucesso do job não significa `product_ready=true`.
