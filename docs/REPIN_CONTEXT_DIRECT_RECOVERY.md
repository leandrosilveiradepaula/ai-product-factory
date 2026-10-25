# Prova 2 — evidência auditada de repin e retomada segura do Direct

Caso real: Service Desk como **módulo do CRM InfoDive**. O produto
comercial não está pronto; o objetivo é demonstrar autonomia da Factory.

## Incidente verificado em 25/10/2026

O Direct original `bd5a2e8d-413e-442b-8f23-6ef3016ea39e`
(processando Work Unit `9f4ad826-709e-452d-82ea-c00c6fb88c25`)
recusou uma implementação apesar do repin válido do candidato CRM.
Seu pacote antigo não incluía o **evento oficial de repin**, portanto
o modelo viu `CURRENT_TASK.md` apontando para o SHA anterior
`463a37d...`, mas recebeu base `042987...` sem prova do sucessor.

A evidência real está no Control Plane `fjplmxfcshhbmzgvyqlm`:
evento `project.delivery_target.reconciled` #1924, projeto CRM,
ator `system/factory-candidate-reconciler`, PR CRM #56, CI nativa
`CRM validation` run #40143764314, commit
`0429872652e8cb2bc0e9cde618bf5e848190e186`, geração 12,
versão 11. A branch Preview e a PR ainda estão abertas; nenhum
arquivo ou dado do CRM foi modificado por esse Direct.

## Correção de governança, não atalho

1. `SupabaseChangeSetStore.context_source` consulta dados server-side
   restritos: target, controle de geração e recibos de repin do mesmo
   projeto. `verified_repin` exige correspondência de ator, projeto,
   branch, PR, SHA novo/anterior, CI, geração, versão e avanço linear.
   Ausência, inconsistência ou desativação de política **não** viram
   comprovação.
2. `build_context_packet` acrescenta `repository.delivery_repin_evidence`
   somente quando a prova corresponde ao `exact_base_commit` e ao
   target. As `write_scopes` continuam as mesmas; nenhuma credencial
   ou chave entra no pacote. `PinnedNonproductionTarget.verify` continua
   verificando PR e branch reais independentemente.
3. O produtor só reconhece sucessor repinado se `CURRENT_TASK.md`
   **permitir explicitamente** isso e a prova corresponder ao SHA.
   Documentos que proíbem sucessores continuam bloqueando.

## Recuperação versionada, inerte até gate humano

`supabase/migrations/20261025010500_resume_blocked_repin_context.sql`
adiciona uma RPC `SECURITY INVOKER` com `EXECUTE` exclusivo a
`service_role`. Não habilita RLS pública.

A RPC só retorna a mesma run/tarefa/Work Unit/Change Set a filas
quando **todas** as condições se verificam: tipo existing, target
Preview explícito e SHA atual, geração/versão corretas, evento de
repin exato e atual, raiz Product Stage já concluída, único Work Unit,
nenhum commit/merge/lease, pacote antigo sem prova porém com escopos
exatos, blocker persistido com texto correspondente e anterior
`literal_scope_recovery` auditado. Caso contrário retorna `idle`.

Limite: até dois por chamada, `FOR UPDATE SKIP LOCKED`,
evento idempotente `change_set.repin_context_requeued`.
Não reexecuta Discovery, Spec ou Product Stage. Não chama modelo e não
autoriza merge/release. O próximo Direct legítimo segue o ledger e
limites financeiros, não o próprio script de recuperação.

## Evidência e ativação

- Testar unitariamente `test_repin_context_evidence.py` e
  `test_repin_context_recovery.py`, além das suítes regulares.
- Testar `verify_repin_context_recovery_postgres.py` em PostgreSQL
  **descartável**, incluindo ACL, drift SHA/generation/version, lock,
  scope e idempotência. Nunca apontar para Supabase real.
- Após CI e revisão, **merge humano** da PR da Factory, pois altera
  `main` com runtime.
- **Gate humano independente** para aplicar a migration ao Control Plane.
  Autorização anterior para outras migrations não se transfere.
- Verificar ACL e SHA novamente. Acionar comando OWNER
  `/factory-candidate-repin` na issue #1055. Verificar recibo
  `requeued=1`, evento auditado e mesma identidade de run.
- Executar wake OWNER legítimo. Exigir commit/PR criados **pela Factory**
  no CRM, CI nativa no SHA exato, reviews Security/QA/Ops e Preview
  real verificado até `awaiting_release`. Produção permanece merge
  humano. Prova 2 só PASS com evidência dessa cadeia.

Não declarar release, não criar outro Supabase/Vercel para Service
Desk, não executar benchmark 63, nem fazer chamadas pagas apenas
para teste.
