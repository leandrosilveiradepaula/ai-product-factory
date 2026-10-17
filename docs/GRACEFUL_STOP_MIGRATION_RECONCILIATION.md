# Graceful STOP — reconciliacao de migration aplicada via SQL Editor

Escopo: somente a migration ja instalada em producao a partir do arquivo versionado
`supabase/migrations/20261017193000_factory_graceful_stop_preserve_queue.sql`,
no projeto Supabase `fjplmxfcshhbmzgvyqlm`. O SQL Editor **nao** escreve automaticamente
em `supabase_migrations.schema_migrations`. Nao reaplicar o SQL apenas porque a
migration nao aparece no historico.

## Evidencia independente (17/10/2026)

- A PR #903 foi mergeada por humano na Factory.
- As cinco funcoes versionadas existem em producao com assinaturas esperadas:
  `factory_guard_project_execution_dml()`,
  `factory_control_project_v1(text,text,uuid,bigint,uuid)`,
  `factory_settle_project_control_v1(text)`,
  `factory_assert_claimed_run_epoch(uuid,bigint,uuid,text)`,
  `factory_claim_next_run(text)`.
- Na `factory_assert_claimed_run_epoch`, EXECUTE = true para `service_role`
  e false para `anon` e `authenticated`.
- A consulta independente confirmou a logica de `stopping` e `lease_owner`.
- O historico remoto terminou em `20261017175848_factory_manual_project_execution_controls`;
  a versao **20261017193000** nao estava registrada na ultima verificacao.
- O workflow temporario da PR #904 falhou antes de aplicar qualquer SQL: primeiro
  por segredo ausente, depois porque a conexao tentou o socket local do runner.
  Ele nao e mecanismo de reconciliacao.

## Procedimento aprovado: somente corrigir historico (gate humano)

1. Conferir no Supabase SQL Editor o resultado de
   `scripts/sql/verify_graceful_stop_production_readonly.sql`.
   Todas as colunas de verificacao devem ser true e `status` = `PASS`.
   Se houver `FAIL`, nao reparar o historico: investigar divergencias primeiro.
2. Em um computador autenticado no Supabase, abrir o clone atualizado do repositorio
   `leandrosilveiradepaula/ai-product-factory`. Usar a CLI oficial do Supabase;
   verificar primeiro `supabase --help` e `supabase migration repair --help`.
   Quem usa a CLI via npm pode substituir `supabase` por `npx supabase`.
3. Executar apenas:
   
   ```sh
   supabase login
   supabase link --project-ref fjplmxfcshhbmzgvyqlm
   supabase migration list
   ```

   A CLI pode solicitar a senha PostgreSQL: digitar localmente, nunca colar em
   Issues, PRs, chats, logs ou variaveis de navegador. Confirmar que a versao
   `20261017193000` consta no lado LOCAL e falta no lado REMOTE.
4. Com autorizacao humana especifica para reconciliar o registro da migration ja
   aplicada, executar **somente**:

   ```sh
   supabase migration repair 20261017193000 --status applied
   supabase migration list
   ```

   Isso atualiza o registro de migration sem executar novamente as cinco funcoes.
   Se a CLI reportar outros conflitos, nao aplicar `db push`, `db reset`,
   `migration up` nem reparos em outras versoes sem reconciliacao propria.
5. Verificar remotamente, apenas por leitura: a lista de migrations deve incluir
   a versao `20261017193000`; a consulta de schema e permissoes deve continuar
   `PASS`. Registrar versao, horario, actor e evidencias no Control Plane/PR
   conforme a politica; nao resolver gates por suposicao.

## Fronteiras permanentes

- **Schema de producao** e **registro de historico** sao alteracoes distintas.
  CI verde e PR mergeada nao as autorizam. O operador aprova a acao exata.
- Preferir sempre o Console administrativo ja implementado, que aplica migrations
  versionadas via Supabase Management API com gate humano e verificacao, **antes**
  de qualquer aplicacao manual do SQL. Nao usar o Console para reaplicar esta
  migration ja instalada. Para recuperacao de historico pos-SQL Editor, usar a
  operacao oficial da CLI descrita acima.
- Nao criar workflow Actions com URL PostgreSQL de producao, nem incluir
  `FACTORY_PRODUCTION_DATABASE_URL` em workflows.
- Nao configurar RLS permissiva, nao adicionar credito/API billing, nao iniciar
  projetos, nao executar benchmark 63, e nunca auto-merge de producao.

Referencia: https://supabase.com/docs/reference/cli/supabase-migration-repair
