# Recuperação determinística de CI repair terminal — gate da Prova 2

**Incidente confirmado em 24/10/2026:** no CRM InfoDive o repair
\`51078d63-d17e-418c-b9dc-d9c0d77b27da\` tem status \`passed\`,
o Change Set \`bd46da70-447e-4776-9dec-2ee38f139be8\` está
\`completed\` e a release run \`e5fd06d5-9d48-4796-bf58-f495cd785f06\`
está \`integrated\` após merge humano **somente na branch Preview**.
A source run \`e4b7c1d1-86a0-445e-83f0-191fd5b22cfb\` ficou
\`repair_pending\`, embora sua task esteja \`completed\`.
Ela bloqueia a CAS de repin do SHA antigo para \`463a37d93cd19ef3335ef6dd4c2421761de4f230\`.

## Remédio, sem ad hoc SQL em produção

A migration \`20261024162500_settle_terminal_ci_repair_sources.sql\`
introduz RPC **SECURITY INVOKER, service_role-only**, que só encerra a
source run em \`completed\` quando a cadeia inteira, no mesmo projeto e
execution epoch, confirma: request \`passed\`, source \`repair_pending\`,
Change Set \`completed\`, release run \`integrated\`, SHA original e
corrigido idênticos aos recibos, tarefa \`completed\`, leases ausentes
e todos os IDs de linhagem exatos. Insere auditoria por source.
\`SKIP LOCKED\` e batch até 4 tornam cron e replay idempotentes.
Não altera Change Set, release, PR, projeto, dados comerciais ou quota.

O reconciliador de candidatos da própria Factory executa
\`python scripts/settle_terminal_ci_repairs.py --max-items 3\`
antes do repin normal. Sem a migration, retorna
\`blocked_migration_not_applied\`, com zero escrita; nunca usa RPC
genérica para editar status. Outros erros bloqueiam e são visíveis.
Não gera cobrança OpenAI, Codex ou deploy.

## Ativação e evidências necessárias

1. Testes Python e PostgreSQL **isolado** no SHA da PR.
2. Revisão/merge humano da PR quando aplicável.
3. **Gate humano separado:** aplicar apenas a migration versionada
   ao Control Plane após autorização de produção; não rodar SQL manual.
4. Emitir wake OWNER \`/factory-candidate-repin\` na issue operacional
   #1055 e verificar o recibo: \`settled=1\` no incidente, depois repin
   do CRM para o HEAD da PR #56, CI nativa SHA-exata.
5. Só então admitir a nova continuação real da Factory no CRM,
   respeitando escopo do \`CURRENT_TASK.md\`, budget e produção.
   
A PR Service Desk #10 continua sem browser evidence PASS devido a
\`/api/session=503\`. Nem o assentamento de CI nem o repin aprovam
essa run histórica ou a Prova 2, nem permitem auto-merge.
