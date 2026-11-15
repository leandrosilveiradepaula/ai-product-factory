# B4 — Recuperação única de revisões especialistas esgotadas por falha de infraestrutura

**Finalidade:** recuperar a prova E2E do produto greenfield real e já autorizado,
**sem** inventar Start, fazer merge, modificar o candidato, apagar auditoria ou
aprovar artificialmente Segurança/QA/Operações. Somente a conclusão independente
das três novas revisões permite voltar à etapa de Preview. Esta recuperação
**não certifica** test_strategy/critical_e2e.

## Falha concreta que motivou o caminho

- O primeiro candidato do projeto greenfield legítimo permanece em PR própria
  com CI original aprovado.
- O release-run entrou em specialist_review_failed depois de três leases
  expirados por lane devido a falha no verificador de PR reconciliada
  (inteiro vs. string); a correção de código #1444 foi mergeada.
- O mesmo SHA e seus recibos continuam íntegros, mas a recuperação normal
  factory_recover_specialist_lanes(3) não pode reabrir jobs bloqueados.
- SQL em produção não deve ser alterado por scripts ad-hoc ou UPDATE manual.

## Pacote técnico único

1. O preflight independente lê **novamente** Control Plane, geração do projeto,
   Change Set, três roles, PR original + reconciliação, SHA do
   candidato, GitHub PR aberta, run/job CI da PR e validação push na main
   corrente da Factory. Uma declaração do operador não substitui esses dados.
2. A RPC factory_resume_specialist_infrastructure_once_v1, SECURITY INVOKER
   com GRANT **somente para service_role**, mantém RLS e rejeita geração
   diferente, Stop/Pause, candidato movido, lease ativo, findings de código,
   revisão concluída, reparo existente, Change Set diferente e segunda recuperação.
3. A RPC registra as três tentativas anteriores por lane em
   factory_audit_events, revoga tokens antigos, reabre os mesmos três jobs
   e concede uma única janela adicional de três tentativas. Não muda o
   Change Set, cria nova jornada ou autoriza release.
4. As revisões reais executam a inspeção novamente com tokens novos e
   devem produzir, por si próprias, passed ou failed.
5. Os testes PostgreSQL isolados exercitam ACL, positivo e negativos
   (SHA, epoch, pausa, findings, replay, token antigo e auditoria).

**Criação da migration no repositório e CI não são autorização para aplicá-la
no Supabase de produção.**

## Caminho operacional

Após CI verde, **merge humano** da PR da Factory e autorização explícita da
migration de produção, aplicá-la pelo Supabase, conferir função/ACL e iniciar
um dos seguintes caminhos **no workflow principal** da Factory (broker OIDC
autoriza essa identidade, não workflows novos):

- workflow_dispatch no Factory autonomous runner com specialist_recovery=true,
  specialist_run_id e specialist_candidate_sha. O default
  specialist_execute=false é somente preflight; true reabre as lanes.
- Comentário do OWNER na issue #713, exatamente:
  /factory-specialist-infra-recover <run_uuid> <candidate_sha>.
  OWNER, issue, branch e evento são exigidos pelo job.

O job não ativa schedule-probe, agentes, Primary, Codex, Preview, pagamentos
ou release. Se a verificação de fonte falhar, mantém as lanes bloqueadas.
Não substituir E2E por fixtures.

## Depois da recuperação

Verificar separadamente nova execução do worker especialista e o Control
Plane: as três lanes precisam terminar passed, preservar SHA da PR e
produzir recibos. Somente então a Factory segue sua política de Preview real
ou Preview N/A e o awaiting_release humano. Preview greenfield quando exigido
precisa de prova real de navegador; CI isolada e Vercel READY não bastam.

Depois do merge humano, o release observer deve registrar merge e operação.
B4 só muda para passed quando verificador independente revalidar provas no
SHA atual da Factory e persistir o resultado no Control Plane. Este reparo
sozinho não aumenta 16/19.

## Recusa e auditoria

Preflight bloqueado e SQL PT409 são impeditivos. Se a RPC executar e a leitura
posterior falhar, consultar auditoria e marcador de recuperação da run:
replay igual é idempotente, segunda janela não é concedida. Nunca zerar jobs
com SQL manual, apagar auditoria ou forçar status passed.
