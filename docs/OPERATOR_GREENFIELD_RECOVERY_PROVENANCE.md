# Recuperação autenticada de reparo greenfield — 21/11/2026

O Restart humano do Dark Channel já foi autorizado e registrado pela RPC
`factory_restart_blocked_work_v1`, mas a continuação de Product Stage
`02f156ba-4593-4876-96da-9cfa96949485` falhou antes da LLM.
O guard greenfield genérico admitia apenas `github-owner`, embora
a recuperação do operador fosse uma rota autenticada independente.

Esta PR adiciona leitura de evidência para um **run já reivindicado**:
confere identidade de projeto, comando Restart, operador ativo, geração,
pedido original, source run bloqueado, repair job, Change Set terminal e
acceptance criteria de um único SQL versionado. Só após todos esses
vínculos consulta a `main` atual, ancestralidade do candidato e
`README.md`, `package.json` e migration no SHA exato. Não reaproveita
nenhuma autorização de escrita do Change Set terminal.

O Product Stage aceita o recibo autenticado **somente** para reconciliação
e restringe o plano a no máximo um builder task, com escopo exatamente
igual ao arquivo SQL original. A finding `permissive_public_grant`
não prova, sozinha, que um GRANT para `authenticated` deva ser removido:
é necessário verificar policies RLS e os testes multi-tenant.

Um retry depois do merge deve validar primeiro o `retry_of` do run
originalmente autorizado e seu erro tipado. O comando
`factory_retry_failed_run` é privilégio server-side; nenhum retry é
criado nesta PR. A admissão de OWNER Start permanece inalterada.
Sem nova migration Factory, sem aplicar migration Dark Channel, sem
alterar RLS, sem custo pago de teste, sem auto-merge.
Preview do Console é N/A: não altera `apps/console/**`.
