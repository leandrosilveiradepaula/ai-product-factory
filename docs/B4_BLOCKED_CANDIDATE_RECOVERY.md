# B4 — Recuperação segura do candidato da jornada real

Objetivo: corrigir a divergência entre SHA da PR da jornada humana e o SHA que ficou bloqueado pela política de release. Não criar outro projeto, não comprar Supabase e não contar 19/19 sem release humano observado.

## Causa e correção

Quando a PR de integração recebe mudanças depois da decisão de release, o Change Set pode continuar em ci_pending, mas o run raiz estar em release_policy_blocked no SHA anterior. A RPC existente de CI exige run ci_pending e não resolve esse estado. Mudanças manuais nas tabelas falsificariam a linhagem e a auditoria.

O novo reconciliador verifica: projeto ativo e execução running, run e Change Set sem lease, release report original blocked com pelo menos um DoD não-humano pendente, PR aberta com origem/branch/target exatos, histórico Git ahead/behind_by=0, inventário de arquivos limitado, e CI nativo do novo SHA. Refaz a leitura de PR e branch antes da transação. CI atesta o commit apenas para permitir **recomeçar a verificação**; não substitui especialistas, revisão, navegador, DoD ou liberação.

A RPC versionada SECURITY INVOKER verifica o mesmo contrato dentro de uma transação e **apenas** atualiza o SHA do candidato e volta o run a ci_pending. Mantém o release report bloqueado, as avaliações antigas, o gate humano e todos os registros de auditoria. Um novo recibo reconcile_pr_candidate documenta o salto de SHA. Não concede release, merge, acesso público ou pagamento.

## Validação e ativação

A QA em PostgreSQL 17 descartável, sem rede de banco externo, testa a migração real, grants negados para anon/authenticated, função não-definer, falhas de estado, geração, SHA, branch e recibo, além do requeue com auditoria e ausência de duplicação.

**Não aplicar a migration no Control Plane sem autorização humana específica**, ainda que o CI da PR fique verde. Após merge humano da PR na main da Factory e aprovação da migration, usar na issue da Factory um comentário OWNER de uma linha:

    /factory-reconcile-blocked run=<UUID> pr=<PR>

O workflow autonomous-runner.yml aplica o comando exclusivamente ao run e PR selecionados. Para a jornada existente, o UUID é 3e747d9d-2440-4e78-8db0-55461753954e e PR 2 (números operacionais, não constantes no runtime). O requeue é desenvolvimento, não produção.

Em seguida: revisar CI novo e especialistas QA/Security/Operations no SHA novo, verificar Preview/navegador novamente, satisfazer de verdade os DoD migration_validation e rollback_analysis e só então atingir awaiting_release. O operador deve fazer manualmente qualquer merge produtivo; o observador apenas testemunha o merge humano existente. O certificado 19 exige release e operations efetivamente observados.

**Limites:** a migration e o RLS do Studio já foram testados em PostgreSQL descartável, mas isso não prova aplicação em um banco real nem UI funcional completa. Sem backend do Studio, seu portal retorna 503 fail-closed; não marcar produto pronto ou DoD aprovado por testes sintéticos. Evitar mudanças de requisito, criação de serviço pago e qualquer auto-merge.

**Recuperação de falha:** a RPC é aditiva. Nunca apagar dados históricos ou reverter SHA via UPDATE manual; um novo reparo requer CAS e evidência auditável própria. Não executar rollback destrutivo sem aprovação e backup verificável.

## Correção da linhagem original → reconciliado → candidato novo

O recibo imutável de `create_pr` identifica o primeiro SHA, que pode diferir legitimamente do SHA bloqueado após uma reconciliação anterior de CI. A recuperação exige um único `create_pr` de mesma PR/Change Set; se houve avanço anterior, consulta o recibo `reconcile_pr_candidate` mais recente e verifica SHA original, antigo/nova candidata, PR, repo/branch, comparação `ahead`, `behind_by=0` e conclusão CI `success`. Ausência ou divergência bloqueia. O novo recibo preserva `previous_commit` e `old_sha` como a origem do PR, e guarda o SHA imediatamente anterior separadamente como `prior_candidate_commit`, para compatibilidade com `SupabaseCIFollowupQueue.next_pending`. A QA PostgreSQL isolada cobre tanto a recuperação direta quanto dois avanços legítimos de candidato, mantendo relatório anterior bloqueado e impedindo falsos recibos. A migração permanece **não aplicada** no Control Plane até autorização específica.
