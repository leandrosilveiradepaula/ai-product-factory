# B4 — recuperação controlada de candidato após review bloqueado

**Escopo:** a mesma jornada legítima do projeto greenfield, usando o PR original e seu Change Set. A Factory está em **18/19**. Esta alteração **não** certifica 19/19, não faz merge e não cria novo Start nem Supabase para o produto piloto.

## Defeito comprovado

Um Change Set `ci_pending` pode ter seu run raiz em `release_policy_blocked` por DoD de migração/rollback. Se o autor corrigir o candidato na branch não produtiva, o PR original muda de HEAD, mas a RPC antiga `factory_reconcile_change_set_ci_candidate` exige `run.status=ci_pending` e não aceita corretamente esse caso. Copiar manualmente SHA ou status no Control Plane destruiria a linhagem e reutilizaria especialistas/Preview do commit antigo.

## Correção

A migration versionada **`20261116152500_reconcile_blocked_release_candidate_once.sql`** instala a RPC `factory_reconcile_blocked_release_candidate_once_v1`, `SECURITY INVOKER`, com `EXECUTE` somente a `service_role`. Ela exige, numa transação com locks e CAS:

- PR original ainda aberto na branch `factory/change-set-*` ou `factory/journey-*`, base `main`, sem merge ou draft; identificadores e repositório vinculados ao Control Plane
- SHA original do recibo imutável `create_pr`, SHA do último recibo `reconcile_pr_candidate` e SHA antigo do run, com duas ancestralidades GitHub `ahead` e sem divergência
- GitHub Actions do SHA novo realmente concluído, com inventário limitado de check-runs nativos e workflow exato aprovado na branch de integração
- run `release_policy_blocked`, Change Set `ci_pending`, relatório anterior `blocked`, task raiz `integrated`, projeto ativo `running`, mesma geração, work wave maior ou igual a 2, leases ausentes
- ausência de mudanças de release já observado; nenhuma alteração de `factory_evaluations`, `factory_specialist_lane_jobs`, deployments ou `factory_release_reports` existentes

**Somente quando todas as condições conferem**, atualiza SHA do run/Change Set e seus recibos de época, move o run para `ci_pending`, cria novo recibo reconciliado compatível com leitores existentes e evento de auditoria. **Não** marca CI, especialistas, Preview, DoD nem release como aprovados: exige novamente todos os verificadores no SHA novo. Tentativas repetidas e corridas de lease/generation falham fechado.

O comando `scripts/reconcile_blocked_release_candidate.py` é **dry-run por padrão**. Ele lê GitHub e Control Plane de maneira autenticada, confere fonte duas vezes, valida check-runs e as duas ancestralidades e só usa a RPC quando explicitamente executado com `--apply` após instalação aprovada da migration. Nunca registrar credenciais/headers ou passar secrets ao browser.

## QA e gates humanos

O workflow `b4-blocked-candidate-postgres.yml` aplica a migração *somente* num PostgreSQL 16 efêmero GitHub Actions e verifica ACL, CAS, permissão negada a `anon`/`authenticated`, 30+ casos negativos de spoofing, persistência do histórico, recibo de novo SHA, replay rejeitado e conservação do gate de produção. O teste recusa host remoto ou nome de banco não isolado.

**Operação depois do merge humano da Factory e autorização separada da migration Control Plane:**

1. Verificar `main`, PR, checks GitHub, SHA original e SHA novo. Usar `PYTHONPATH=src python scripts/reconcile_blocked_release_candidate.py --change-set-id <uuid> --run-id <uuid>` em runner server-side com credenciais de mínimo privilégio, primeiro sem `--apply`.
2. Registrar recibo do preflight. Somente se a migration aprovada estiver ativa, executar o mesmo comando com `--apply`. O operador deve autorizar especificamente essa alteração no Control Plane; **um merge de código não autoriza aplicar SQL**.
3. Disparar/verificar `ci-followup`, reviews de Segurança/QA/Operações e Preview no SHA exato **novo**, incluindo teste de navegador apropriado. Anotar evidências reais `migration_validation` e `rollback_analysis` somente após QA independente (PostgreSQL descartável ≠ aplicação de migration em produção).
4. Exigir `awaiting_release` genuíno, PR sem conflitos, DoD cumprido, QA e Preview integrais. **Merge na `main` do produto continua ação humana**; não há capacidade de auto-merge. Observer só registra release humano já ocorrido.
5. O certifier `critical_journeys` só libera 19/19 após release observado e operação independente. Sem essa prova, manter `product_ready=false`.

**Limitação:** o Studio ainda não demonstrou funcionalidade ponta a ponta com Auth/banco dedicado e IV/SRT integrados na interface publicada. Esta correção resolve o motor de recuperação da Factory, não diminui requisitos nem transforma uma página em produto completo. Nenhum serviço pago, deploy produtivo ou migration foi realizado por esta PR.

Link de acompanhamento: https://github.com/leandrosilveiradepaula/ai-product-factory/issues/1414
