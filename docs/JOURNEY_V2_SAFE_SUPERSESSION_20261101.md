# Retomada verificável da Jornada V2 do CRM — incidente #1188

Esta mudança **não** inicia uma nova jornada, não libera custo de LLM, não altera
nenhum registro do CRM e não faz merge. O objetivo é concluir a recuperação
da jornada #171 sem fabricar artefatos e liberar um novo Start **somente** por
comando OWNER autenticado na issue Factory #1055, com demanda CRM #209 real.

## Estado confirmado em 01/11/2026

- Factory main: `8a5a9fdd2ce83916e4d6c4e50e5994c9c36dd5da`.
- CRM main: `d63fa1ad8f1ffd252fe7df27f93a562e7184e8f6`.
- Jornada anterior: `88e94d11-4ada-4630-aa6a-fbf2c5665b2b`,
  geração 16, origem `fea4669258fcd832c7e187e7b00c1c5fb4d90a76`.
- Change Set `c105550f-3f2e-4623-bf21-f93f335deb62`: blocked; Work
  Unit `a82b7582-5b93-40de-998e-dee62a531134`: blocked, output null.
- PR CRM #207 é DRAFT e contém código humano: **nunca atribuir à Factory**.
- Nova base `preview/crm209-delivery-v3` criada pelo operador, SHA
  `d63fa1ad8f1ffd252fe7df27f93a562e7184e8f6` verificado no GitHub.

## O que o código faz

A migration `20261101130000_journey_v2_safe_supersession.sql` adiciona
`superseded` ao estado de jornada e uma RPC **SECURITY INVOKER**, somente
`service_role`, com auditoria e recibo idempotente por command UUID.

Para **superceder** exige CAS de versão/geração, operador admin ativo,
jornada executing ainda vinculada à geração, ausência de produção/candidato
efetivo, tasks/runs/Change Set/Work Units terminais sem output, ausência de
gates/deployments/release reports e ausência de lease relevante; não altera
o histórico de runs, Change Set ou branch. Rotaciona geração e política V2
na mesma transação; há validação de SHA de `main` e do novo Preview
na resolução futura, em duas leituras antes de vincular a origem.

A mesma migration faz o `factory_enqueue_journey_intake_v2` rejeitar
Start paralelo **após a validação de replay idempotente** e o bind rejeitar
outro ciclo ainda ativo. O operador deve conservar a autenticação de
Github OWNER no gateway, sem permitir chamada pública direta à RPC.

## Condições para a operação humana protegida

1. Merge humano da PR Factory, CI completa + QA PostgreSQL descartável
   **verdes**, migration revisada e aprovada separadamente.
2. Aplicar migration versionada no Supabase Factory via fluxo oficial;
   confirmar função e grants `service_role`, RLS, sem políticas públicas.
3. Antes da supersessão, reler os **dois refs** do CRM via GitHub
   e exigir `main == preview/crm209-delivery-v3` exatamente no SHA acima.
   Reler project control, jornada, leases e PRs no GitHub. Não sobrescrever
   PR #207 nem a base antiga; não declarar Preview publicado.
4. Invocar `factory_supersede_inactive_journey_v2` com:
   `project_key=crm-infodive`; `journey_id=88e94d11-4ada-4630-aa6a-fbf2c5665b2b`;
   `expected_generation=16`; `expected_version=15`;
   `expected_old_source_sha=fea4669258fcd832c7e187e7b00c1c5fb4d90a76`;
   `new_preview_ref=preview/crm209-delivery-v3`;
   `verified_main_sha=verified_preview_sha=d63fa1ad8f1ffd252fe7df27f93a562e7184e8f6`;
   `command_id` novo UUID e `actor_user_id` do operador admin autorizado.
   Esses parâmetros são **snapshot**, não autorização para chamada sem
   preflight. Não executar de forma automática no deploy da migration.
5. Verificar recibo, `generation=17`, nova versão da política e
   `journey.superseded` durável, sem modificar tarefas/CS anteriores.
6. Somente após essa verificação, o próprio OWNER publica um novo
   comentário **exato** em #1055: primeira linha
   `/factory-start crm-infodive`, pedido principal CRM #209 nas linhas
   seguintes (máximo 6000 caracteres). **Não postar por uma integração
   genérica em nome do owner**: o parser valida GitHub actor ID,
   associação OWNER, issue, repository e evento `issue_comment`.
7. Conferir aceite no Control Plane, Source Binding V2 e novo SHA;
   não confundir CI/Preview na branch manual #207 com saída da nova
   jornada. A Factory para em `awaiting_release`, merge de produção
   é sempre humano.

## Segurança / limites

Não há auto-merge, não são criados projetos sintéticos, não há alteração
do CRM nem da semântica de contratos antes da nova jornada. O SQL de
supersessão é restrito ao projeto existing e ao operador admin ativo;
`authenticated`/ `anon` não obtêm EXECUTE. O QA tem DSN local fixado
para PostgreSQL descartável e exercita CAS stale, operador não autorizado,
lease, gate, replay e segundo Start. Não considerar CI unitária substituto
da QA PostgreSQL real ou do Preview do CRM.
