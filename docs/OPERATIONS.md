## 23/10/2026 — Recuperar planejamento sem replay de modelo pago (candidato)

**Diagnóstico:** o retry genérico `factory_retry_failed_run` copia `metadata.stages` completa. Nunca usá-lo no run CRM #24 `090cd768-b6e5-44ce-9d77-92f9ffe9620d`. Os outputs comprovados do run original são snapshot `c702b7e7-58b4-49ad-8be9-ee87b4f3c15d` (reconciliation), `factory_projects.manifest.gap_analysis`, audit events de `run.stage.recorded` + `product.stage.persisted`. Não há `metadata.stage_evidence` recuperável no run original: não reconstruir artificialmente uma saída completa inexistente.

**Nova ação, inicialmente inativa:** após CI/PR mergeados, publicação autorizada do broker OIDC (guard separado `rpc/factory_resume_failed_product_planning_v1`) e aplicação autorizada da migration `20261023023000_resume_product_planning_checkpoint.sql`, usuário OWNER pode comentar **exatamente** na [issue #1055](https://github.com/leandrosilveiradepaula/ai-product-factory/issues/1055): `/factory-resume-planning run=090cd768-b6e5-44ce-9d77-92f9ffe9620d`. Somente GitHub `issue_comment.created` autenticado, repo/issue/actor imutáveis, no workflow `autonomous-runner.yml`. A RPC service-only sob project lock verifica source.failed por budget exato, source stage list, run/task/epoch, auditoria de ambos os stages, snapshot no mesmo run, último gravador do gap, ausência de outro trabalho atual; serializa pedidos e cria somente `stages=['planning']`, task original requeued, auditorias `human/github-owner` e `system/checkpoint-resume`. Nenhuma chamada paga ocorre durante o enqueue. O novo ProductStageExecutor reaproveita `prior_stages` atestadas e chama a API apenas para `planning` quando o ledger real permitir.

**Ordem de liberação:** CI/PG isolado → merge humano → deploy Edge autorizado → verificação do source v+1 / identidade → migration autorizada e ACL de `service_role` (anon/auth false) → autorização de novo teto interno no Control Plane + comprovada disponibilidade real da OpenAI → emitir um único comando OWNER na issue #1055 → observar receipt `created=true`, novo run `queued` e seu wake, conclusão de planning/Change Set/PR, CI e Preview. Nunca interpretar `queued` como `completed`; controle financeiro não pode ser ampliado silenciosamente. GitHub comentário é público, não publicar segredos. Merge de produção continua manual.

## 22/10/2026 — Novo Start por GitHub proprietário; sem dependência operacional do Console (candidato)

**Contrato:** no GitHub da Factory, comentar na issue dedicada [#1055](https://github.com/leandrosilveiradepaula/ai-product-factory/issues/1055), como OWNER da conta vinculada, a primeira linha **exatamente** `/factory-start crm-infodive` (ou outra chave existente) seguida de quebra de linha e pedido real em PT-BR (até 6000 caracteres). Ex.: `/factory-start crm-infodive\nReconciliar issue CRM #24, corrigir apenas lacunas comprovadas, CI nativa, Preview verificado e merge humano.`. O comentário é **público** em repo público: não incluir credenciais, dados de clientes ou documentos privados. Não tratar a issue #713 ou comentários em PR como Start.

**Segurança:** job `owner-start` do workflow `autonomous-runner.yml` tem OWNER association, GitHub actor/user/sender ID (imutável), repository ID, issue #1055 e `refs/heads/main` verificados por parser **antes** de OIDC. A Edge `factory-runtime-control-plane` só proxy `rpc/factory_enqueue_github_owner_continuation_v1` se OIDC issuer/audience/repo/ref/workflow/actor correspondem ao **issue_comment** real. A RPC nova, invoker/service_role somente, aceita exclusivamente projeto ativo existente `running`, deduplica por `pg_catalog.md5(issue_no:comment_id)` convertido a UUID (não usado para autenticação), serializa com o mesmo lock de projeto do Console, proíbe raízes/filhos ativos, persiste `factory_projects.manifest.continuation_request`, task, run, cost=0 e eventos atômicos `project.continuation.requested` (human/`github-owner`) + `project.reconciliation.enqueued` (system/`github-owner`), ambos com project/task/run/request e identidade GitHub completa. Replays legítimos retornam `created=false`; payload alterado é PT409; não troca `actor_ref` do Console para simular origem.

**Despertar:** somente quando `created=true` e a transação concluiu, `GITHUB_TOKEN` do próprio workflow (`actions:write` exclusivo do job) chama `workflow_dispatch` **local** de `autonomous-runner.yml` com `project_key`. Os executores que assumirem o run respeitam rota, geração, autorização de custos, Preview, review e gate de produção. Falha de wake deixa run durável e emite `enqueued_wake_unavailable`; cron faz recuperação. O token não vai ao Python gerado ou ao browser. Recibo limitado é preservado em artifact `factory-owner-start-<run_id>`; sem prompt/segredo nos logs.

**Rollout, nessa ordem:** (1) validar 100% da CI e PostgreSQL QA isolada em PR; (2) humano efetua merge da PR por atingir runtime de produção; (3) autorização humana específica para publicar a alteração restritiva da Edge broker em produção; (4) autorização humana específica e aplicação da migration `20261022211500_factory_github_owner_continuation.sql` no Supabase, com verificação `pg_get_functiondef`, grants apenas `service_role` e teste read-only; (5) comentar um único Start real em #1055 pelo OWNER; (6) verificar job `owner-start`, resposta com `created=true`, task/run e audit unificados, worker wake e jornada por `/factory-journey-audit` do root run, sem reutilizar Change Sets históricos nem inferir Product Ready. **Não** executar Start antes de 3/4; não declarar pipeline completo por este protocolo apenas. A arquitetura de merge humano permanece inviolada.

## 22/10/2026 — Proveniência de Preview e Change Sets em auditoria de candidato (candidato)

Comando OWNER existente: `/factory-candidate-gates <project_key> pr=<n> sha=<40-hex>`, issue #713. O auditor usa o GITHUB_TOKEN da Factory somente para GET do **workflow fixo** `.github/workflows/console-browser-evidence.yml`, `run_id` declarado pelo snapshot do Control Plane, e seus jobs. **Somente** um snapshot `observed_stage=verification`, projeto/repo/SHA exatos, sem gaps, constraints de release falsas, nonce UUID, run único `workflow_dispatch` da branch `main` e SHA declarados, `display_title` correlacionado, job `browser-evidence` success e commit status Vercel success dão `preview.browser_verified=true`. A janela máxima da evidência é 14 dias; a falha posterior para o mesmo SHA prevalece sobre o sucesso antigo. O verificador de Preview faz apenas smoke de página pública e registra `verification_scope=public_preview_browser_smoke_only`; não implica login autenticado, Product Ready nem Release autorizado.

Bloqueios com `candidate_commit` diferente e válido são isolados como `historical_unrelated_blocked_change_sets` apenas se o root task é terminal e **todas** as runs vinculadas têm `metadata.execution_generation` íntegra, anterior à geração atual, e estado terminal. Root inexistente, erro de leitura, metadata ausente, geração atual ou run ainda ativa permanecem bloqueando; não se reabrem ou alteram Change Sets. Inventários com mais de 25 blocked, 25 snapshots ou 100 runs por lote não recebem prova incompleta. A resposta continua sem release authority mesmo se só restar `human_production_merge_pending`.

Para o CRM #56: antes desta mudança, browser parent GitHub run #39841207756, verifier #39841239361, snapshot `2ebb6fe2-9819-41b1-9133-d9e70e1dfc72` são fatos observados. Depois de CI e **merge humano do patch** da Factory, repetir **uma vez** o comando OWNER exato `/factory-candidate-gates crm-infodive pr=56 sha=184adae8ecf246790f51d9dc01e7145d14c6b458` e consultar o artefato/recibo. Não anunciar resultado do patch antes de verificação real. Para autonomia de desenvolvimento, continua necessário novo Start legítimo no Console (a auditoria não o substitui).

## 22/10/2026 — Auditoria exata de PR grande / candidato existente

O auditor GET-only `/factory-candidate-gates <project_key> pr=<n> sha=<40-hex>` aceita agora inventário de arquivos paginado, até **3.000 caminhos GitHub PR** em no máximo 30 páginas de 100, usando `changed_files` da PR como contagem congelada. Resposta curta/incompleta, extra, duplicidade entre páginas, arquivo renomeado sem origem e paths inválidos bloqueiam antes de avaliar applicability de Preview. Acima do teto REST de 3.000, não certificar, nem inferir paths ausentes. Ao terminar arquivos + CI, o auditor refaz GET da PR e recusa drift de identidade, base, branch, draft, estado, SHA ou `changed_files`. Somente erros de inventário/proveniência/deriva recebem motivo público fixo e sem dados arbitrários; outros erros seguem `unverifiable_live_evidence`.

Para o CRM (PR #56, 400 arquivos), a execução anterior [#39833468333](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/39833468333) bloqueou de propósito antes da correção. Após CI + merge humano da correção, emitir um **único** comando OWNER exato na issue #713 e consultar artefato `factory-candidate-gates-<run_id>`, além de Control Plane e GitHub PR. Resultado `blocked` com razões de CI, Preview/browser e gate humano é válido se a leitura é completa; `unverifiable_live_evidence` não é prova de gates. Não criar Start, trabalho, deploy nem modelo pago. O merge de produção continua exclusivamente humano.

## 22/10/2026 — Reconciliação de candidatos existentes isolada do scheduler de tarefas (candidato)

A `candidate-repin` opera **somente** com políticas `manifest.delivery_target.repin_policy.enabled=true`. O worker lê um inventário limitado (100 projetos; 3 processados por run), confere o SHA da branch e a PR/CI nativa exata antes de qualquer avanço. `unchanged` é no-op absoluto no Control Plane, não produz nova geração, task ou PR; `updated` somente via CAS da RPC `factory_repin_nonproduction_target_v1` com quiescência. Ausência de política => `idle`. Uma falha por projeto não oculta os outros do mesmo lote; o resultado agregado `partial_failure` falha o job depois da avaliação bounded.

O job GitHub Actions **`candidate-repin`** foi separado de `github-access-preflight` e agora tem apenas dois triggers:
- `schedule` nos crons existentes `17 * * * *` e `47 * * * *` (best-effort; GitHub pode atrasar/omitir);
- Comentário GitHub exatamente `/factory-candidate-repin` emitido pelo **OWNER** da Factory, mesma identidade `github.actor` e `github.event.comment.user.login`, repositório correto. É um wake diagnóstico e limitado, **não** um Start de produto, nem altera escopo/requisitos. Comentários arbitrários e o comando `/factory-wake` não o disparam. É possível executar esse comentário na issue operacional #1049 depois da publicação humana da PR deste job.

A action preserva OIDC do Control Plane e GitHub App/token cross-repo oficial, **sem permissões novas**, sem `OPENAI_API_KEY`, Codex, modelos, deploy ou merge. O job não tem `issues:write` ou `contents:write`. O modo `workflow_run` permanece reservado à recuperação read-only/filas e **não** recebe novo direito de mint de GitHub App token cross-repo. O recibo JSON é validado por `scripts/summarize_candidate_repin_run.py`: até cinco resultados, contadores/paginação consistentes, sha válido e resultados permitidos. Apenas project_key/status/SHA passam ao GitHub Actions Step Summary; razões brutas, tokens, configuração de credencial e manifestos não são ecoados. `error/blocked` geram falha visível no job, sem repetir SQL.

Para comprovar o piloto CRM já habilitado, verificar em um **novo** job `candidate-repin` no SHA de `main`: `eligible=1`, `crm-infodive/unchanged`, SHA `184adae8ecf246790f51d9dc01e7145d14c6b458`, nenhum evento novo `project.delivery_target.reconciled` e geração/versão ainda 6/5. Não concluir essa prova a partir de `validate` verde, job `schedule-probe` ou corrida antiga anterior à ativação. Mesmo com `unchanged` comprovado, a Factory **não** possui E2E novo para projeto `existing`: é necessário um Start legítimo e seu ciclo completo até operação.

## 22/10/2026 — Gate de Preview com nonce por browser job autenticado

O workflow `exact-preview-browser-evidence.yml` não pode correlacionar
um `workflow_dispatch` de `console-browser-evidence.yml` somente por
`created_at`: chamadas concorrentes recebem timestamp próximo e o
estado agregado da run pode continuar `in_progress` depois que o
único job confiável terminou. Após o Preview READY no SHA exato do
candidato, o pai gera um UUID `request_id`, lê uma vez o SHA
imutável da branch `main` e despacha o fluxo de browser da main
com esse nonce.

Ao consultar, `selectBrowserRun` exige o título `Console evidence
<UUID>`, workflow path, `main`, SHA atual fixado, evento exato,
`run_attempt=1` e URL/ID GitHub consistentes. A função
`trustedBrowserJobOutcome` exige payload integral com **somente um**
`browser-evidence` terminado e `success`, mesmo `run_id`
e SHA da main, sob evidência de workflow correlacionado. Resultado
agregado explicitamente failed/cancelled e todo job incompleto,
ilegítimo ou duplicado **bloqueiam**. A transição de job concluído
sem agregação ainda atualizada tem escopo estrito: browser verificado;
não certifica os seis domínios do produto e não libera merge humano.

A implementação não adiciona segredos, OIDC, chamadas pagas,
permissões GitHub, migrations ou deploy de produção. Testes Node
`scripts/tests/browser_run_correlation.test.cjs` são obrigatórios
na workflow `validate`. Preview do próprio Console continua
obrigatório no candidato, com SHA exato e commit status assinado pelo
GitHub Actions, nunca por check Vercel Comments isolado.

## 22/10/2026 — Integridade das migrations aplicadas pelo Console

O identificador local `20261022125100` do arquivo SQL do CI repair e o identificador remoto `20261022141432` são **diferentes**, mas o SQL remoto armazenado em `supabase_migrations.schema_migrations.statements[1]` é byte-idêntico ao arquivo de 14.700 caracteres (verificação read-only no projeto `fjplmxfcshhbmzgvyqlm`). A migration já está executada e não deve ser reaplicada, nem usar `db push` para “corrigir” historico.

Para novos gates humanos de migration no Console, conferir **nome + versão gerada pelo Supabase + SQL original** antes de resolver um gate como `already_applied`. A API oficial de leitura é `GET /v1/projects/{ref}/database/migrations/{version}` e requer `database_migrations_read`, o mesmo escopo usado na listagem. O SQL é obtido do arquivo GitHub no SHA do candidato, confirmado pelos checks. O verificador exige concatenação literal de `statements` idêntica ao arquivo, sem normalização de whitespace nem interpretação de SQL. Campos ausentes, duplicidade de nome/versão, payload incompleto ou SQL diferente causam recusa segura. Não exibir SQL remoto nem corpo de erro da Management API no Console/log/audit.

Depois do POST, o Console relê a versão gerada e a fonte exata antes de emitir `human_migration.console_apply_succeeded` e resolver o gate. Em timeout após aplicação bem-sucedida, a nova tentativa consulta versão/SQL e recupera idempotentemente, sem fazer novo POST. Em erro de leitura, **não repetir SQL pelo SQL Editor** sem verificar antes se já foi aplicado. Esse mecanismo não amplia credenciais nem autoriza migration automática, modifica gate apenas após clique humano explícito e exige Preview autenticado quando o Console mudou.

## 21/10/2026 — Comando OWNER para verificar gates exatos de PR

Comente exclusivamente na issue #713 da Factory o comando de exemplo:

    /factory-candidate-gates infodive-service-desk pr=5 sha=c7b061c6f18961bd1fdfea51f59e2985bbe8247a

O job candidate-gates-readonly do autonomous-runner.yml exige comentario OWNER, numero da issue e texto integral exatos antes do broker OIDC. Consulta apenas via GET o projeto registrado no Control Plane, seu controle operacional, a PR HEAD real no GitHub, checks de CI nativos e workflow pull_request no repositorio de destino. O token GitHub do Actions vale so no proprio repo da Factory: cross-repo usa GitHub App autorizado ou FACTORY_GITHUB_TOKEN explicito; ausencia falha fechado.

Policy Preview ausente significa policy_missing; quando required, falta de browser evidence continua bloqueada. Quando o Preview nao se aplica a paths do diff, o escopo e explicitamente explicado, nunca inferido da ausencia de deployment. Change Sets previamente bloqueados sao contados, mas nao retomados. Mesmo todos os checks verdes nao geram autorizacao: ready_for_production=false, product_ready=false, writes=0, paid_calls=0.

Auditoria retorna success ao provar status blocked com evidencia completa; ausencia de prova retorna unverifiable_live_evidence e falha. O JSON sanitizado vai ao artefato GitHub com 7 dias de retencao. Sem chamada de modelo, merge automatico, migration, nova credencial publica ou Preview criado. O codigo e um diagnostico consultivo, nao um mecanismo de liberacao.

## 21/10/2026 — Run terminal não certifica entrega descendente

A auditoria owner-only `/factory-admission-diagnose <project_key> <run_uuid>` era suficiente para estados de `run`, mas responder `no_new_action` a `run.status=completed` ignorava o Change Set materializado para a mesma raiz. No caso real do CRM, a continuação concluída terminou em um Change Set `superseded`; 1 Work Unit produziu um commit, mas a auditoria E2E da mesma origem só verificou 5/12 etapas. Reabrir o Change Set, reproduzir modelo ou certificar integração sem PR/SHA seria incorreto.

O leitor de admissão passa a consultar **somente** `factory_change_sets` vinculados pelo `root_task_id` do run terminal explicitamente informado, com `project_id` exato e até 30 Change Sets e 30 Work Units. A saída é sanitizada: estado da integração, quantidade de outputs com SHA formalmente válido, existência de `release_run_id`, comparação de generation atual e geração de origem; **não** imprime prompts, raw metadata, nomes de arquivo ou outputs SHAs. Checa antes de classificar se há registros fora da raiz, duplicados, respostas maiores que limite ou commits malformados. Se não houver Change Set, conserva o diagnóstico anterior. Para run filha, não inventa uma raiz.

Os estados `superseded` e `blocked` explicam falta de prova de entrega; `completed` do Change Set continua exigindo a verificação de release; work unit concluída não prova PR, CI, Preview ou merge. Epoch antigo em Change Set ainda ativo bloqueia reexecução automática. Nenhuma consulta faz claim, retry, merge, migration ou chamada de modelo. O scanner é um **diagnóstico**, não comando operacional, e `next_step` nunca autoriza ação sem o caminho oficial.

Para checar em produção após CI+merge humano: refazer `/factory-admission-diagnose crm-infodive 8b607ffb-008c-4ae4-aa29-2f624f27988b` na issue #713, validar `root_change_set_superseded`, generation revogada, 1 receipt de output, 0 release do root, `read_only=true`. A prova de jornada CRM permanece 5/12 até novo fluxo autêntico com CI/Preview/gate; o Service Desk permanece bloqueado por antecipação de release. Se a consulta falhar, manter `unverifiable_live_evidence`, sem acesso público ou correção manual de status.

## 21/10/2026 — Acionamento manual seguro das rotinas de settle

O runner da Factory permite ao OWNER comentar **exatamente** `/factory-wake` em uma issue para acionar o mesmo job `schedule-probe` usado por cron; comentários genéricos não passam. Em 21/10, o run [39621332271](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/39621332271) demonstrou que só Recovery e Probe corriam nesse evento; as quatro etapas de housekeeping haviam sido omitidas por condições específicas no YAML. Isso impedia usar o wake autenticado para recuperar uma release legada sem esperar pelo cron.

Esta atualização cria o recibo de passo `owner_wake` apenas quando as três provas coincidem: `github.event_name='issue_comment'`, `github.event.comment.body='/factory-wake'`, `github.event.comment.author_association='OWNER'`. O job mantém o gate original, fazendo duas validações de elegibilidade. Os passos `project-control-settle`, `release-state-settle`, `legacy-release-readiness-repair` e `project-control-wake` aceitam esse recibo, além dos eventos antes previstos. Qualquer RPC mutante continua com proteção de controle humano, geração/lease e `service_role` somente, seguindo a migration aplicada; o comando não revoga Pause/Stop, não cria liberações nem altera permissões.

**Prova de execução:** identificar no Actions o run correspondente ao comentário, job `schedule-probe` com `owner_wake=success` e quatro steps de settle executados. Não confundir runner `success` com correção do projeto: confirmar de forma independente no Supabase o audit `release.legacy_readiness_backfilled` e o snapshot de seis domínios exatos com `ready=false`. Ausência de evidência permanece aberta; erro não permite UPDATE ad hoc no banco. A mudança é Python/YAML/documentação, sem migration nem Preview do Console. O merge de produção segue humano. Para E2E de Start ou continuação humana usar `/factory-journey-audit` explicitamente, nunca `/factory-wake` como atalho.

## 21/10/2026 — Playbook: legado de release concluído antes do outbox

A migration de produção #1025 (`atomic_release_state_and_replay_outbox`, histórico Supabase `20261021131818`) cobre **novos** merges humanos observados. As releases anteriores que receberam um `project.state.reconciled_after_release` mas nenhum follow-up de prontidão exigem recuperação diferente. O job `legacy-release-readiness-repair` foi proposto para operar apenas após a migration separada `20261021135000_recover_latest_legacy_release_readiness.sql`.

A rotina consulta o seletor `factory_pending_legacy_release_readiness_v1` com permissão `service_role` e limite de 16 itens por página, e executa até 4 projetos por wake. Os recibos são qualificados no banco por `last_release` atual, report released, run merged, auditoria de merge humano, status `running`, geração ativa e ausência de release mais recente. Cada correção aciona `factory_reconcile_latest_legacy_release_v1`, que usa `factory_reconcile_observed_release_v1` numa transação e registra `release.legacy_readiness_backfilled`. Um erro permanente recebe `release.legacy_readiness_needs_review` em RPC própria; outage permanece retryable. SQL ausente retorna `blocked_migration_not_applied`, sem usar REST PATCH/POST isolados.

Operação e validações somente leitura: consultar `supabase_migrations.schema_migrations` por **nome** (versão Supabase pode diferir do nome Git), ACL de três RPCs (service_role sim, anon/authenticated não), `factory_pending_legacy_release_readiness_v1(NULL,16)` e, após o primeiro wake real, manifestação de `product_readiness_followup.ready=false`, snapshot com seis gaps e auditoria de correção do SHA exato. Comparar com `docs/LEGACY_RELEASE_READINESS_RECOVERY.md`. Nunca invocar mutação em produção manualmente para simular progresso; aplicar a migration só após nova autorização de produção. Merge em produção segue humano.

## 21/10/2026 — Observações de release no mesmo commit SQL (candidato, migration não aplicada)

`run_release_once` observa merge real, grava report `released` e depois reconcilia o projeto. Historicamente eram três writes REST (project, snapshot, audit), permitindo `operations` com snapshot sem gaps ou auditoria sem manifest. O erro não autoriza reprocessar implementação/CI/modelo nem tocar na liberação manual: apenas persistir, de forma confiável, consequências de um merge humano já comprovado.

Nova migration `20261021090000_atomic_release_state_and_replay_outbox.sql`: transação da marcação `released` exige run realmente `merged`, report pronto, SHA merge real e audit `release.human_merge_observed`; gera `release.reconciliation_requested` com o próprio projeto/run/SHA e deduplica por lock do report. O reconciliador versionado lê apenas report `released` do projeto e do run exatos, confere identidade da candidata, hash de merge, audit testemunha e recusa release mais antiga que outra já liberada. Em um único SQL COMMIT escreve manifest de `operations`, snapshot com seis gaps de prontidão `not_assessed` e audit `project.state.reconciled_after_release`. Um erro no snapshot, report ou auditoria faz ROLLBACK de tudo. Tentativas repetidas dão `idempotent=true` sem novos registros.

O leitor de outbox usa paginação por `factory_audit_events.id` (keyset), limite 16/consulta e batch 4 no worker OIDC existente. Eventos incompatíveis geram `release.reconciliation_needs_review` permanente, sem liberar produção; erros de infraestrutura não são suprimidos como resolvidos e podem ser tentados novamente. Nenhum evento de release histórico é retroativamente enfileirado; portanto, o `infodive-service-desk`, bloqueado após merge antes de CI/quality gate, NÃO será promovido. As quatro funções são `SECURITY INVOKER`, `EXECUTE` apenas para `service_role`, sem grants/policies públicos, sem função de merge.

Validação proposta: PostgreSQL 16 descartável com role ACL, ausência de testemunha, SHA adulterado, greenfield/existing, snapshot forçado a falhar e rollback completo, dedupe de release e auditoria, duas liberações na ordem contrária, marcador de review liberando a fairness do outro projeto. CI, Factory Acceptance, posterior merge humano e autorização distinta para executar a migration são exigidos. No intervalo após merge e antes de migration, o worker novo falha fechado se o RPC não existir; não se deve simular sucesso nem executar `db push` cego.

---

## 21/10/2026 — Specialist completion e traceability transacionais (candidato)

Problema: o worker gravava review, reparo e status por `factory_complete_specialist_lane_atomic`, e so depois ligava requirements e Definition of Done por `factory_record_delivery_evidence`. A segunda chamada podia falhar apos o primeiro commit; no proximo wake o job ja nao esta `claimed` e o recibo da entrega fica ausente, impedindo rastreabilidade confiavel.

A nova migration `20261021041000_atomic_specialist_traceability_evidence.sql` cria `factory_complete_specialist_lane_with_trace` (**novo** endpoint). Ele chama a funcao atomica anterior e, sob os mesmos locks de projeto/geracao, registra evidence em `factory_record_delivery_evidence`. Nao aumenta grants: `REVOKE PUBLIC/anon/authenticated`, EXECUTE somente `service_role`, `SECURITY INVOKER`. O worker troca para o novo RPC sem fallback ao anterior, logo antes da migration a chamada falha sem mutacao parcial. `traceability_recorded=true` mais contagens `requirements_linked`/`dod_checks_linked` sao obrigatorios para reportar sucesso; zeros sao permitidos quando nao existem requisitos/DoD vinculados, mas auditoria ainda e persistida.

PG16 isolado usa a funcao historica real de evidencias em fixture, testa links com evidencias, `DoD` invalido causando rollback e tentativa posterior, Pause/Resume, deduplicacao de evaluacoes e auditoria. Evitar novas chamadas de modelo. A migration e separadamente aprovada pelo operador depois do merge humano e deve seguir a historia real no Supabase, **nunca db push cego**.

---

## 21/10/2026 — Transacao unica de review, repair e recheck (candidato)

Depois de `factory_complete_specialist_lane` completar uma avaliacao, a versao antiga do Python chamava outro endpoint para `factory_enqueue_repair_from_specialist` ou `factory_close_repairs_after_specialist_pass`. Uma pausa no meio da sequencia nao retroagia a avaliacao. Uma resposta HTTP perdida podia repetir a RPC de reparo e alocar outra wave/tarefa para o mesmo job.

A migration `20261021040500_atomic_specialist_repair_handoff.sql` faz a acao de pos-review no mesmo commit SQL, sob o lock de controle ja tomado por `factory_complete_specialist_lane`. Os dois RPCs secundários passam a exigir o job original `failed/passed`, vinculo run/task/project/candidate, `metadata.execution_generation` e `evidence._factory_epoch`, projeto ativo `running` com geracao exata e `FOR SHARE OF c,p`. O enqueue compara `p_findings` com as findings persistidas e retorna recibo idempotente se o mesmo specialist_job_id ja gerou reparo. O recheck so atualiza reparos `integrated` do projeto/Change Set certo e, repetido, retorna updated=0.

Rollout sem meia transacao: o runtime passa a chamar exclusivamente `factory_complete_specialist_lane_atomic`, RPC novo criado nesta migration com `SECURITY INVOKER`, `REVOKE` para PUBLIC/anon/authenticated e `GRANT` estritamente a service_role. Antes de aplicar esta migration, nao existe esse RPC e o Python falha ANTES de executar a conclusao antiga. Nunca habilitar permissao publica para contornar um 404.

O Python agora faz UMA chamada de completion, exige o marcador `post_review_applied=true` e recebe `repair` e `repair_recheck` na mesma resposta. Se o backend nao tiver esta migration, o worker rejeita o sucesso parcial; ativar SQL e app de forma coordenada.

Este candidato NAO foi aplicado em producao. Supabase migration anterior `20261021030000` de #1021 tambem esta pendente e deve antecede-lo. Testes de PostgreSQL isolado e CI devem estar verdes antes do merge humano e do gate SQL. Se API responder com timeout apos commit, consultar a evidencia duravel em vez de repetir revisao de modelo.

---

## 21/10/2026 — Specialist epoch/lease-token fencing (candidate; not applied)

A run's original execution generation is pinned in `factory_specialist_lane_jobs.evidence._factory_epoch` when enqueuing security, QA and operations lanes. Claim and recovery compare both this immutable original epoch and `factory_runs.metadata.execution_generation` to the current project generation before selecting any work. Jobs from an earlier Pause/Resume generation and legacy/unmarked jobs fail closed; recovery quarantines them once with `specialist.lane.epoch_quarantined` instead of replaying specialist work.

Every fresh claim generates `_factory_claim_token` stored only inside the server-side Control Plane job. The worker receives this opaque token and includes it in the existing completion RPC payload. SQL requires exact match and a live, unexpired lease before mutating evaluations, run status or audit, then strips the token from published evidence. An old worker cannot complete after another worker reclaims the job.

The completion RPC takes `FOR SHARE` locks on both project and execution control, binding the same epoch across all completion effects. If Pause/Stop commits first, completion aborts with PT409; if completion holds the shared lock, Pause/Stop waits until it commits. The recovery selector uses SKIP LOCKED so pausing a project cannot block unrelated active projects.

Migration `20261021030000_fence_specialist_epoch_and_lease_token.sql` is NOT active until separately approved. The runtime Python companion will intentionally fail closed if a deployed DB still returns old tokenless claim receipts; this may defer new specialist work until migration activation. The post-merge operator must reconcile migration versions and confirm no active specialist jobs before applying.

---

## 21/10/2026 — Gate de proveniencia do auditor global rebaseado (#1013)

Ao revalidar evidencias de CI/visual do mesmo SHA, filtre GitHub Actions por `event=push` antes da checagem de `total_count` e valide que cada item realmente veio de push. Runs via issue_comment, schedule, workflow_run e dispatch nao sao CI da main e nao podem esgotar o limite 100. O path da workflow trusted `.github/workflows/validate.yml` tambem precisa ser exato; falha de historico ainda bloqueia certificacao. Nao transformar um `validate` ou observer SUCCESS em `product_ready=true`: as seis areas independentes continuam avaliadas separadamente.

---

## 21/10/2026 — Run epoch recuperada nao equivale a nova autorizacao

Caminho reproduzivel: o operador pausa um projeto no final de um lease; com nenhum lease ativo remanescente ele e `paused`. O operador retoma; `generation` sobe. A recuperacao original selecionava `r.status=running/implementing`, lease expirado, `state=running`, mas nao conferia `r.metadata.execution_generation`. Portanto uma run da geracao antiga poderia voltar para `queued` e adquirir nova geracao no claim, repetindo HTTP/API/commit ja aceito.

A migration `20261021021000_quarantine_cross_epoch_recovery_replay.sql` substitui cinco funcoes existentes mantendo SECURITY INVOKER e grants server-side. Ela: (1) coloca expirados antigos e queued antigos em `blocked` com auditoria e sem novo run; (2) propaga o bloqueio ao work unit e Change Set; (3) exclui claims antigas antes do LIMIT nos Product e Direct workers; (4) revalida a geracao durante a transacao; (5) remove capacidade antiga de retries realmente solicitados pelo operador, preservando a procedencia.

`blocked` e um gate de reconciliacao de efeitos/custos externos, nunca um gatilho para recarga de modelo. Nao reabrir em massa e nao executar nova tentativa sem evidencias de idempotencia. A funcao de especialistas, cujos jobs legados nao possuem geracao duravel, permanece fail-closed pelo controle humano mas deve ser avaliada separadamente antes de concluir garantia de exactly-once em todos os terceiros.

Valide `recovery-operator-control-postgres` e `validate` no SHA do PR. No fixture local de PostgreSQL, uma antiga gen1 expirada apos Resume(gen2) fica blocked; uma gen2 expirada requeue; Product/Direct ignoram antigas queued antes do LIMIT; retry solicitado gera uma unica nova run com procedencia; auditoria e unit states nao duplicam. Sem uso de OpenAI, alteracao em piloto ou Preview de Console.

**Nao aplicar no Supabase enquanto nao houver autorizacao separada.** A migration `20261021014000` tambem permanece pendente e deve ser aplicada/registrada antes da nova, se ainda ausente; reconciliar IDs Supabase e arquivo Git, nunca usar db push cego.

---

## 21/10/2026 — Fencing do reconciliador de descendentes em recovery (#894, candidato)

Depois da migration de recovery `20261020194500` aplicada e validada no banco sob version ID `20261021012144`, a funcao `factory_reconcile_terminal_task_descendants()` permaneceu sem checagem de controle humano. Ela e executada por `run_recovery_once` e pode cancelar um child queued ou marcar Change Set superseded quando o projeto inteiro estiver paused/stopped se o parent/root estiver `cancelled`. O banco de producao tinha zero candidatos na auditoria, mas a falha existe na definicao atual.

O novo arquivo `20261021014000_fence_terminal_descendant_recovery_manual_control.sql` substitui apenas a mesma funcao SQL, mantendo retorno, eventos de auditoria, status, SECURITY INVOKER e grants atuais. Os dois caminhos exigem projeto ativo e controle `running` com geracao positiva. O `FOR SHARE OF c,p SKIP LOCKED` mantem o controle bloqueado durante a transacao de recovery; se Pause/Stop ganhou o lock, o candidato e ignorado, em vez de bloquear ou sofrer efeito. Child parent e Change Set root precisam estar no mesmo projeto; nenhum chamado GitHub/Vercel/LLM ocorre.

Evidence: testes unitarios novos e `recovery-operator-control-postgres` testam a funcao SQL real e Pause/Resume cruzados em PG16 isolado. A fila de outro projeto continua recuperavel em presenca de lock humano. Aplicar em Supabase producao **somente com nova autorizacao explicita**, depois conferir historia, definicao, permissions e RLS; nao executar `db push` historico nem usar version IDs dos arquivos Git como IDs do Supabase.

---

## 20/10/2026 — Auditor de E2E por Console continuation e candidato reconciliado (candidato)

Ciclo real observado: projeto ai-product-factory, continuation root run
`945c0da5-f36f-46da-a454-072037a988a5` solicitado no Console em
03:07:16Z, Change Set `f95e3840-555e-40d7-8c91-011802debf8a`.
A solicitacao autenticada usa `project.continuation.requested` com actor
`human/factory-console` e `project.reconciliation.enqueued` com
`system/factory-console`, ambos ligados a mesmissimos
project_id/task_id/run_id/request_id; o run metadata exige
`source=factory-console` e `continuation_request_id` exato. A trilha
classica `factory_project_execution_commands/start` continua aceita
separadamente. Nao usar mera existencia de tarefa/run para forjar Start.

Integracao Work Unit: codigo de `d653d4b4...` foi copiado para
`c555249c...` (blobs identicos no SHA exato, sem relacao ancestral direta).
O candidato final `4b0e1cf3...` descende de `c555249c...`
por fast-forward auditado via `factory_reconcile_change_set_ci_candidate`.
Auditor le o `create_pr` imutavel, a RPC `reconcile_pr_candidate`, a
Change Set, o PR HEAD e compara paths/ancestralidade reais na API GitHub;
para cada Work Unit exige byte-for-byte equality com o candidato inicial
e presencia do commit no repositorio. O SHA final exige CI exato no GitHub.
Nao fazer GET de branch mutavel como fonte de comprovacao.

Gate de producao: aceitar evento legado `release.awaiting_human_merge`
OU o par auditado `release.policy.decided=ready_for_human_release` e
`run.status.updated=awaiting_release` no mesmo run/SHA depois de QA/CI
e Preview verificado/N/A. Merge precisa ser humano e observado, com
release_report.status=released, evento release.human_merge_observed ligado
ao PR, e project.state.reconciled_after_release=operations no merge SHA.

Executar apenas auditor read-only com corte UTC anterior ao request
e root run especifico; `product_ready=false` por padrao, nao reinterpretar
E2E de uma tarefa como prontida universal da Factory. Nenhum Start, modelo,
retry, merge, migration ou deploy deve resultar da auditoria.

## 20/10/2026 — Recuperacao de Work Unit platform bloqueada antes de codigo

Cenario real: projeto `ai-product-factory` e `project_kind=platform`.
Product Stage run 945c0da5-f36f-46da-a454-072037a988a5 passou por
Reconciliation, Gap Analysis e Planning, materializando Change Set
f95e3840-555e-40d7-8c91-011802debf8a com Work Unit
dcac15fd-9c16-466b-a72d-4a2c5f6020c7. Direct run
5057260d-3f4e-4a28-8209-53a0ea0ed5d2 bloqueou antes da fonte
e antes de chamar modelo: `PermissionError: unrecognized project kind`.
GHA 39362614047 falhou; nenhum arquivo/branch/commit foi produzido.

Candidato corrige builder, integração claim, integrador: para `platform`,
a fonte/PR target e `main` no SHA exato; branch de trabalho permanece
factory/*; drift de main bloqueia antes de escrita; nunca merge automatico.
`existing` continua preso ao Preview PR explicitamente pinado.

A migration versionada
`20261020032500_retry_blocked_platform_kind.sql` apenas cria uma RPC
`factory_retry_blocked_platform_kind` service_role invoker; NAO executa
recuperacao enquanto aplicada. Após merge humano do codigo runtime e
autorizacao especifica para aplicacao em producao, verificar SHA da main,
estado/generation do projeto, statuses e identificadores da run original.
Apenas entao chamar RPC uma vez com ID da Change Set, ID da run,
project_key, generation e motivo. Conferir audit
`change_set.platform_kind_requeued`, estados requeue, e disparar o
runner oficial sem refazer Product Stage. Nunca aplicar SQL UPDATE ad hoc,
never auto-merge, nunca reprocessar o Product Stage pago.

A RPC rejeita Change Set que ja tenha fonte/commits ou mais de uma Work
Unit, lease ativo, generation alterada, projeto nao-running,
blocker diferente ou tipo que nao seja platform. Custo efetivo da
fase de produto na run: US$ 0.223000 (reserva nao e gasto).
Ao retomar, somente a implementacao real pode usar modelo dentro do
ledger real e do budget; nao usar chamadas pagas para testar readiness.

## 20/10/2026 — Hardening de progresso real no Product Stage (candidato)

Foi identificada no nucleo uma falha de verdade operacional: o
`DeterministicBootstrapHandler` devolve um marcador `requires_model=true`,
mas `RuntimeWorker` aceitava esse marcador como stage `completed`.
Tambem se permitia `planning` com zero tarefas e zero decisoes, deixando
uma run concluida sem gerar backlog. O candidato recusa explicitamente
os placeholders e planos vazios antes de `record_stage`/Change Set.

O tratamento preserva fencing de execution_generation e usa o mecanismo
existente de falha da run. Nao chama OpenAI/Codex, nao cria migration nem
muda gates de release. Testes simulados verificam que nenhuma etapa
falsa e persistida; isso nao substitui a prova de Start → codigo → CI →
Preview → awaiting_release → merge humano observado.

## 2026-10-20 — Fonte no SHA exato: auditoria sem modelo e classificacao sem gate artificial (candidato)

Em um novo Start ou continuidade explicita, a Factory usa o claim RPC existente com fencing de generation e gate de custos. Para reconciliation do tipo platform, a leitura de codigo e governanca GitHub no SHA exato ocorre antes de qualquer chamada de modelo. O avaliador compartilhado classifica scope como complete (codigo lido), partial (faltante/omitido/truncado mas ainda possivel planejar), new_files_only (arquivos citados a criar) ou unscoped (pedido livre sem paths).

Nao usar essas categorias para fingir codigo verificado nem para solicitar aprovacoes humanas artificiais. Apenas recibos corrompidos/inconsistentes (SHA errado, path invalido, evidencia contraditoria) bloqueiam antes do modelo, encerrando o claim pela RPC ja existente com reason_code estavel e sem segredos. O auditor offline imprime categorias honestas e nao chama modelos/retries/Start. O runtime nao chama LLM para verificar paths/SHAs. Em tarefas verdadeiramente semanticas, respeitar budget/ledger.

Falhas genericas de auth/IO mantem o motivo fail-closed e nao sao prova de defeito no codigo. Run historica #987 permanece terminal. Sem RLS, migrations, refresh de token humano, auto-merge ou API paga para sondagem.
## 2026-10-20 - Continuacao na propria Factory: duplo clique e contexto platform (candidato)

Operador abriu Novo pedido na Factory; os dois cliques de Iniciar novo ciclo foram observados como uma unica task/run no banco. A run 16b12d17-9cb0-4578-a0e2-0d601f36b856 chegou a run.claimed e falhou em 39352319002 antes do modelo: `SupabaseRuntimeQueue._live_candidate_context` exigiu `project_kind=existing`, mas `ai-product-factory` e `platform`. Diagnostico verificado por GitHub Action e Control Plane; nao fazer retry do run antes do merge/correcao e sem avaliar budget.

Candidato conjunto: status pendente, desabilitacao e live region no submit; manutencao da chave `request_id` de idempotencia no RPC; preflight separado para platform que le um unico commit exato `main` e `AGENTS.md`/`PROJECT_PLAN.md` usando GitHub GET, revalida branch apos os reads e nunca finge haver Preview PR. Existing/importado segue exigindo pinned `preview/**` + PR aberto. Nao alterar gates de release nem usar API paga para sondar. Validar CI, Console build e Preview/browser SHA-exatos antes de qualquer merge. Falha historica fica preservada, nenhuma reativacao automatica.

## 2026-10-22 — Safe nonproduction candidate re-pin for existing projects

- Source of truth is the **open PR and its exact head commit**, never a floating branch or old Control Plane snapshot. The reconciler is generic for `project_kind=existing`: it has no CRM repository, branch, PR or workflow-name fallback.
- Migration `20261019031000_repin_nonproduction_target.sql` is applied. Its `service_role`/`SECURITY INVOKER` RPC row-locks project and execution control, requires CAS SHA+generation+version, `running` state and quiescence/no active runs or Change Sets, then atomically updates only `manifest.delivery_target.sha`, advances epoch/version and writes `project.delivery_target.reconciled`. It never rewrites historical run/eval/release evidence.
- An eligible manifest must declare `delivery_target.repin_policy` with `schema_version: 1`, `enabled: true`, and `native_ci` containing `schema_version: 1`, exact numeric GitHub `workflow_id`, `.github/workflows/*.yml` path, workflow display name and event (`pull_request` or `push`). A missing or malformed policy is `blocked`; the runtime must never infer CI from a green check, Vercel, a comment workflow or another project.
- `--mode candidate-repin` consulta páginas de até 20 projetos `existing` por vez e **falha fechado acima de 100**; seleciona apenas manifestos com `repin_policy.enabled=true`, sem deixar projetos legados sem política consumir vagas. Processa no máximo 3 por execução (limite configurável até 5), em grupos que rotacionam a cada 30 minutos UTC conforme os horários `:17`/`:47` do cron. Essa rotação é **best-effort**, não cursor durável: schedules perdidos podem atrasar um grupo; nunca declarar cobertura plena sem observação. `--project-key` restringe a um projeto. Retorna `idle` se nenhum estiver habilitado; `partial_failure` se uma política habilitada falhar, com resultado individual, e o CLI encerra com código não zero **depois** de processar os demais do lote. A última tentativa do workflow declarado no SHA/branch deve ser `completed/success`; tentativas duplicadas ou malformadas bloqueiam.
- O worker rejeita **PR draft**, CI de SHA antigo, mudança de PR/branch após observar a CI e recibo da RPC sem identidade e epoch exatos. `version=0` é aceita conforme contrato SQL da RPC instalada; `generation>=1` segue obrigatório. O worker **não** faz merge, deploy, planejamento, mutação em bancos-piloto, chamada paga ou marcação de readiness. O cron mantém `continue-on-error` desabilitado; um evento de auditoria transacional `project.delivery_target.reconciled` é a prova autoritativa de mudança. CRM e outros projetos sem política explícita ficam `idle/disabled` sem Work Units ou calls externas, até um operador aprovar política server-side.
- Regression: `PYTHONPATH=src python -m unittest tests.test_nonproduction_candidate_repin tests.test_runtime_cli -v`. This is isolated evidence only: it neither reopens old CRM work nor proves a real existing-project Start or production release.

## 2026-10-18 — Durable project-control wake (candidate)

Five functional blocks: SQL outbox trigger recording START/RESUME/RESTART atomically; privileged claim/ack lease with five attempts and generation fencing; postcommit Console delivery with durable failure; existing scheduled runner observes pending work without paid calls; project UI exposes status, with PostgreSQL 16 concurrency/idempotence testing.

The SQL migration `20261019002000_project_control_wake_outbox.sql` is **not applied**. Needs SHA-exact CI and Console Preview, human Factory production PR merge, and separate migration authorization. No registration autostart, paid probe, broader RLS access, new timers or runtime auto-merge. "Observed" means runner saw the wake, NOT task executed.
## 2026-10-18 — CRM Preview-only integration observer (candidate)

- External nonproduction merge verified: `crm-infodive` PR #180, candidate `aee522fe`, merged into `preview/hardening-release-candidate` at `88c35175`. The production branch `main` did not move. Vercel status for the merged SHA is success; no deployment to production was claimed.
- The proposed `factory_observe_nonproduction_preview_merge` RPC checks PR/merge/base/repository/status evidence, Control Plane project generation, exact CI+quality+specialist+browser receipts, plus the postmerge browser snapshot for the **merge SHA**. It also requires the readiness report. It atomically preserves the historical release report while setting `blocked` with explicit `production requires separate main PR`, concludes only the **nonproduction** Change Set, records audit/tool receipts, and releases agent scope locks. Repeating an identical observation is idempotent.
- Python `run_release_once` gains observation-only support for `preview/**` targets; it never gains merge capability, does not mark `human_release`, and does not close the issue/mark project production-released. Merged Preview branch head must be exact or a bounded descendant of merge SHA. Vercel **commit status** of the merge SHA, not its feedback check, must be `success`.
- Human production merge remains mandatory for any future `main` PR and requires fresh SHA-exact CI/Preview/release-policy evidence. Until the new migration is explicitly approved and applied, the CRM run remains `awaiting_release`, not `released`.

## 2026-10-16 — Policy UI reconciliation, migration already applied (candidate #866)

- The privileged Supabase migration `factory_primary_cost_policy` is already present in production migration history as version `20261015232347` (verified 16 October). It seeds the previously authorized internal budget USD 10.00 and reservation USD 0.50; this does **not** prove OpenAI Platform credits or permit automatic purchases.
- This branch rebases the staged admin-configurable budget UI/runtime onto the live post-#881/#863 Factory code. Exact merged GitHub fixes for early-human-merged CI and OpenAI pre-response credit rejection are preserved. Both the production merge and exact-SHA Console Preview/browser evidence remain mandatory.
- Do not reapply the policy migration, auto-merge, requeue Service Desk, run paid model probes, or infer current OpenAI credit from the internal ledger.

## 2026-10-16 — Fail-closed early-merged CI release candidates (candidate, not applied)

- **Incident:** Service Desk PR #7 was merged by a human into the private repo's `main` before CI, quality-gate or Preview evidence. GitHub evidence: PR merged at `2026-10-16T10:59:11Z` into `412f24d6dc7d0805b231ce91f12874ced743eebb`. Factory run `605212cf-b47e-418a-b4c4-79ad1efc6f59` and Change Set `effc36be-212c-42f2-928b-97381b6d8a28` remained `ci_pending`; this should not be promoted to `released` automatically. Incident audit `release.external_human_merge_observed_before_ci` #1041 was recorded with verified GitHub identity.
- **Independent blocker:** Factory owner cross-repo QA command was accepted after PR #880 merged, and real GHA [#38895967648](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/38895967648) began. Its exact-PR preflight failed because the workflow-level `FACTORY_GITHUB_TOKEN` secret is absent, before checkout and before any npm tests. The system refuses fallback to `GITHUB_TOKEN`. The private pilot's own Actions runner remains unavailable. This is not evidence that package-lock or app build failed. Admin credential/billing choices remain external human gates.
- **Root cause of stale queue:** `run_ci_once` evaluated CI without checking `GitHubPullRequest.merged` first, so merged PRs could continue returning `wait_ci` and re-occupy `ci_pending` indefinitely; no real quality evidence would be produced. The fix verifies exact head SHA before any update, checks human merge SHA, then calls a new service-role-only, invoker-rights Postgres RPC in a single transaction.
- **SQL contract:** `supabase/migrations/20261016120000_block_early_merged_ci_candidates.sql` defines `factory_block_early_merged_ci_candidate` with strict run/project/repository/candidate/create_pr/PR number evidence, linked Change Set ownership, status and release-report checks; locks rows and atomically sets run/Change Set `blocked`, preserves candidate SHA, and appends `external_early_merge` metadata plus a single `release.human_merge_before_readiness_blocked` audit. Idempotent when the same GitHub evidence is observed twice. No CI evaluation is forged, no Preview/release/project stage is marked ready, no human gate is bypassed.
- **Deployment gate:** This migration is **not applied** by merge. Validate Factory PR CI and acceptance first. Obtain explicit human production database-migration authorization separately, apply only via trusted migration path, verify service-role-only EXECUTE and actual function definition, then allow **one** normal CI follow-up to observe the existing merged Service Desk PR. Check the exact row status changes, metadata, audit and unchanged candidate SHA. No automatic retries of failed private QA; no new paid provider tests; no auto-merge.
- **Recovery after project remediation:** The early-merged run remains blocked pending explicit operator reconciliation; do not relabel it released merely because a PR merged. Quality work continues in independent draft PRs #3/#5 and pilot issue #8. The pilot's private Actions/FACTORY_GITHUB_TOKEN availability requires account administration, not a data migration.

## 2026-10-16 — Integration attempt counter per wave (candidate, not deployed)

- Real greenfield Service Desk eight-wave Change Set `effc36be-212c-42f2-928b-97381b6d8a28`: wave 4 `knowledge-base` Direct run `28497089-9415-43e8-b8e4-06bf754b5607` completed and produced `dc044aaaf23f64ca6a3df818430ec1e2a1fa3df5`, but Factory GHA [#38839037505](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/38839037505) Change Set integration logged `claimed:false, processed:0` even though its job was green.
- **Confirmed root cause (Supabase production read-only):** `factory_claim_change_set_integration` requires `s.attempt_count<3`, and the Change Set has `attempt_count=3` from successful integrations of waves 1, 2 and 3. `factory_complete_change_set_integration` advanced the `current_wave` without resetting the counter. It would silently starve all eight-wave plans after three successful waves.
- Proposed SQL fix **preserves** the maximum three attempts within each wave and resets `attempt_count=0` **only on successful advancement to a later wave**, while persisting `integration_attempts_by_wave` history; an unsuccessful integration does not reset the retry count. The claim/recovery SQL is intentionally unchanged, and all functions remain `SECURITY INVOKER`/service-role-only.
- The versioned migration includes an **exact-identity, fail-closed and audited one-time repair** for this recorded Change Set. It checks the project ID, exact candidate/base, no leases, precisely 3 prior integrated waves/4 units, the completed wave 4 run/commit and 8 untouched later work units. It does not create a run, merge a PR, or touch the pilot data schema. All mismatches abort the migration atomically.
- **PRODUCTION GATE:** GitHub CI and PR merge alone do not apply SQL. Administrator must explicitly apply the migration via the authorized Console path, then independently verify the function definition and the audit/counter in Supabase. Only after applied migration and confirmed candidate branch SHAs may one OWNER `/factory-wake` resume existing wave 4 integration. No autonomous migration, no auto-merge, no paid test calls. The pilot's security/React/CI blockers remain open issues #1/#2; green Factory jobs with `processed:0` are not quality evidence.

## 2026-10-16 — Safe greenfield continuation scopes (PR candidate, NOT released)

- Real Service Desk second-wave Direct run `151954cb-91ba-4434-bd50-6b389175906f` on GHA [#38836556208](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/38836556208) was claimed after first-wave integration, but stopped in preflight with `semantic write scope could not be resolved safely: auth`. The original run, work unit and Change Set remain blocked; the other 11 units remain pending. This is a legitimate fail-closed result, not an OpenAI billing problem.
- Root cause: scope resolution relied on filenames already existing; the eight-wave greenfield plan explicitly names semantic areas whose modules must be created later. The README-only bootstrap applies only to wave 1 and correctly does not permit blanket writes in later waves.
- Candidate fix reads authoritative `project_kind` from Control Plane and enables bounded architectural namespace mapping only for post-foundation greenfield work units, only with existing README, package metadata and `src/` foundation. Versioned migration writes require an existing migration root. Known structural suffixes (domain, API, UI, services, jobs, workspace, portal, layouts and queries) work for other products without product-specific exceptions; unknown scopes, uninitialized repos and imported projects retain fail-closed behavior. Exact explicit context paths are never overridden. Model writes are still checked by `enforce_write_scopes`; no repo-root scope, `.github/**`, credentials, or production path is introduced.
- Regression tests cover the real wave 2, all 12 planned scope groups, imported project refusal, unexpected paths, frozen context, missing migration roots and path traversal. No calls to paid models, provider quota checks or Vercel deployments are part of these tests. Only GitHub PR CI is evidence before merge.
- **Recovery remains separate**: never automatically requeue the blocked second-wave run or create a duplicate. After a human production merge and verified CI, revalidate the exact blocked run, task, assignment, work unit, and Change Set, then perform an individually authorized, transactional/audited same-run recovery before one OWNER wake. No auto-merge.

## 2026-10-16 — README-only greenfield foundation preflight (awaiting merge)

- Real Service Desk GHA [#38826947695](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/38826947695): after human-merged #868, adaptive concurrency correctly became **1** despite Vercel `deployments_daily=blocked`, and the real protected Direct job **started** run `e0d94242-9236-4288-a415-54d81a9553d7` for the first foundation wave. This is not code success. `change_set_worker._resolved_repository_context` blocked with `repository context discovery found no relevant files; replan with explicit context_paths`. Database set run, task, work unit and change set to `blocked`; no model cost increase or commit occurred.
- Root cause: `leandrosilveiradepaula/infodive-service-desk` at its frozen SHA `62dcc97187c78f53408ac60cba88b83585d6323b` contains **only README.md**, while work unit `foundation-app`, wave 1, requests the semantic foundation scopes `application-foundation`, `database-migrations`, `environment-template`, `domain-shared` to create the initial TypeScript files. Existing context ranking requires already-matching code files; it cannot bootstrap an empty codebase.
- Candidate change is generic, **not hardcoded to Service Desk**: in a README-only/metadata-only repository, for **wave 1**, an explicit foundation/bootstrap/scaffold plan task and **only known semantic scope keys** may resolve to a fixed, allowlisted set of structural paths (package.json, TypeScript config, `src/**`, tests, migration directories and safe configuration source files). Always include README and any actual AGENTS/CURRENT_TASK governance in the bounded frozen-SHA context snapshot. Never grant `.` or `.github/**`, live `.env`, secrets, unrestricted root, or override explicit context paths. Populated repos, later waves, unknown scopes and unrelated work retain strict failure. Model-produced writes still pass `enforce_write_scopes`; out-of-scope writes block the unit with auditable `repository_governance`.
- New deterministic tests exercise README-only success, AGENTS governance, no root scope, fresh-file acceptance, populated-repo rejection, unknown scope/later wave rejection, invalid explicit paths, and attempted workflow writes. **No paid model call or real provider usage** is performed by CI.
- **Important recovery gate:** original run `e0d94242...`, work unit `389631fb-13b6-4c9b-ad0d-065b91b86a10`, change set `effc36be-212c-42f2-928b-97381b6d8a28` remain durably `blocked`. The standard recovery RPC only requeues expired running leases, and `factory_retry_failed_run` supports `failed` tasks only; neither silently unblocks this stopped work. After human merge and verified CI, a **separate explicitly approved** audited, idempotent Control Plane recovery must requeue exactly the original run/work unit and reset the change set if no other blockers; never create a duplicate run or reset later waves. Document and confirm the recovery state before triggering the next authorized wake.
- No `apps/console/**` changes: Factory Preview N/A for this candidate. #866 Console financial policy remains Draft until real Vercel Preview READY + browser evidence at its own SHA; Vercel provider quota remains blocked. Release merge is always human.

## 2026-10-15 — Service Desk Direct concurrency blocked by unrelated Vercel Preview quota

- Real run [#38825991468](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/38825991468) was triggered exactly once through the existing OWNER-only `/factory-wake` path, after #867 merged. Queue probe found 13 eligible portfolio work units; Product Stage published protected `primary_ready=true`; dispatcher **correctly created the first Direct run** `e0d94242-9236-4288-a415-54d81a9553d7` and assigned the development agent. This verifies #867's scope fix in real production behavior.
- But the dispatch work matrix returned `direct=[]`, `effective_concurrency=0`, reason **`resource quota is blocked`**, and the Direct GitHub job was SKIPPED. The durable run is queued, not completed; Service Desk change set `effc36be-212c-42f2-928b-97381b6d8a28` now has 1 queued unit in wave 1 and 12 pending units across waves 2–8, with no code commit or PR.
- Live Control Plane `factory_resource_limit_snapshots` has only **Vercel / team / deployments_daily** signals (latest persisted 2026-10-13 17:38 UTC, blocked). `factory_agent_concurrency_decisions` recorded that same blocked signal as an unscoped global quota for a Direct task. Vercel **deployment** quota only applies when publishing/validating Console Preview or release; it is not consumed by Direct code writing to GitHub. This cross-provider coupling is the actual root cause, not exhausted OpenAI budget: known paid ledger USD 3.7210392, 0 unknown events; existing protected model gates stay in place.
- Candidate change (Python + tests + docs only): exclude **only** Vercel `deployments_daily` signals from the Direct/Codex concurrency matrix. Keep all other provider and resource quota blocks, unknown paid-cost blocks, per-run reservation, protected Primary enablement/identity, and provider-billing gates. If no execution-relevant quota is observed, status remains `unknown` and concurrency stays capped at 1 rather than presumed healthy. Record Preview quota separately as telemetry; **do not change Preview's own fail-closed Vercel cooldown or deployment evidence**.
- New deterministic tests replay the exact `vercel/deployments_daily/blocked` case and verify a single runnable Direct item; prove independent OpenAI/GitHub/other blocked quotas and unknown paid costs still enforce concurrency=0. No API calls, Vercel deploys, schema migrations, fresh tasks or credits.
- The patch is **not deployed** until human merge of its green CI PR; next native/authorized wake should resume the existing queued run without duplicating it. Check a real Direct job, commit, PR and cost ledger before claiming implementation succeeded. Preview N/A for the Python-only Factory patch. PR #866 Console remains Draft until exact-SHA Preview/browser evidence.

## Revisão do formulário financeiro (15/10/2026) — antes de Preview

- A seção `Configuração → Orçamento e custos` passa a mostrar as **últimas 20 alterações auditadas** de teto/reserva, com ator, horário, valor anterior/novo e justificativa. O histórico é lido server-side pela chave privilegiada do Control Plane. Falha de leitura **não** aparece como "sem alterações": UI informa "Histórico indisponível".
- As regras de entrada passam a aceitar o limite máximo de `100000.0000`, igual ao CHECK de banco, sem permitir zero, quantia negativa ou precisão superior a quatro casas. Isso é validação de formulário, **não autorização** para elevar o teto atualmente aprovado de US$ 10,00. Mudanças financeiras exigem administrador, confirmação explícita e auditoria na mesma transação.
- Esta revisão ainda pertence à PR Draft #866; CI/Preview SHA-exato/merge humano seguem obrigatórios.

## 2026-10-15 — Service Desk wave 1 dispatch gate fix awaiting human merge

- Production Evidence: GHA [run 38822922959](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/38822922959) Product Stage `FACTORY_PRIMARY_MODEL_ENABLED=true` inside protected `openai-api` environment, completed Service Desk planning run `d5f1ea54-c388-4266-83b1-b8b06f2fd302`, materialized change set `effc36be-212c-42f2-928b-97381b6d8a28` with 13 pending work units across eight dependency waves. Dispatcher subsequently logged `FACTORY_PRIMARY_MODEL_ENABLED=false`, `FACTORY_DISPATCH_PRIMARY_READY=true` and returned `blocked_executor_readiness` because unprotected `dispatch` cannot see environment-scoped GitHub vars.
- Candidate fixes only `dispatch` to use the **trusted, fail-closed output of protected Product Stage** for both the primary flag and prior authentication readiness signal. If Product Stage is absent/blocked the output is not `true` and dispatch stays disabled. The Python gate `require_dispatch_claim_readiness` still requires both booleans and rechecks the real ledger/reserve before any atomic claim. No secrets are passed into dispatcher; Direct itself still checks opt-in + credentials + cost with protected `openai-api` environment.
- Regression contracts assert the source is the protected job, that the dispatcher cannot depend on repository-level vars for this decision, that the protected jobs retain strict explicit opt-in, and that no API token appears in dispatch. No Console path changes: Preview **not applicable** for this patch.
- No runtime merge or paid probe, no change to total US$10/reserve US$0.50, no API purchase, no Codex token, no changes in #866 Draft. Publish to main only by human review/merge.

## Operator-configurable paid policy — activation order and rollback

The Source of Truth for total Primary model ceiling and per-call reservation is the `public.factory_primary_cost_policy` singleton in Supabase. The initial `budget_usd=10.0000`, `reserve_usd=0.5000` seed represents the authorized limit, not OpenAI API balance. Admins can change both under `/configuration#orcamento` using an explicit confirmation and written reason; an optimistic policy version prevents stale concurrent updates. Persist an audit event with before/after values in the same transaction. Operator profiles can read but not mutate.

**Production migration first:** apply and verify `20261015231500_factory_primary_cost_policy.sql` via a real human database-migration gate. Confirm RLS on the new table, no policies for anonymous or `authenticated`, exact singleton row/seed and service-role-only privileged RPC. Do **not** deploy the runtime first; the new worker deliberately blocks paid execution when the source of truth is unavailable. Do not backfill anything by deleting/requeuing existing Service Desk runs.

**Console Preview second:** the PR changes `apps/console/**`, so CI alone is insufficient. Obtain Vercel READY at the exact candidate SHA, execute browser evidence with admin and nonadmin UI paths, including form validation, stale-version conflict, a successful audited update and historical usage display. If Vercel is rate-limited, remain pending rather than bypassing Preview.

**Human merge last:** merge to the Factory production `main` only after migration + Preview/quality gates are verified. Confirm `/usage` and `/configuration` reflect the persisted policy. Observe existing Service Desk run and paid ledger without issuing smoke model calls, purchasing API credits, widening GitHub App access or enabling Codex. A decrease may intentionally block new paid execution; an increase is an explicit admin financial decision and does **not** refill OpenAI Platform credits.

Rollback: before merging, no runtime behavior changes. After merge, restore code to the last verified commit **without rolling back the table or erasing audit**; a compatible prior runtime still uses its previously reviewed workflow ceiling. Database writes are append-audited; reversing a policy amount is a new admin transaction with a reason. Do not silently substitute YAML defaults if the runtime cannot read the table. This is independent of the existing release-merge and Preview gates.

## 2026-10-15 — Reused Preview ref ≠ Vercel deployment (candidato sem Console)

- Caso real #863: a ref `preview/pr-863` aponta para o SHA candidato, mas a Vercel retornou `Deployment rate limited` às 22:23:10 UTC e não publicou Preview. A primeira recuperação (#861) detectou um deployment posterior no SHA #860, mas a tentativa de novo Preview consumiu uma promoção de ref e recebeu nova negativa do provider.
- Este candidato adiciona o guard determinístico `scripts.preview_reuse_guard` ao fluxo já existente: quando `preview/pr-N` é reutilizada no mesmo SHA, exige status Vercel mais recente, inequívoco, `Deployment has completed`/`Deployment ready` e URL HTTPS de deployment concreto no mesmo commit. Rate limit, `Ignored Build Step`, ausência de status, empate de timestamps e inventário inválido bloqueiam antes de disparar outro browser workflow; o bloqueio é explicitado no resumo.
- Não força a ref de volta ao parent nem recria branch, não chama Vercel API/CLI, não habilita quota paga e não atribui Preview `READY` a uma referência Git. A prova pelo navegador continua obrigatória após status Vercel real. Para o mesmo SHA previamente recusado, um **novo deployment autorizado pelo provider** permanece dependência externa; rerun do promotor por si só não o cria.
- Somente Python, workflow e documentação; Preview Console N/A para o patch da Factory, CI obrigatório e merge de produção humano.

## 2026-10-15 — Atomic project intake and first run (#713)

The previous Console submitted create-intake, attachment-finalization and initial-bootstrap as three independent database calls. A failure after creation could strand a project with no initial run; repeating the form then hit the duplicate project key.

A new privileged SECURITY INVOKER function factory_start_project_intake_v1 executes those operations in one PostgreSQL transaction, using the original draft UUID as a stable idempotency key. The server obtains the operator identity and re-counts the private draft attachments (0–10), including finalized records for exact retries, rather than trusting a count in the URL. Any count mismatch, changed intake, conflicting project key, missing task or missing durable run fails closed. The same exact retry returns the existing run rather than starting another cycle, even after it has finished. The Console no longer calls the unsafe three-step sequence on project review.

**Preview validation:** a promoted `preview/pr-*` candidate always builds, even if that SHA was seen on a previously skipped branch. A Vercel status `Canceled by Ignored Build Step` is not READY evidence. Browser verification still requires a real SHA-exact Preview URL.\n\n**Required human gate:** apply and verify the versioned Supabase production migration before merging or deploying the Console change. There is intentionally no fallback to the old non-atomic flow when the RPC is unavailable. The PR's CI and Preview are only candidate evidence; they do not prove production database rollout or complete greenfield product E2E. No RLS widening, paid model calls or automatic production merge is introduced.

## 2026-10-15 — Non-starving autonomous CI/release followup (#713)

- After #832 human merge (Factory main `8854d640dcf6e70ed4d40370b145d3c285facb7c`), a concrete fairness gap remained: the bounded CI/release drain intentionally stops when its oldest `ci_pending` run is waiting for external CI or its oldest `awaiting_release` PR has not been human-merged. This could prevent later *independent* ready CI results or human merges being reconciled during the same scheduler wake.
- Both existing read-only Supabase queue selectors now accept a bounded tuple of previously observed run IDs. An empty tuple retains the original `limit=1` call; non-empty tuples read up to the 12 oldest candidates and select the first not yet observed **in the current wake**. Identifiers are never interpolated into a REST query; no schema/RLS change or Control Plane writes are introduced by selection.
- New `drain_waiting_followups` scans at most 8 distinct run IDs, completes at most 3 ready CI/release items per native scheduler job and records waits separately. It fails closed on duplicate IDs, malformed worker responses or bounds violations. A waiting human release gate is never approved or merged by the runtime; only an *already existing human merge* may be observed by `run_release_once`. CI keeps its existing SHA/quality checks.
- All other deterministic lanes, Direct, Codex, product stage, Preview and model/budget gates retain their existing behavior. This is a bounded fairness improvement, not a claim of greenfield full E2E. No historical queued task replay, new cron, paid model calls, Vercel Preview or Supabase migration.

## 2026-10-15 — Autonomous deterministic continuation within one scheduler wake (#713)

- Live Control Plane read-only check: 3 projects, 0 active runs, 0 pending human gates; 10 historical `queued` children of completed parents, **not eligible for automatic replay**. The native scheduler is active and can legitimately report no work. Never synthesize tasks or mark `product_ready` because CI/Preview passed.
- Previously, CI followup, Change Set integration, each Security/QA/Operations specialist lane and the release observer handled **one** candidate per scheduler run. The runtime now supports `--batch-items 3` for these **existing deterministic workers only**, processing at most 3 verified independent items per job and stopping on empty queues, unresolved CI, unmerged release, duplicate durable IDs, blocked status, or invalid worker output.
- `--batch-items` defaults to 1 for manual CLI calls; generic batch helper rejects bounds >4, booleans, non-allowlisted identities, duplicate IDs and malformed responses. GitHub Action permissions, OIDC, required CI/quality, exact SHA, paid budget controls and human release observer semantics do not change.
- Product/Direct/Codex/Preview remain single-item and governed by their existing cost, identity, quota, safety and release policies. Batch processing neither issues paid model calls nor invokes a merge operation. The scheduled job executes only when the authoritative queue probe signals work; no extra cron, GitHub Actions or Vercel deployments are requested.
- Regression tests include 8 deterministic batch invariants and workflow contracts. Following a human merge, verify the next *actual eligible work* and not merely the scheduler heartbeat; no newly eligible work is presently live. Do not interpret this implementation as E2E greenfield completion.

## 2026-10-15 — Auditoria real OIDC da Edge Function broker v2 (#822)

**Escopo:** apos autorizacao humana separada, Supabase `factory-visual-evidence-broker` foi publicado em v2 ACTIVE; o arquivo remoto `index.ts` coincide com `main` `0c206195...`. A captura autenticada #38667957692 anterior ao deploy da v2 nao prova o comportamento do novo broker.

**Gatilho confiavel:** o workflow `.github/workflows/authenticated-visual-evidence.yml` executa codigo confiavel de `main` em `push` que altere `.github/authenticated-visual-target.json` (alem de workflow/script); o arquivo aponta para o ultimo Console READY `34c614be92a544bb52c1b2634fc6c82b1be6d25e` em `https://ai-product-factory-console.vercel.app`. O candidato altera apenas metadado `purpose` e docs/testes; depois do **merge humano** cria um novo ID de workflow para a prova do broker v2. Nao habilitar `pull_request_target`, push de branch nao confiavel, ou auto-merge, e nao usar `rerun failed jobs`: o run ID e unico no ledger. Nao ha mudanca em `apps/console/**`, portanto nenhum Preview/deployment Vercel se aplica.

**Criterios verificaveis:** (1) workflow de `push` em `main`, `run_attempt=1` e passo OIDC de provisioning concluido na v2; (2) captura autenticada nas rotas, inclusive `/runs` sem CSS 404; (3) viewport 390px de `/configuration`, `/projects` e `/` sem overflow; (4) `status=success` no workflow, artefato `authenticated-console-<new_run_id>` presente e registro em `factory_visual_evidence_runs` com `status=captured` ligado ao SHA do run; (5) operador temporario removido, sem vazamento de password/token/key nos logs. `status=prepared`, erro 403, run duplicado, falha HTTP de asset, artefato ausente ou cleanup incompleto mantem o gate fechado.

**Limites:** toda verificacao deve usar o SHA exato do deploy do Console e o SHA real do run GitHub, sem atribuir o commit de documentacao a uma compilacao Vercel inexistente. API key / WIF OpenAI, Codex, benchmark 63, novas migrations e custos pagos estao fora do escopo. Somente apos evidencias funcionais novas fechar a issue #822. O gate de product readiness global #713 permanece independente.

## 2026-10-15 — Bounded pagination do cooldown Vercel (fix pós-#811)

- Fato verificado: `Promote exact PR candidate to Vercel Preview` run #38657573456 falhou na etapa `scripts.preview_provider_cooldown` com `recent PR inventory exceeds safe bound`. A consulta tinha 52 PRs atualizados nas últimas 24h, ultrapassando o limite artificial de 50. Isso bloqueou a promoção antes de qualquer chamada à Vercel.
- A leitura do cooldown passa a paginar até cinco páginas de 100 PRs por consulta, mantendo duas fontes: PRs atualizados recentemente (inclui fechados) e todos os PRs abertos, inclusive antigos. Revalida estrutura, horário, ordenação e limites; inventário parcial continua bloqueando. O máximo de 500 registros candidatos continua deliberadamente fail-closed; nenhum token, serviço, permissão, scheduler ou ref privilegiado é alterado.
- Testes reproduzem 52 PRs recentes, falha Vercel encontrada na segunda página, PR aberto antigo com rate limit recente, inventário excessivo e ordem inválida. Ausência de rate limit continua sendo observação não autoritativa de quota, não promessa de disponibilidade.
- PR #811 foi **mergeado por humano** em `34c614be92a544bb52c1b2634fc6c82b1be6d25e`. Vercel de produção marcou deployment como concluído no SHA, CI de pós-merge verde. Auditoria visual autenticada pós-merge #38658173777 necessita leitura separada dos resultados. Este patch é somente Python/tests/docs; Preview Console não é requerido e merge em produção continua humano.

## 14/10/2026 — Candidato consolidado de Console: uma promoção de Preview, gate humano preservado

Este PR #811 agrega três candidatos antes separados: #786 (bootstrap/continuação transacional e RPC previamente aplicada), #789 (diff cumulativo de Vercel Preview) e #811 (legibilidade mobile, readiness fail-closed, inventários paginados e diagnóstico da fila). O propósito é validar uma única vez o mesmo SHA com Console CI, PostgreSQL isolado, Preview Vercel e Playwright autenticado, reduzindo a quota consumida por candidatos intermediários.

**Segurança:** a migration `20261014160500_atomic_project_continuation.sql` já foi aplicada anteriormente ao Control Plane com aprovação humana. Este PR NÃO a reaplica nem executa mudanças no banco; o workflow PostgreSQL roda contra instância de CI descartável. PRs originais permanecem abertos até CI do consolidado ficar verde, quando poderão ser encerrados SEM merge como substituídos. Preview em apps/console exige Vercel READY e browser evidence no SHA exato; não herdar evidência dos SHAs anteriores. Publicação de produção exige merge humano.
## 14/10/2026 — Console: filhos de pais concluídos não somem da fila (#713)

A leitura read-only do Control Plane confirmou 10 tarefas em status queued, sendo 5 da Factory e 5 do CRM, todas descendentes de tarefas-pai completed; nenhuma possuía run ativo. A página de fila descartava esses descendentes por status do pai e podia exibir fila vazia. Essa apresentação não comprova que os filhos foram implementados e escondia um diagnóstico relevante.

O Console agora mantém o inventário completo limitado a 100 tarefas + sentinela de paginação. Ele consulta pais e projetos de forma obrigatória (erro HTTP ou resposta incompleta falha fechado), distingue itens operacionais de tarefas que exigem reconciliação, informa o status do pai e nunca usa essa classificação como autorização de execução. Somente após reconciliação de Work Units, dependências, run e gates um caminho de retomada pode ser decidido; **este patch não reativa trabalhos nem cria migrations**. Os contadores de despacho excluem os registros apenas diagnósticos, mas eles permanecem visíveis em seção própria.

Alteração no Console requer CI/build e Preview/browser SHA-exato; não comprova automaticamente a ausência de overflow mobile. O PR #811 permanece draft e produção é gate humano.
## 14/10/2026 — Console: relatório operacional completo ou falha explícita (#713)

Após a paginação de runs no backend (#807), o Console ainda consultava apenas 200 runs e 1.000 eventos de uso; quando o ledger falhava, uma resposta vazia podia ser exibida como custo zero. O Console agora pagina ambas as tabelas com ordenação verificada por created_at e id, limites de 200 por página e 4.000 por fonte; IDs de runs são UUIDs e IDs de uso são BIGINTs. A leitura detecta duplicidade, respostas truncadas, quebra de ordem, falha HTTP e valores inválidos, e falha fechada em vez de declarar saúde operacional.

O status de runs falhos é correlacionado com a tarefa atual em lotes de 100, e dead-letters já recuperadas não voltam a contar como incidentes ativos. Custo de modelo pago sem valor registrado permanece explicitamente desconhecido. Nenhuma dessas contagens concede autorização de dispatch ou atesta product_ready.

Offset REST não é snapshot transacional durante concorrência. Falhas detectáveis de deslocamento são bloqueadas; um próximo passo opcional seria RPC de inventário transacional após revisão de schema. Regressões funcionais executam a implementação TypeScript real com Node, compilada localmente pelo TypeScript instalado no npm ci do Console: >200 runs, >1000 custos, BIGINT, HTTP 503, páginas duplicadas/desordenadas, valor desconhecido, status recuperado e limite de 4000. Esta alteração afeta apps/console/** e precisa de Preview com SHA exato antes de merge do #811. Não houve Vercel deployment nem mutation de banco.
## Auditoria autenticada de viewport 390px: configuracao (14/10/2026)

O run de produção GitHub Actions `38638289607` falhou no Playwright durante a verificação de `/configuration`: `document.documentElement.scrollWidth=458` com `innerWidth=390`. O CI/build #808 foi verde, mas não representa validação visual. Este candidato adiciona classe de grid `configOverviewGrid`, tracks `minmax(0,...)`, wrapping de dados/repositórios longos e empilhamento mobile para cards/configRows/compactRows. O teste de navegador **continua fail-closed**: ao detectar largura excessiva, agora registra tag/classe/width/right dos elementos responsáveis, sem texto, credenciais ou valores de campos. Não esconde overflow via `body{overflow-x:hidden}`.

Trata-se de correção de código e teste de contrato CI; **não** é evidência de que o overflow em produção já foi corrigido. O PR #811 deve ficar draft até Vercel Preview READY + navegador autenticado no seu SHA exato, sem conflitar com #786/#789. Nenhuma migration, token novo ou merge automático.

## Consolidação de auditoria do Console (#795 + #798)

Este candidato combina legibilidade responsiva e avaliação rigorosa da prontidão global, reduzindo para um único Preview SHA-exato após liberação do Vercel. CI de código não substitui verificação visual de navegador, revisão acessível ou gate humano de release. Esta seção não afirma produto pronto.

## Product-readiness evaluation and current HEAD distinction (14/10/2026)
Audit #713 found that the Console previously treated an evaluation result JSON's own `ready:true` and `status:passed` plus a self-consistent `assessed_commit == baseline_ref` as enough to display **Produto pronto**. This could misrepresent a failed evaluation row, populated blockers, missing coverage, malformed domains, or stale project HEAD. The Console now checks the evaluation row status, empty blockers, exact 40-char SHA and all six mandatory domains with explicit verification state, coverage and evidence before labeling the **evaluation** approved. It no longer says the product is ready globally from this record alone: an audit at SHA N does not prove that the repository's current HEAD is still N or that release gates/Preview/CI are satisfied.
This is a defensive presentation and read-boundary change, not proof of live E2E readiness. A future authoritative current-head check and full-product release assessment remain part of audit #713; no GitHub credentials are placed in browser code. The latest observed production CRM evaluation was `failed/not_ready`; the patch does not turn it into passing. This PR changes `apps/console/**`, so browser Preview of the exact final SHA is required and remains blocked by the provider's observed deployment rate limit.

## 14/10/2026 — Draft to Ready desperta Preview sem novo gatilho privilegiado (#797)

O Console CI nao reagia a ready_for_review: tirar Draft nao cria push e nao ativa o workflow de validacao por padrao. O gatilho de pull_request read-only agora enumera opened, synchronize, reopened e ready_for_review, mantendo os mesmos filtros de path/branch e permissions: contents: read. A mesma validacao de typecheck/build volta a rodar, e seu evento workflow_run de sucesso pode acordar o promotor confiavel ja existente em main.

O promotor ainda verifica PR open/nao Draft, mesma origem/base, SHA exato, checks verdes, mudanca apps/console/**, cooldown de rate limit e limite de budget antes de atualizar ref ou disparar navegador. Nao foi adicionado pull_request_target, issue_comment, cron, novo token de escrita, permissao de Console ou auto-merge. Gatilhos privilegiados existentes permanecem intactos.

Este patch nao confirma Preview do PR #811 ou #789, nem contorna a quota Vercel; transicao para Ready deve ocorrer apenas quando a disponibilidade do provedor estiver adequada. PR #786 que ja estava Ready antes do patch nao gera evento retroativo. O merge em main continua gate humano.

## 14/10/2026 — Alertas desacoplados do schedule-probe (Falha 38619635786; #809)

**Evidencia de producao:** workflow nativo agendado #38619635786 observou filas e gerou heartbeat, mas `Evaluate operational alerts in the shared scheduler runner` falhou com `RuntimeError: cost usage inventory has invalid or duplicate ID`. A falha no step final invalidou o job `schedule-probe` e fez todas as lanes de trabalho dependentes dele serem puladas, mesmo com a sondagem de filas bem-sucedida. A validação do ledger foi corrigida depois, mas o acoplamento continuava perigoso para qualquer futura falha de observabilidade.

Correção: mover a reconciliação de alertas do último step de `schedule-probe` para o job `alerts` **já existente**, usando `always()` para `schedule` e preservando o `workflow_dispatch/run_alerts=true` com check de probe. Os processos de recuperação, heartbeat e roteamento seguem sob `schedule-probe`, com as mesmas restrições. Uma eventual falha de `alerts` **continua vermelha e visível no workflow nativo**, mas não cancela `product-stage`, `dispatch`, `ci-followup` e demais lanes com `needs.schedule-probe.result == success`. O job de alertas não recebe `FACTORY_GITHUB_TOKEN` cross-repo; o probe perde escopo `issues: write` porque só o job de alertas deve escrever Issues. Nenhum cron, trigger, ambiente, modelo pago, migration, Preview ou autorização de produção é adicionado.

O alerta #809 segue aberto até **duas execuções nativas agendadas completas e com sucesso**, não apenas alert-only ou backups. Esse patch evita bloqueio transversal, não afirma que o GitHub tenha voltado a emitir cron nem substitui evidência real de recuperação pós-merge.

## 2026-10-14 — Fechamento TOCTOU do Preview (issue #797, patch sem ampliar acesso)

O pipeline `.github/workflows/promote-preview-candidate.yml` permanece exclusivamente disparável por `workflow_run: Console validation completed` e `workflow_dispatch`, operando apenas com código fixado da main. Nenhum novo evento `pull_request_target`, `ready_for_review`, concessão de token, terceiro servidor ou merge automático é habilitado neste patch.

Após a espera pelos três checks, o verificador consulta novamente o PR e impede `reused` se ele deixou de estar aberto, não-draft, base `main`, same-repo ou SHA exato. Após cooldown e budget, o **próprio passo de escrita** consulta uma nova cópia do PR, lista mudanças `apps/console/**` e exige `test`, `factory-acceptance` e `validate` com status `completed/success` no candidato antes de `git.updateRef`. A etapa de navegador só funciona após uma ação `reused|updated|created_then_updated`, revalidando o PR e consultando `preview/pr-N` para confirmar SHA idêntico antes de disparar verificação. Mudanças concorrentes levam a `skipped_stale`, `skipped_no_console`, `skipped_checks` ou `skipped_ref_mismatch`; nunca ao falso sucesso do Preview. A summary durável do Actions registra a ação e o navegador independentemente.

A integração ao gatilho `ready_for_review` é trabalho **separado** e depende de revisão das permissões do evento privilegiado: não foi ativado aqui. Run antigo, CI verde e Preview de SHA anterior continuam insuficientes para autorizar release. O PR de código de workflow não muda `apps/console/**`; Preview da Factory não é aplicável a este patch. Merge que publica produção continua humano.

## 14/10/2026 — Dependabot e CI do Console sem ampliar privilégios (#808)

O CI do PR #808 (upgrade `actions/setup-node`) falhou no passo `Enforce Console branch convention` porque toda branch `dependabot/**` era rejeitada, embora a automação já fosse autorizada a abrir PRs e o workflow seja `contents: read`. A exceção agora exige simultaneamente autor autenticado `dependabot[bot]` e head repository idêntico ao repositório da Factory, obtidos de campos separados do evento GitHub (não do nome da branch). Forks, nomes falsificados e `preview/**` continuam bloqueados.

A alteração não cria gatilhos privilegiados, não amplia permissões, não fornece secrets e não chama o Vercel. Testes unitários executam o script bash do gate com identidade real, spoofing, fork e ramos permitidos. O PR #808 ainda precisa de CI verde sobre o SHA correto após incorporação deste patch e de revisão humana do update Dependabot. Merge em produção continua gate humano.

## 14/10/2026 — Preparação fail-closed do Preview (#797; sem ativação privilegiada)

\`scripts/preview_candidate_contract.py\` define um contrato **puro e determinístico** de elegibilidade:
PR aberto e não-draft, origem/destino no mesmo repositório confiável, base \`main\`, SHA completo idêntico, checks \`test\`, \`factory-acceptance\` e \`validate\` verdes no SHA exato, e alterações verificadas em \`apps/console/**\`. O segundo predicado só admite evidência de navegador se a promoção tiver resultado comprovado \`reused\`, \`updated\` ou \`created_then_updated\`, e o ref observado continuar no SHA exato.

**Isto ainda não altera o pipeline.** O workflow privilegiado de promoção deve buscar **novamente** PR, checks e ref imediatamente antes da escrita; um resultado anterior à espera por CI não é garantia de estado atual. A integração e o gatilho \`ready_for_review\` são mudança de segurança e precisam de revisão/aprovação explícita das permissões do GitHub Actions. Não houve criação de trigger, modificação de workflow, promoção de ref, Vercel deployment ou merge. O PR #811 permanece draft até Preview/browser evidenciarem o SHA candidato ou a política explicitamente permitir outro caminho.

## 14/10/2026 — Confirmacao pos-merge das correcoes de operacao

- PR #806 mergeado em `2c604bec`: o alerta `scheduler_pipeline` foi exercitado pela reconciliacao `/factory-alerts` (run `38628800312` SUCCESS); issue #809 foi aberta pelo bot, pois run agendado #38619635786 concluiu FAILURE. `scheduler_gap` (heartbeat) estar fechado nao equivale a pipeline recuperado.
- PR #807 mergeado em `10016635`: CI de push `38629927087` SUCCESS; issue #804 encerrada. Scan paginado de `factory_runs` e leitura em lotes sao codigo de producao, mas **nenhuma validacao com mais de 200 runs reais** foi feita: o banco possui 81. Regressao simulada no CI cobre >200.
- Para o proximo ciclo, confirmar duas `schedule` de `autonomous-runner.yml` nativas, consecutivas, com `conclusion=success`, antes de fechar #809. Rerun, `workflow_dispatch`, issue_comment e OIDC backup nao contam. Nao criar trabalhos falsos, creditos de API nem redeploy do Vercel.
- Ao testar #786, conferir SHA exato e sinais READY + browser, sem reutilizar URLs antigos. A migration RPC ja esta aplicada; evitar executa-la novamente. Publicacao de producao exige gate humano.
- O diagnostico de custos/saude nao concede permissao para dispatch ou calls pagas.

## Operational runs: complete bounded read, no false healthy totals (2026-10-14 candidate #804)

\`SupabaseOperationalHealthReader\` must not infer the current number of failed, dead-letter, or expired-lease incidents from the latest 200 \`factory_runs\` only. The run history now paginates in deterministic \`created_at desc,id desc\` order (200 records/page, up to 20 pages), validates unique run IDs and known statuses, and **raises an error** instead of reporting incomplete totals. The limit is intentional (4,000 runs): reaching it without observing the final short page fails closed. Failed-run parent task statuses are fetched in bounded 100-ID batches, preserving the rule that recovered/completed tasks suppress obsolete historical failure warnings. Independently partitioned Preview and usage-ledger scans keep their earlier rules.

\`offset\` pagination is not a transactional snapshot. Concurrent inserts/deletes can move boundaries; overlapping IDs or inverted timestamp order are detected and rejected. Missing rows caused by concurrent shifting that produce no duplicate cannot be ruled out by offset scans: for immutable complete historical accounting at much higher volume, use a privileged transactional snapshot/keyset pagination strategy in a separately reviewed change. Operational health is **observability**, never evidence authorizing paid-model calls, dispatch, or release. No production schema change, paid model usage, Console Preview, or new token permission is required.

Observed production on 2026-10-14: 81 total Factory runs, so the 200-row truncation was a latent growth hazard, not a live missing incident. Tests exercise 201+ histories with failed/expired/recovered incidents, duplicate IDs, invalid statuses/timestamps, batch lookup, and bounded overflow. Merge into production still requires the human gate; after human merge, verify scheduled alert evaluation against a read-only Control Plane snapshot.

## Native scheduler completion vs heartbeat (2026-10-14 candidate)

The existing \`scheduler_gap\` is a **delivery-cadence** warning derived from two native \`schedule_probe.native_observed\` events in Supabase. Those are emitted before alert evaluation; therefore they cannot prove the GitHub Actions workflow completed successfully. A manual \`/factory-alerts\` pass can legitimately clear the cadence warning while a preceding native workflow failed. Never claim an autonomous runner is end-to-end healthy on that basis alone.

\`scheduler_pipeline\` independently observes the GitHub Actions REST \`actions/runs?event=schedule\` inventory, filtering to \`.github/workflows/autonomous-runner.yml\` on the trusted \`main\` repository. It requires the **last two completed** native scheduled workflows to have \`conclusion=success\`, with the newest fresh (under 2 hours) and the completion observations within 2 hours. The currently running scheduled workflow is not considered complete; unrelated scheduled preflights, dispatches, owner comments and backup wakes never count. Read-only API errors or malformed results retain a warning and cannot silently resolve the issue. This uses the existing GitHub token/client and opens/closes only the existing deduplicated alert mechanism; no extra cron, workflow permissions, database migration, paid provider, or deployment is introduced.

After a human merge, a **real** scheduled runner must complete twice (at timely intervals) for pipeline health. Verify the GitHub Actions run IDs/conclusions independently; alert-only checks are evidence of the alert system, not the completion of the native runner. If the token cannot read the Actions inventory, investigate its existing permissions before making any access expansion. No automatic permission change is authorized by this patch.

## Hotfix: production BIGINT cost usage IDs (2026-10-14)
At native scheduled run [38619635786](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/38619635786) at 18:58 UTC, the alert step failed with `RuntimeError: cost usage inventory has invalid or duplicate ID` introduced by #803. The live schema proves `factory_tool_usage.id bigint NOT NULL` (identity sequence), so PostgREST returns the IDs as JSON numbers, whereas #803's read-only pagination erroneously required strings. Live SQL verified 97 distinct/non-null IDs; no corruption.
The reader now accepts signed-BIGINT-range **positive integer** JSON values or decimal-string forms and normalizes them to the same canonical ID before duplicate detection. It rejects booleans, floats, zero, negatives, malformed strings or out-of-range values. Existing cost pagination and fail-closed budget/ledger semantics remain unchanged. Tests use numeric IDs mirroring the production schema, include numeric-string cross-page duplicate detection and invalid boundary values.
The two genuine native scheduler heartbeat rows at 18:40:54Z and 18:58:22Z now meet the heartbeat timing threshold, but the second *whole run failed*. Scheduler recovery must not be declared operationally end-to-end until a successful alerts-only / real scheduled validation after this hotfix's human merge. No database migration, spending or Preview is needed.

## Complete operational cost observation and recovered dead-letter signal (2026-10-14)
The operational alerts reader formerly selected only the newest 1,000 `factory_tool_usage` rows and summed them as though they were the entire historical budget, potentially suppressing `budget_exhausted` and `unknown_cost` warnings when usage exceeded the page. It now retrieves deterministic 1,000-row pages ordered by `created_at,id`, validates unique row IDs and nonnegative finite amounts, and refuses an incomplete inventory after a bounded 20-page limit. Partial or malformed observations are errors, never successful budget totals; underlying model-execution paid ledger and production purchase/authorization gates remain separate and unchanged. At verification, Supabase held 97 tool-use rows, so overflow was a future-safety bug, not an observed current budget breach.
The same reader previously counted historical failed runs with `maximum attempts` as dead-letter incidents after their tasks were recovered/completed. It now counts failed/dead-letter incidents only if the linked task remains failed, and it rejects incomplete failed-task lookup results. This preserves existing previews and has no database migration, model request, or dashboard code change.
Regression exercises >1,000 usage events including late unknown paid cost, duplication across pages, invalid/negative amount, recovered historical failure and missing task records. Read-only GETs with bounded paging; no changes to control-plane data.

## Backlog inventory — unknown Work Unit state fail-closed (14/10/2026)
The live PostgreSQL CHECK constraint `factory_change_set_work_units_status_check` enumerates exactly `pending, queued, running, completed, integrated, failed, blocked`. Prior to this hardening, the read-only inventory accepted *any string* as a unit status, counted it as not active and could report a completed-parent child as historically inactive even if the database contract had drifted or the response was corrupted.
The reader now rejects an unknown/missing/non-string Work Unit status with `RuntimeError`. The seven states allowed by the current database constraint retain their previous active/inactive classification and diagnostics. This does not mutate Work Units, change dispatch/claim permissions, infer queued-work eligibility, or require a migration. Tests cover every allowed state plus malformed/unexpected values. Keep this classifier distinct from the authoritative atomic planner/dispatcher.

## Queued children under completed parents: diagnostic visibility (14/10/2026)
The versioned migration `20261006023500_completed_parent_keeps_backlog.sql` explicitly restores queued children under a completed parent: completion can satisfy a dependency rather than terminate a child's backlog. The live read-only inspection found **10 queued children of completed parents**, of which **8 have no Work Unit** and **2 have integrated Work Units**, with zero active Work Units. The original backlog inventory labeled all ten historical, which is not sufficient evidence that all ten are ineligible for future materialization.
The inventory now preserves its existing summary fields for compatibility and exposes separate `completed_parent_without_work_units` and `completed_parent_with_inactive_work_units` counters. Unknown/non-terminal parent states, including `failed` and `merged` when no policy establishes task-level terminality, remain visible through `other_queued_without_active_units` and `unverified_parent_status_without_active_units`; malformed parent status fails closed. This is **read-only diagnostics**, not automatic dispatch, backlog reactivation, state repair, or proof that any child should execute. The actual source of dispatch eligibility remains the authoritative planned-work RPC and claims with human gates.
The prior #800 suggestion to simply add `failed/merged` to a terminal set was rejected after checking actual task statuses and the completed-parent migration: neither status currently appears in `factory_tasks`, and neither should silently suppress potential work without a separately reviewed lifecycle policy.

## Draft PR Preview observability (14/10/2026)
A Console validation on draft PR #795 triggered the automatic Preview promotion, but the resolver returned a red workflow for an intentional non-deployable draft. This is an *inapplicable candidate*, not a failed build. The resolver now emits `not_applicable_draft` only for a verified open, same-repository main-branch PR whose SHA matches the successful CI and whose trigger is automatic. It does not update Preview refs, call Vercel, consume quota or dispatch browser evidence. Explicit manual attempts still fail closed for drafts. Mark a Console PR ready for review only after policy permits real Preview and the provider rate limit is no longer observed. No UI/release success is inferred from green CI or from the draft skip.

## Preview rate-limit guard: recently closed PRs and superseding Vercel statuses
After PR #792 merged, the observer's initial version checked only open PR heads. A Vercel rate-limit failure could vanish from that inventory when a PR was merged or closed, and a newer Vercel success on the same SHA could otherwise be masked by historical failures. The guard now inventories open and recently closed PR heads within a rolling 24-hour window, reads bounded Vercel commit status history, and treats a newer verified success as superseding older failures on the same SHA. A pending state does not clear cooldown. Incomplete/truncated inventories, missing timestamps and invalid status history fail closed; no false assumption of quota availability is made.
This is an additional preventive signal, not an authoritative provider quota. A rewritten/superseded PR head from an earlier ref may still be missed; source-of-truth rate-limit data from Vercel or the Control Plane would be required to remove that limitation. No Vercel token, API purchases, Preview build, or production mutation is needed to test this change.

## Vercel Preview rate-limit observation cooldown (2026-10-14 candidate)
When GitHub receives a Vercel commit status such as `Deployment rate limited — retry in 24 hours`, new Preview promotions must not burn more attempts. The provider status is a negative signal, not a complete quota measurement. `scripts.preview_provider_cooldown` reads current open PR head statuses using GitHub REST before the existing budget observer: a recent exact Vercel rate-limit message blocks for a 24-hour observation window; unknown inventory, authorization and status errors fail closed. It does not require a Vercel token, buy credits, alter limits, write to Control Plane or disable browser evidence. After 24 hours the check may be retried, but a green GitHub preflight does **not** guarantee available Vercel quota. Scope: only open PR heads; a rate-limit on an already closed or superseded head may not be observed. The official Vercel API limit snapshot remains authoritative when configured, and no false quota confidence is inferred from negative signals alone. If the candidate's exact SHA is currently Vercel rate-limited, leave the release in draft/awaiting_release, not merged. The existing production human gate is unchanged.

## Verified release ordering after PR #789 (2026-10-14)
1. Review PR #787: manual and automated Preview dispatches must both verify exact open same-repository main PR head, non-draft and `apps/console/**` changes. PR #787 has green `validate` and Preview N/A because it changes only workflow/tests. Merge only via the human production gate; the runtime GitHub adapter has **no automatic merge capability**.
2. After the merge is observed and main CI reconciled, PR #789 may be marked ready for human review if its exact Vercel/Browser status remains successful. The candidate `a87cbb38...` has `Vercel=success` and `Factory Preview browser evidence=success` backed by trusted Actions workflows. A **human** then decides on the main merge; do not deploy any Preview simply to 'check again' when candidate evidence is already exact and green.
3. PR #786 remains draft until an operator explicitly approves and applies the versioned atomic-continuation migration in production, then verifies the RPC signature, `service_role`-only grants, shared project lock, and Supabase migration history. CI and Preview **cannot replace** database installation evidence.
4. Do not clear scheduler_gap issue #790 based on OIDC preflight, alert reconciler, manual dispatch, or the first recovered Cron event. Observe at least two timely consecutive native scheduled heartbeats and re-evaluate freshness. Treat a stale native scheduler as degraded autonomy even if overall CI is green.
5. The Vercel ignored-build step executes `sh ./vercel-ignore-build.sh` from the Console root; only `preview/pr-N` promoted refs are eligible for candidate builds. It compares against `VERCEL_GIT_PREVIOUS_SHA` when the previous SHA exists in the Git checkout; missing/unavailable history builds rather than claiming no change. Non-candidate Preview refs are skipped. The script's exit codes follow Vercel: 0 ignores; 1 builds. All rollout validation uses exact SHA and browser evidence; do not infer provider deployment from local tests.

## Atomic project continuation — deployment order (14/10/2026)
1. **Do not merge PR #786 while the production RPC is absent.** CI and a verified Vercel Preview do not apply SQL automatically. The candidate is deliberately a draft pending this administrative gate.
2. Human operator reviews `supabase/migrations/20261014160500_atomic_project_continuation.sql` at the exact candidate SHA, validates diff and applies it through the official privileged Supabase migration path with explicit production approval. No scheduler, agent or GitHub adapter may apply it.
3. Read-only production verification should confirm `to_regprocedure('public.factory_enqueue_project_continuation(text,text,uuid,integer)') is not null`, `FOR UPDATE` in `pg_get_functiondef('public.factory_enqueue_project_bootstrap(text)'::regprocedure)`, and restricted function EXECUTE grants to `service_role` only. Check Supabase migration history as well. Never claim deployed based solely on an API 200 or CI success.
4. **Only after step 3:** mark PR #786 ready for review, revalidate expected candidate SHA, CI, Preview/browser checks and release policy, then perform the human production merge. Verify Console health and a legitimate continuation run separately; no synthetic product tasks or paid model probes.
5. If the migration is not approved, leave PR #786 in draft; keep the current Console/Control Plane in place. If a response to an already submitted continuation is ambiguous, do not delete private files merely because HTTP returned 409/5xx or timed out; the request may be durably committed. The isolated PostgreSQL workflow checks same/different request races, transaction rollback, historical children, existing bootstrap race and service-only privileges.

## Do not clear scheduler gap after one cron event (candidate)
A native `schedule_probe.native_observed` record proves one successful GitHub schedule wake, **not a stable cadence**. The liveness contract now requires the two newest native records to both exist, the newest to be younger than two hours and their separation shorter than two hours before `scheduler_gap` can resolve. Old generic audit events and operator/backup `issue_comment`/`workflow_run` wakes never count. This intentionally preserves warnings after a cold start or prolonged outage until the second timely native wake.

Issue #772 was prematurely closed at 13:47:10 UTC on 14/10 after only the first native record; this was a logic bug, not proof of health. The GitHub alert adapter currently searches only open marked issues, so it may create a new numbered warning when the corrected reconciler first runs. Record linkage to #772 in that new issue; never close it based on just CI green or an owner manual wake. No changes to cron frequency, queue dispatch, Preview or human production gate.

## Scheduler native heartbeat provenance (candidate)
Use schedule_probe.native_observed for GitHub event_name=schedule only. A workflow_run fallback or manual operator wake records schedule_probe.observed, never proving the native cron healthy. A native heartbeat write failure fails that probe; backup telemetry may remain best effort. No schema changes. Verify live schedule and native DB event after human merge; do not close scheduler_gap on fallback-only success.

## Required CI and human-only DoD whitelist (candidate)
Candidate release readiness requires `github_ci` explicitly satisfied; absence of the key blocks even if the DoD lists are structurally valid. A missing item can be marked `human_only: true` only when its key is exactly `human_release`. Any other human-only claim is treated as an unauthorized attempt to waive a deterministic gate and blocks release. These rules supplement strict JSON booleans and duplicate/conflict validation. They do not themselves certify the CI run for a SHA; the evidence collector must still verify exact SHA check-runs and Preview as applicable. Even a legitimate candidate remains subject to the human production merge gate.

## Fail-closed Definition of Done inputs (candidate)
When preparing a release assessment, do **not** coerce `human_only` or allow untyped DoD `missing` entries to vanish. Only a literal JSON boolean `true` denotes a human-only item. Strings such as `"false"`/`"true"` and numeric flags are invalid and block release. Omitted or malformed `definition_of_done.satisfied` or `definition_of_done.missing` arrays, duplicate missing keys, invalid missing rows, and simultaneous satisfied/missing keys also block deterministically. A missing DoD must never be treated as evidence that all checks passed. Separately, the human production gate always applies, even when nonhuman checks are complete.

## Mandatory product-readiness domains and evidence format (candidate)
The product-wide readiness evaluator may only accept `product_experience=not_applicable` for documented headless workloads, never `security`, `observability_operations`, `test_strategy`, `documentation`, or `functional_completeness`. Every mandatory domain needs full required coverage and valid evidence. `evidence` and `coverage` values must be lists of strings; any non-string entry fails closed rather than being coerced into a bogus reference. The release reporter reuses this evaluator for the SHA-exact product assessment.

This deliberately does not authenticate arbitrary external evidence strings or claim complete product readiness in absence of verified evidence. All production merge/release gates and provider Preview policies remain separate, unchanged.

## Exact-candidate full product readiness in release reports (candidate)
Release reports must **not** treat `facts.product_readiness.ready=true` as a trusted completion verdict. `build_release_assessment` now revalidates the six `domains` using the same deterministic `assess_product_readiness` contract and requires `assessed_commit == candidate_commit`, a real `assessment_ref`, coverage/evidence/verification state, and no critical blockers. `baseline_ref` is historical context, not equivalent to an assessed candidate SHA. When evidence is missing or malformed, the report stays `readiness_scope=release_candidate` and `product_complete=false`; no release outcome or human production gate is changed. In particular, Preview or CI for a single PR never constitutes a whole-product assessment.

## Conditional backup alert observer via OIDC preflight (candidate)
Scheduled GitHub Actions events can be delayed/dropped under load even with off-hour-minute Cron entries; no code-only change can guarantee cron delivery. The existing `control-plane-oidc-preflight.yml` runs every six hours and is an independent workflow file in the **same GitHub provider** (not a separate infrastructure scheduler). It now probes durable `schedule_probe.observed` timestamps read-only after its usual authenticated Control Plane check. Only if the existing `scheduler_gap` predicate is true does an alerts-only job start, authenticating via protected OIDC with read-only contents, OIDC token minting, and scoped GitHub issue write. No model, Codex or cross-repo credentials are injected; this fallback must not dispatch implementation work.

Investigate issue #772 and schedule delivery using GitHub Actions run history (event=`schedule`) against the Supabase timestamps. The `scheduler_gap` issue may stay open after a manual wake: do not treat manual calls as proof the native Cron is healthy. If an actual independent scheduler is required, the production Supabase project currently lacks `pg_cron` and `pg_net`; enabling it and furnishing a supported, scoped GitHub App/token for `workflow_dispatch` are separate infrastructure/access decisions requiring authorization. This candidate does not enable any extension, create recurring paid execution, or add cron frequency.

## Owner-only alerts wake without dispatch (candidate)
When scheduled GitHub Actions wakes are delayed, the safe recovery command is a *GitHub issue comment* containing exactly `/factory-alerts`, authored by the repository OWNER. It deliberately does not reuse `/factory-wake`, which can run the scheduler, recovery and executor lanes. A PR comment, a non-owner comment, altered/mixed command text, or an issue edit must not start the alerts job.

`alerts-owner-comment` independently checks out main, installs the pinned Python runtime, obtains protected Control Plane access via OIDC, validates availability fail-closed, and invokes only `python -m ai_product_factory.runtime_cli --mode alerts`. It gets only `contents:read`, `id-token:write` and `issues:write`; neither model nor Codex secrets are passed. Alert deduplication/reconciliation still depends on authoritative live DB data. Verify the workflow run and resolved GitHub issues after dispatch; never infer success from posting a comment alone.

This GitHub-hosted operator hook is not independent monitoring if GitHub Actions itself cannot start jobs. Production release, cost, auth and Preview gates remain unchanged.

## Scheduler wake-gap alerting (candidate)
Operational alerts now include `scheduler_gap` from the durable Control Plane `schedule_probe.observed` timestamps. The read-only health check inspects the newest two entries; a latest probe age >=2 hours or a separation >=2 hours raises a deduplicated warning. Missing evidence also warns. It uses normal alert issue marker/closing reconciliation and does not disclose credentials.

**Limitation:** GitHub cron is best-effort; if GitHub never schedules the Factory, this in-run detector cannot emit an alert until another scheduled or owner-triggered alerts-only run executes. This is not independent uptime monitoring and does not constitute a guaranteed wake SLA. Do not compensate by adding paid services, noisy deployments, or production work. Investigate the schedule itself and consider an independent, approved monitoring channel if a wake SLA becomes a requirement.

## Read-only queued backlog audit (candidate)
When `schedule-probe` reports no executable work, it does NOT imply all `factory_tasks` are terminal. Historical planning child tasks may remain `queued` under completed parents with no active `factory_change_set_work_units`. Use `python -m ai_product_factory.runtime_cli --mode backlog-audit` for an explicitly read-only report, or inspect its best-effort scheduled log when `work_detected=false`.

The reader uses only GET queries with bounded rows (100 queued tasks, 500 work units), validates all identities and parent references and fails closed rather than misreporting partial data. It does not promote tasks, create runs, claim work, contact a model, or infer human release approval. A queued task with active unit is still not necessarily dispatchable: only authoritative scheduler/claim gates decide. No schema migration is needed.

## Stale Preview alert provenance (candidate)
The operational health reader now separates real overdue delivery candidates from historic product-readiness audit rows (`metadata.source=dogfood_manual_audit`) using the same `is_delivery_preview_run` rule as the Preview queue. It reads an oldest-first `preview_ready` partition, not the newest 200 general runs. An overflow >200, malformed row or missing delivery timestamp fails closed before the alert reconciler can incorrectly close an issue. This does not change run status, queue scheduling, quota, or Preview/production gate rules.

Post-merge, the existing `alerts` runtime can reconcile issue #754 when the current Control Plane reports no actionable overdue deliveries; no manual reset or invented Preview evidence is needed.

## Agent scope race prevention (candidate)
The follow-up migration `20261014092500_serialize_agent_scope_claims.sql` is **not installed until human release gate**. Agent-row `FOR UPDATE` locks alone cannot protect a scope hierarchy across two independently assigned agents. A transaction-scoped PostgreSQL advisory lock by project serializes the final scope-conflict query and insert inside `factory_claim_agent_slot`; no persistent lock row or new privileges are introduced. An empty scope array does not require project serialization. Per-run/per-agent protections still operate independently.

The dedicated `Codex PostgreSQL claims` workflow now loads the real versioned functions `factory_claim_agent_slot` and `factory_schedule_run_agent` instead of a simulated allocator. The test fixture schema is isolated and simplified, but concurrent PostgreSQL transactions exercise the same SQL bodies. Do not apply this migration or report production race protection until the merged SHA is confirmed and the official Supabase migration tool verifies function body and ACL afterward.

## Real PostgreSQL regression for Codex claim isolation (candidate)
Run `scripts/verify_codex_claim_postgres.py` only in the dedicated `factory_codex_claim_test` database on loopback with `FACTORY_CODEX_PG_TEST_ISOLATED=true`; the integration harness fails closed otherwise. The `Codex PostgreSQL claims` workflow provisions ephemeral Postgres 16 on GitHub Actions, installs the pinned psycopg client, and executes the exact versioned manual/automatic claim, scheduler and work-matrix functions in concurrent transactions. It never accesses the production Supabase project, calls Codex or grants new production permissions.

The generic agent allocator is represented by a minimal fixture, NOT by the real `factory_schedule_run_agent` function. Hence the suite proves mode-aware claim row-lock behavior and related route filters, not scope-lock/capacity allocator correctness. Existing RLS and cost/auth gates remain separate. Do not report full Codex end-to-end until protected auth, paid ledger, real task, PR/CI and human release observer are verified.

## Codex automatic agent claim hardening (candidate)
The follow-up SQL migration `20261014032600_codex_claim_agent_hardening.sql` is **not** installed yet. It requires both `codex` and `github_write` tools when choosing, advertising or claiming an automatic Codex agent. Scheduling rejects a mismatched agent returned by the generic role-aware allocator transactionally. The claimer rechecks exact agent key, task capabilities, active project and queued Work Unit with row locks and checks assignment update success. Python consumers also reject mismatched run/agent IDs. This adds defense in depth but **does not** prove simultaneous claim behavior without an isolated multi-transaction integration test. No synthetic work is created in the production Control Plane; official Codex auth, paid ledger and human release gates remain unchanged.

## Codex mode isolation (candidate)
New Codex runs are stamped manual/automatic in one transaction; both claimers filter exact mode. Untagged historical runs fail closed. Automatic Codex scheduling uses Codex-capable agents only and the exact run ID. Activation needs protected Codex auth and FACTORY_CODEX_COST_APPROVED=true; this variable remains off until cost entitlement and real ledger approval. Migration 20261014015500_codex_atomic_mode_isolation.sql was applied via the official Supabase migration tool after human PR #763 merge and verified against pg_proc ACLs; `codex_atomic_mode_isolation` is recorded in history. No automatic production merge.

## Codex routing safety: mandatory durable execution-mode isolation

The protected Codex route preflight added in PR #760 proves presence of
configuration only. It must **not** enable automatic Codex claims by itself.
The legacy `factory_claim_next_manual_codex_handoff` RPC currently accepts
every queued Codex run without checking an execution-mode discriminator.
Automatic Codex dispatcher/worker therefore cannot safely coexist with
the manual handoff consumer, even if the automatic worker is configured.
New automatic claims are temporarily fail-closed; explicitly enabled manual
handoffs are unchanged.

Activation requires a follow-up **atomic Control Plane migration**: stamp
`manual` or `automatic` in the same transaction that routes the run;
enforce that stamp in both automatic and manual claim RPCs; assign the exact
newly routed automatic run (not an unrelated queued run); and test both
concurrent claims in isolated transactions. Do not enable automatic Codex
until the migration is installed, CI and preview requirements satisfied and
official login/ledger gates approved. Never workaround by automatically
merging production.

## Independent Codex preclaim readiness and official access token fallback

The protected `openai-codex` workflow now exposes a strict boolean route
preflight to dispatch only when actual routed work exists and Codex is
explicitly enabled. It requires a complete official WIF federation mapping
or a configured `CODEX_ACCESS_TOKEN`, plus an explicit cross-repository
GitHub credential. Partial WIF rejects token fallback; secrets NEVER reach
the dispatcher or the Primary jobs.

This is a **configuration preflight**, not an official Codex login success:
the `codex` worker rechecks WIF/token, attempts the official auth mode and
fails closed before any model invocation if credentials are invalid.
Activation still requires a prior no-model auth validation recorded by an
operator; do not flip `FACTORY_CODEX_ENABLED` merely because a secret
exists. No token values or invented federation settings belong in docs.

Automatic Codex route authorization is independent from Primary budget or
API key. If Primary is disabled but Codex is explicitly active and protected
preflight passes, only Codex may be claimed. If neither route is available,
work remains unclaimed. The manual Codex path remains separate and
explicitly opt-in when automatic Codex is off. No auto-merge or Preview
policy is changed.

## Downstream stage wakeup without REST-window starvation

`factory_scheduler_queue_signals` now also uses read-only PostgreSQL
`EXISTS` for Change Set integration, CI follow-up, human release observation,
and queued specialist security/QA/operations work. These signals are
independent of 200/400-row history windows. Terminal specialist lanes never
wake a worker. Strict nine-boolean response validation fails closed when
the RPC is not yet deployed.

Preview retains its separate SHA, origin and quota policy. Direct/Primary
auth, Codex WIF, ledger/cost and human merge gates remain unchanged.
Deploy migration `20261014001500_extend_scheduler_queue_signals.sql`
after CI and human merge, and verify ACLs and empty-queue signals.

## Authoritative queue wakeup signals

The status-window scan is diagnostic only. The `factory_scheduler_queue_signals`
read-only, stable, security-invoker, service-role-only RPC uses indexed
PostgreSQL EXISTS/joins to detect genuine product runs, routed Direct/Codex
runs and pending manual Codex followups independent of legacy queue volume.
The query checks active projects and task/run state. New Work Units still
require the existing eligible portfolio RPC. This avoids false idle when
a genuine run falls between oldest/newest REST windows.

The scheduler fails closed if the RPC is missing, malformed or inaccessible;
do **not** treat that state as successful idle. Therefore
`20261013235000_scheduler_queue_signals.sql` must be applied and ACL-tested
immediately after a human merge, before depending on a production schedule.
Preview eligibility, quota, model/ledger gates and human release gates stay
unchanged. This is queue detection only, not paid-model authorization.

## Bounded queue join and newest-run fairness

When a run status partition reaches 200, the read-only probe samples **both**
the oldest and newest 200 rows for that status. This prevents a historical
manual-preview backlog from hiding new delivery work while retaining old FIFO
work. Because the task status partitions are bounded independently from runs,
the probe also resolves missing run/task references through batched exact
PostgREST task-ID lookups (40 IDs/request, 400 additional IDs maximum).
Identifier format and row membership are validated before use. A malformed
server response fails closed; all requests remain read-only and zero-model.

Audit diagnostics report capped status partitions and linked-task lookup
truncation so the system never claims exhaustive queue coverage beyond these
hard limits. Only a transactionally eligible Change Set wakes new dispatch,
and Preview still uses its source/sha/quota policy. This is not a replacement
for a future SQL-indexed existence RPC if one status exceeds these bounds.

## Status-partitioned work detection after recovery

The autonomous runner's read-only schedule probe used to fetch the oldest 200
runs across *all* statuses and 200 tasks across two statuses. Historical
Preview/audit rows could therefore hide newly queued Direct/ Codex work, and
legacy queued tasks could hide an active queued_execution task. The probe now
reads each status in an independently bounded 200-row partition, retaining
per-status caps in audit diagnostics and de-duplicating IDs by the latest
observed status if a transition happens while probing.

This affects only wakeup detection, not claim authorization. A pending Work Unit
still requires a real eligible portfolio candidate. Manual Preview audit rows
never cause deployment. A queued execution wakes the dispatcher, which still
checks executor readiness and the known-cost ledger before creating any new
assignment. Status partitions at the 200 cap are diagnostic evidence of possible
further backlog; do not claim complete coverage beyond that bound. No changes
to human merge gates, Primary activation or Codex WIF.

## Fail-closed recovery and route-isolated workers
The recovery job can requeue expired runs, resume decisions and release expired agent slots, but **must not allocate a new agent**. Generic `factory_schedule_next_unassigned_run` can select Codex manual or Direct work while its executor is disabled. Direct allocation is handled only by dispatch after Primary auth, real budget and ledger checks, through `factory_schedule_eligible_direct_run`.

When a Direct/Codex worker starts without an exact run ID, it may read only the durable existing assignments for its own route using `factory_agent_work_matrix`. It must not call the generic scheduler or implicitly create a new assignment. Missing assignments produce `empty`. Neither operation activates Codex WIF or Primary, requeues historical work, or authorizes a production merge.

## Route-safe Direct scheduling and post-gate recovery (PR #753 extension)

The versioned `factory_schedule_eligible_direct_run` RPC assigns only an
active project's Direct run when its run is `queued`, task is
`queued_execution`, and no assigned/claimed agent slot exists. It uses
row locks and passes the persisted agent role, capabilities and scope keys
to the existing capacity/scope-checked allocator. An explicit run ID
schedules a freshly claimed Direct candidate; a null run ID safely resumes
previously queued Direct work after human approval or agent-capacity recovery.
No Codex manual work may be scheduled by this RPC.

Python skips agent assignment for all `human_gate_required` runs and only
drains unassigned Direct work when Primary auth and the paid ledger have
passed the existing fail-closed gate. If Primary is disabled, it leaves
approved Direct work queued without consuming slots. Owner issue-comment
wakes can prepare independently enabled Codex manual handoffs.

Migration `20261013224500_schedule_eligible_direct_run.sql` must be applied
only after CI and human merge; until then the new RPC fails closed. No paid
model smoke or fabricated product task is authorized by these tests.

## Agent slots after atomic dispatch

The dispatcher must schedule the **exact run ID** returned by the atomic
route-aware claim. It must not call the global schedule-next RPC immediately
after a new claim, because that RPC can assign an unrelated older run.

Manual Codex handoffs are an intentionally unstaffed waiting state:
when the selected and approved route is Codex manual, no agent slot is
reserved. The dispatcher includes the claimed Codex route in its durable
output; the workflow uses that signal to wake the manual Codex prepare job
without requiring a work-matrix agent assignment. A Direct route still
receives an agent assignment by exact run ID and the planned preferred agent
key when specified. Empty/malformed claim IDs fail closed.

Previously assigned in-flight work and recovery remain separate concerns;
this patch does not requeue historical runs, enable Codex WIF, purchase
model credit, create Previews, or alter the production release gate.

## Manual Codex handoff — explicit opt-in and issue provenance

A **new** manual Codex handoff may be claimed only when
`FACTORY_CODEX_ENABLED` is not enabled and
`FACTORY_CODEX_MANUAL_FALLBACK_ENABLED` is explicitly the exact value
`true`. An unset, empty or malformed flag is **disabled** in both the
GitHub Actions prepare step and the Python worker. The dispatcher has the same
strict default-off rule. This avoids accidentally claiming a task that would
need a human Codex operator.

For a pre-existing handoff the read-only PR-followup path remains usable even
if the opt-in flag has since been disabled; no new handoff is claimed during
followup. Before marking any new handoff `awaiting_codex_manual`, the worker
confirms the Issue's body contains the exact Factory run marker and, when an
Issue was previously bound, the Issue number still matches. A mismatch aborts
before persisting a new binding or transitioning the run.

This is a human **implementation handoff**, not proof of autonomous Codex WIF
execution or a license for automatic merges. Do not enable manual fallback
solely to manufacture an E2E test or reactivate old plan tasks.

# Operations Runbook

This runbook describes the safe operating modes of the AI Product Factory runtime. It intentionally contains no secret values.

## Runtime modes

| Mode | Purpose | External side effects | Default scheduling | Main gate |
| --- | --- | --- | --- | --- |
| `health` | Report configuration/readiness only | None | Hourly runner | None |
| `github-preflight` | Verify per-project GitHub capabilities with safe read probes | GitHub reads + Control Plane readiness evidence | Hourly when stale/blocked + manual | No synthetic write probes; missing capability stays fail-closed |
| `recovery` | Requeue expired leases or fail exhausted runs | Control Plane writes | Hourly runner | Bounded attempts |
| `product` | Execute one product-stage run | Model call + Control Plane writes | Hourly only when ready | Primary enable + auth + budget |
| `dispatch` | Route one planned task | Control Plane writes | Hourly bounded + manual | Optional project key |
| `direct` | Produce implementation and open PR | Model + GitHub writes | Hourly only after explicit Primary+budget activation; manual supported | Primary enable + auth + ledger budget + risk gate |
| `codex` | Execute one already-routed complex implementation through isolated Codex CLI and open PR | Codex workspace + GitHub writes | Hourly/manual only when explicitly enabled and auth-ready | Codex enable + complete WIF or official `CODEX_ACCESS_TOKEN` + repository-scoped GitHub credential + Control Plane; cross-repo additionally requires `FACTORY_GITHUB_TOKEN` |
| `ci` | Resume one `ci_pending` run | GitHub reads + evidence writes | Hourly | Matching durable PR evidence |
| `preview` | Deploy and verify one `preview_ready` run | Vercel Preview + browser/e2e + evidence writes | Hourly bounded + manual | Preview applicability/readiness + quality evidence |
| `release` | Observe one human PR merge | GitHub reads; issue close/evidence after merge | Hourly | Human merge must already exist |
| `alerts` | Evaluate operational alerts and publish deduplicated GitHub Issues | GitHub issue writes | Hourly bounded + manual | Backend GitHub issue permission |
| `retry` | Create one fresh auditable run from a terminal failed run | Control Plane writes only | Manual | Source run must be `failed`; original run is immutable; explicit retry reason required |

## Atomic route-aware dispatch (candidate; requires migration)

The pending Work Unit can be *peeked* without side effects. Python decides
Direct vs Codex using the existing deterministic router, then calls a single
new transactional RPC with the exact Work Unit ID, a 32-character fingerprint
of the task/unit/Change Set, and the routing decision. The RPC locks and
rechecks the latest ready plan, task/unit state, current wave and fingerprint
before creating the run. It records the route, audit and human execution
gate in the same PostgreSQL transaction. A mismatch aborts the claim; there
is no fallback to the blind claim RPC, whose service_role grant is revoked.

New Direct claims require the protected Primary API readiness boolean and
known-cost budget checks. New Codex claims are independent of Primary only
when the existing manual Codex fallback is **explicitly** enabled by the
corresponding repository variable, automatic Codex is off, and the derived
dispatch readiness signal matches. This is a manual handoff, not an automatic
Codex entitlement or a new production gate. Automatic Codex remains unavailable
for new claims until official WIF/token readiness is proved. No Codex or
OpenAI credential is passed into the dispatcher.

Versioned migration `20261013220500_route_aware_atomic_dispatch.sql` must
be applied in a controlled deployment after merge. Between merging code and
applying the migration, new dispatches fail closed (the new RPCs do not yet
exist); no historical work is reactivated. Verify first with a truly new,
bounded task; zero pending units alone is not a real end-to-end test.
## Preclaim executor readiness for planned Work Units

The dispatcher cannot turn a pending Work Unit into a run unless a real executor
is configured. The product-stage job performs the existing Primary authentication
preflight in the protected openai-api environment, even for dispatch-only work,
without calling the model for dispatch-only readiness.

Dispatch sees only a boolean readiness signal and the explicit primary flag,
not OPENAI_API_KEY. Before any claim, Python checks the enable flag, verified
auth signal and read-only ledger budget/unknown-cost status. Missing readiness
returns blocked_executor_readiness with empty matrices, no new run, and no model call.
The Direct worker independently checks budget and authentication again.

Because route selection currently happens after the atomic claim, this guard
conservatively also prevents NEW Codex routing when Primary is disabled.
Already-routed Codex and manual handoffs continue under independent paths.
Allowing new Codex-only claims without Primary requires a separately designed
route-aware transactional preclaim selector; bypassing this guard is unsafe.
## Same-run dispatch after product planning

The initial scheduler probe's `product_work` signal only indicates a possible
product-stage run; it does **not** prove any Work Units exist. The dispatcher
must not start just because the product-stage job was successful (a job may
succeed after reporting disabled primary credentials). The product-stage job
writes a structured `claimed/completed` result; only a completed claimed
run triggers one additional read-only Control Plane schedule probe. Dispatch
is eligible during a scheduled/owner-wake run if either the initial probe or
the fresh post-product probe reports `dispatch_work=true`. This preserves
same-run planning -> Change Set -> dispatcher responsiveness without an
unproductive dispatch or unnecessary Model/Preview operation. The manual
`workflow_dispatch` intent remains independent. The post-product probe
records existing durable schedule-probe audit events only; it does not
invent or resurrect Work Units.

## Primary-model opt-in for unattended product and Direct execution

The production GitHub Actions `product-stage` and `direct` jobs read the protected
`FACTORY_PRIMARY_MODEL_ENABLED` GitHub variable as a strict, case-sensitive
boolean. When the variable is absent, malformed, or anything other than
`true`, the jobs receive `false`. The mere existence of `OPENAI_API_KEY`
or WIF configuration does **not** authorize paid requests.

Before an administrator explicitly enables that variable, verify the existing
approved API billing/quota and model access, plus Control Plane ledger health
(known spend, no unknown-cost events) and the operator-approved US$ 10.00 internal Factory total budget /
US$ 0.50 reservation (effective only after human merge). The Factory ceiling is not prepaid OpenAI API Platform balance; current provider credit/quota has not been independently verified. Provider billing/429 failures remain fail-closed; no automatic purchase, recharge or retries of paid probes. The Python runtime rechecks both the enable flag and
the ledger *before claiming* a product-stage or Direct run, and the metered
provider still enforces the real per-run reservation. Do not perform paid
smoke calls just to poll readiness, and never purchase credit automatically.

This explicit opt-in does not enable Codex, change GitHub App permissions,
authorize production merges, bypass preview verification, or requeue historical
`plan-*` tasks. A newly created real task must still demonstrate
planning -> new Change Set -> claimable Work Units -> PR -> CI/evals ->
verified Preview when applicable -> awaiting_release. A deterministic
fixture test exercises only the early planning/materialization contract; it
is **not** a release or production E2E signal.

## Merge autonomy

The ChatGPT/operator layer may merge a PR directly after its applicable CI/quality gates are green **only when that merge cannot publish production**. It must use the verified head SHA and fail closed if the PR moved, became non-mergeable, or a human gate condition appeared.

This does not grant merge capability to the Factory runtime, does not enable GitHub auto-merge, and does not change the production boundary. Any PR whose merge publishes production remains a human action.

Production operators may execute that human action from the authenticated Factory Console when the dedicated Console release path is activated. The Console path is intentionally separate from the Python runtime and GitHub adapter. It requires an admin session, `VERCEL_ENV=production`, `FACTORY_RELEASE_GITHUB_TOKEN`, and an explicit source-controlled repository allowlist in `config/factory.release-policy.v1.json`. The token stays server-side and is never exposed to browser code, workers, agents or generated repositories.

## Per-project GitHub capability preflight

Every repository-backed project has a durable GitHub access record. The scheduler may run `github-preflight` before dispatch, using the repository-aware runtime credential.

The preflight:
- performs only safe GET requests;
- verifies repository metadata, contents, Issues, Pull Requests, Actions and Commit Statuses;
- treats Checks as optional when Actions + Commit Statuses provide equivalent CI evidence;
- never creates a fake branch, commit, issue or PR merely to test write access;
- preserves cross-repository write capabilities as unverified until they are backed by an explicitly approved credential;
- blocks Direct/Codex cross-repository writes unless `contents_write`, `issues_write` and `pull_requests_write` are durably verified;
- stores only non-secret readiness metadata in the Control Plane.

The Console shows this contract on each project. An admin can mark the record stale with **Verificar novamente**; the autonomous runner then re-runs the safe preflight. **Corrigir acesso no GitHub** remains an external consent step in Phase 1. The target architecture is a Factory-owned GitHub App with short-lived installation tokens; PAT expansion must never happen silently.

## Factory-owned GitHub App onboarding

The Console contains an inert-by-default GitHub App onboarding path. Registration and installation remain explicit human GitHub actions.

Registration uses GitHub's App Manifest flow from an authenticated Factory admin session. The temporary manifest code is exchanged server-side. The returned PEM, client secret and webhook secret are written directly to Supabase Vault; only non-secret App metadata is stored in the public Factory schema. These values are never rendered to the browser.

For a project, **Verificar GitHub App neste projeto**:
- authenticates as the registered App with a short-lived App JWT;
- asks GitHub for the installation associated with the exact `owner/repo`;
- mints a one-hour installation token constrained to that repository and to the source-controlled delivery permission set;
- verifies repository/contents/issues/pulls/actions/status/check evidence;
- infers write readiness from the granted installation permissions without performing synthetic write mutations;
- persists only `installation_id`, `repository_id`, capability evidence and `auth_mode=github_app`; the installation token is never persisted.

The source-controlled App permission set is limited to Actions read, Checks read, Contents write, Issues write, Pull Requests write and Commit Statuses read. Installing the App or changing repository access is a human GitHub consent action. Until an installation verifies successfully, the existing fine-grained PAT path remains an explicit fallback and cross-repository write stages stay fail-closed.

The Python runtime supports Phase 3 repository-scoped GitHub App credentials without broadening access. For cross-repository work, it first checks the durable project access record. Only `auth_mode=github_app` with `status=ready`, a verified `installation_id` and the exact `repository_id` may mint a short-lived installation token. The trusted Control Plane Edge Function reads the private PEM from Vault and signs the App JWT inside Supabase; neither PEM nor App JWT leaves that broker. GitHub Actions receives only the short-lived installation token restricted to that one repository ID and the reviewed permission set, and the token is never persisted or logged. Same-repository Actions work continues to use the native `GITHUB_TOKEN`. Projects that have not migrated to the App may still use the explicit `FACTORY_GITHUB_TOKEN` fallback; once a project is marked `github_app`, a blocked/incomplete App installation fails closed and never silently falls back to the PAT.

## Preview policy during existing-project onboarding

Imported projects must have an explicit Preview policy before Preview execution. The GitHub capability preflight may persist the safe positive case automatically when read-only GitHub evidence proves an existing Vercel integration on the repository default branch.

Automatic onboarding is deliberately narrow:

- a Vercel commit status with a `vercel.com` target or a check-run owned by the Vercel GitHub App is accepted as integration evidence;
- the persisted policy is only `{"provider":"vercel","mode":"github","required":true}`;
- an existing explicit `manifest.preview` policy is never overwritten;
- absence of Vercel evidence never becomes `required=false`;
- no Vercel team/project identifiers are invented;
- the evidence stores only normalized signal metadata, not raw GitHub payloads;
- the persistence RPC is service-role only and audited as `project.preview_policy.verified`.

If no explicit policy or verified integration exists, Preview remains fail-closed and the Console shows the policy as pending. Re-run the GitHub project preflight after correcting repository access or integration.

## Cross-repo Vercel Preview evidence

For `preview.mode=github`, generic CI evidence can remain valid with Actions + Commit Statuses when the fine-grained token cannot read Checks. Preview URL discovery has a stricter requirement: the Factory needs either a successful Vercel check-run that exposes a `.vercel.app` URL or a successful Vercel commit status plus a Vercel bot comment that exposes a **Ready** preview URL.

`checks_read` is therefore recorded separately as an optional GitHub capability. Missing Checks read does not block generic CI, but it can block Preview discovery when the Vercel bot comment is stale or does not contain a Ready URL. In that case the worker fails closed with an actionable error instead of reporting a generic timeout. The default GitHub path still does not require a Vercel API token.

## Cross-repo CI evidence with fine-grained tokens

For repositories outside the Factory repository, the runtime must not assume that the GitHub Checks API is available to a fine-grained personal access token. The preferred evidence order is:

1. use check-runs when the credential can read them;
2. on HTTP 403 from check-runs, fall back to GitHub Actions workflow runs plus Commit Statuses for the exact candidate SHA;
3. require at least one workflow run for the candidate SHA before treating CI as successful;
4. treat workflow failure or failing/error commit status as CI failure;
5. treat running workflows, non-terminal statuses, missing workflow evidence, or missing fallback capability as pending/blocked rather than success.

The fine-grained fallback requires repository permissions that expose Actions read and Commit statuses read. Do not widen a token to classic `repo` merely to recover the Checks API. Project onboarding/readiness should verify the capabilities actually available to the selected credential.

## Console release credential preflight

The production Console uses `FACTORY_RELEASE_GITHUB_TOKEN` only for the explicit human merge path. Before rendering **Fazer merge em produção**, the Console performs a safe GET of the exact pull request using that dedicated credential.

- HTTP 404 is treated as the credential not seeing the repository or PR.
- HTTP 403 is treated as insufficient read permission.
- HTTP 401 is treated as a rejected/invalid credential.
- No mutation is performed by this preflight.
- The actual merge still happens only after the human confirmation click.
- For a fine-grained PAT, GitHub's merge endpoint requires repository `Contents: write`; reading the PR also requires the token to include the target repository and appropriate pull-request read access.
- The release credential remains separate from runtime delivery credentials and is never exposed to generated code, agents, or the browser.

## Required release sequence

1. Implementation opens a PR; production is not touched.
2. CI follow-up verifies the PR head matches the durable candidate commit.
3. Green CI persists explicit `quality_gate` evidence.
4. Preview applicability is evaluated from explicit project policy and the PR changed files. Missing policy fails closed to Preview required. `required=false` or a non-matching `required_paths` policy records durable `preview_not_required` evidence instead of fabricating a deployment.
5. When Preview is required, it requires the same candidate commit, successful quality evidence, Preview deployment, and successful browser/e2e evidence for the exact Preview URL.
6. The run moves to `awaiting_release`.
7. A human reviews and merges the PR. The action may be performed in GitHub or by an admin clicking `Fazer merge em produção` in the production Console. The Console revalidates the exact candidate SHA and PR state before calling GitHub.
8. The release observer sees the already-merged PR, records/reconciles the merge SHA and audit evidence, marks the run `merged`, and closes the linked issue.

## Console human release action

The optional Console release action is an operator control, not a runtime capability.

Activation requirements:
- production Console only (`VERCEL_ENV=production`);
- authenticated active Console operator with role `admin`;
- dedicated `FACTORY_RELEASE_GITHUB_TOKEN` stored only in the production server environment;
- explicit `operator_allowed_repositories` allowlist in `config/factory.release-policy.v1.json`;
- source-controlled merge method from `config/factory.release-policy.v1.json`.

Before the irreversible GitHub merge request, the Console must confirm:
- the Control Plane release report is exactly `ready_for_human_release`;
- the run is `awaiting_release`;
- the project repository is valid and allowlisted;
- the PR number comes from the durable release report;
- the PR is open, non-draft, targets `main`, and is not from a fork;
- GitHub reports the PR mergeable;
- PR head SHA exactly equals the durable candidate commit and the SHA submitted by the rendered form.

The Console records a durable pre-merge audit event before invoking GitHub. Success/failure evidence is also recorded when possible. A successful Console merge can mark the release report released immediately; the ordinary release observer remains responsible for idempotently reconciling the run/task/issue lifecycle.

Missing token, non-production environment, non-admin operator, repository outside the source-controlled allowlist, stale SHA, draft/closed/non-mergeable PR, or any Control Plane mismatch fails closed.

## Console human migration action

Production database migrations may be applied from the authenticated Factory Console only as an explicit human action on a pending durable gate whose metadata declares `requested_action=apply_control_plane_migration`.

Activation requirements:
- production Console only;
- active Console admin;
- dedicated `FACTORY_SUPABASE_MANAGEMENT_TOKEN` stored only in the Vercel production server environment;
- existing `FACTORY_RELEASE_GITHUB_TOKEN` for read/revalidation of the exact PR and migration file;
- project/repository/ref allowlist in `config/factory.supabase-migration-policy.v1.json`.

Before applying, the Console revalidates pending gate/run/task state, exact candidate SHA, the source PR identity, required green checks, the strict `supabase/migrations/<timestamp>_<name>.sql` path, migration name/file consistency, bounded file size, and the source-controlled Supabase project ref. An open PR must be non-draft. If the source PR was already merged before the migration gate was clicked, recovery is allowed only when GitHub proves a real merge, the PR still targets `main` in the same repository, the head is not a fork, and the durable candidate SHA is still exactly the PR head SHA. A closed unmerged PR remains blocked. SQL is fetched from GitHub at the exact candidate SHA; the browser cannot submit arbitrary SQL.

The Console uses the Supabase Management API migrations endpoint. It lists migration history first for idempotency, applies only when absent, verifies the migration appears afterward, records requested/succeeded/failed audit events, and resolves the human gate only after success. If the account does not expose the official migrations endpoint, the action fails closed; do not fall back to a generic SQL endpoint.

The Management token is never exposed to browser code, Python runtime workers, agents or generated repositories. There is no scheduled/automatic migration apply path.

## Primary model activation

`product` and `direct` are fail-closed inside the Python runtime itself. They require all of:

- `FACTORY_PRIMARY_MODEL_ENABLED=true`;
- a supported primary authentication path: API key or API workload identity;
- configured model budget;
- configured per-run reservation;
- known spend not already exhausting the configured budget.

Do not enable the primary model merely because an API key or API WIF mapping exists. Billing/quota readiness and a bounded smoke test are separate prerequisites. Scheduled Direct additionally requires non-empty budget and reservation variables; the runtime reads current known spend from the Control Plane ledger and blocks if paid usage has unknown cost.

## Factory Console Preview cost policy

Automatic exact Preview/browser evidence for the Factory repository is applicable only when a pushed `preview/**` or `evidence/preview/**` candidate changes `apps/console/**`. Runtime, documentation, tests, broker, or other non-Console changes must not consume a Vercel Preview or browser verification merely because the branch name uses the Preview namespace.

The Vercel project uses the same rule: Preview branches are ignored when the commit does not change the Console tree. Production `main` keeps its broader ignore rule so source-controlled release-policy changes can still publish the Console when required.

Explicit `workflow_dispatch` of exact Preview evidence remains available for a reviewed exceptional case and is not widened by the automatic path filter.

The trusted browser verifier itself is manual-only and requires the exact Vercel URL as an explicit runtime input. Do not persist a reusable Preview URL/candidate pair in the repository: Vercel Preview deployments are ephemeral and a historical URL can later return 410. Exact candidate discovery belongs to the exact-Preview/cross-repo resolver, which reads current GitHub/Vercel checks and then dispatches the trusted verifier with the resolved URL.

## GitHub-hosted browser runtime

Trusted Preview verification on GitHub-hosted Ubuntu 24 runners uses the Chrome executable already provided by the runner image at `/usr/bin/google-chrome`. The workflow still pins the Playwright npm package version, but sets `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1` and does not run `playwright install --with-deps`.

This is a performance/cost hardening only:
- Playwright remains the browser automation library;
- browser verification remains mandatory when Preview is applicable;
- the workflow verifies that the expected Chrome executable exists and fails closed if it does not;
- no browser binary, Vercel bypass secret, reusable credential or generated-code token is persisted;
- the autonomous Preview worker installs the Playwright package only after `preview-probe` reports real browser work.

## Verified Preview activation

The project supplies non-secret deployment metadata in `factory_projects.manifest.preview`. `mode: github` discovers the exact Vercel Preview from GitHub check-runs using `GITHUB_TOKEN`; `mode: api` creates/polls the Preview through the Vercel API and requires Vercel team/project metadata.

For the standard manual GitHub Actions path, the job itself provides the activation flags, uses the native `GITHUB_TOKEN`, installs pinned Playwright/Chromium, and invokes `scripts/verify_preview.mjs`. No external browser service or Vercel token is required when the project uses `mode: github`.

When Vercel Authentication protects Preview deployments, configure **Project Settings -> Deployment Protection -> Trusted Sources** with GitHub Actions scoped to the Factory repository, trusted branch (`main`) and `Preview` environment. Keep the default GitHub OIDC audience unless the workflow explicitly calls `getIDToken()` with a custom audience. The browser job requires `id-token: write`, mints a short-lived token with `core.getIDToken()`, masks it, and sends it only as the `x-vercel-trusted-oidc-idp-token` request header. A successful check must end on the Factory Preview, not on `vercel.com/login`.

For alternative runtimes or `mode: api`, configuration remains explicit: `FACTORY_VERCEL_PREVIEW_ENABLED=true`, provider credentials (`GITHUB_TOKEN` or `VERCEL_TOKEN`), `FACTORY_BROWSER_EVIDENCE_ENABLED=true`, a reviewed `FACTORY_BROWSER_EVIDENCE_COMMAND_JSON`, and an optional bounded timeout.

The Vercel adapters refuse non-Preview environments. The browser adapter receives the exact deployed URL through `FACTORY_PREVIEW_URL` and must return structured JSON evidence. The built-in Playwright verifier checks page load, HTTP status, visible non-empty body, and browser console/page errors.

## Multi-agent team planning

The engineering plan is semantic input, not the scheduler itself. Planning tasks must provide a stable `task_key`, `required_capabilities`, repository `scope_keys`, dependencies by task key, and an optional preferred specialist role only when materially required.

After planning, the deterministic Execution Team Planner reads the live Agent Registry and produces a versioned team plan. It selects the minimum capability-covering/least-privileged specialists, calculates planned workers and dependency/scope-aware waves, records exclusions and blockers, and persists the decision in the Control Plane. It makes no extra paid model call.

Agent `max_concurrency` is a ceiling, never a target. Work may share a wave only when dependencies are satisfied, agent capacity is available and write scopes do not overlap. Parent/child scopes conflict.

A task must have one safe owner. Do not solve a cross-specialist task by granting a read-only reviewer write permission. Instead split implementation, security review, QA/eval or operations verification into independent work units/lanes. Until dedicated read-only specialist lanes exist, policy-required reviewer participation is recorded as advisory and fails closed rather than entering the generic Direct/Codex write worker.

The target integration model is one Change Set per objective: parallel work units use isolated branches/workspaces and converge in dependency order into one controlled integration candidate. Security/QA then evaluate the candidate that will actually ship. Production still stops at the human merge gate.

See `docs/MULTI_AGENT_ARCHITECTURE.md` for selection rules, context packets, adaptive concurrency, metrics and the implementation roadmap.

## Project Brain and Impact Engine

After Planning, the runtime builds a deterministic Project Brain snapshot from the engineering plan and any durable reconciliation snapshot already present in context. No additional model call is made.

The Brain stores versioned nodes/edges with provenance for project, tasks, repository scopes, capabilities, components and observed sources/evidence. Direct public access remains denied by RLS; server-side service access is required.

Before a Change Set builder generates code, the Impact Engine resolves the work-unit task key, loads the current Brain snapshot and traverses relevant dependency/scope/capability relations. The resulting impact packet contains confidence, seed nodes, impacted nodes and explicit unknowns. It is persisted and then passed as factual context to Direct/Codex. Missing knowledge is recorded as unknown rather than invented.

## Change Sets

A ready Execution Team Plan materializes one Change Set. Only builder tasks become work units; Security, QA and Operations remain independent review lanes.

The first builder observes the repository `main` SHA and binds it as the immutable Change Set source. Every work unit in the current wave receives the current integrated candidate as its exact base. Work-unit branches do not create release pull requests.

When all work units in a wave are complete, the Change Set integrator:

1. verifies every work unit was based on the current candidate;
2. rejects duplicate changed-file ownership across the wave;
3. reads exact file contents from each output commit;
4. commits the combined files once to the integration branch;
5. advances to the next wave, or creates one final PR after the last wave.

The final PR head SHA must equal the durable Change Set candidate. The existing CI, specialist review, Preview and human release pipeline then takes over. Integrator retries are bounded; exhausted builder/integration retries block the Change Set.

## Specialist review lanes

After green CI, `factory_enqueue_specialist_lanes` reads the latest ready Execution Team Plan and creates only required Security, QA and Operations jobs for the exact candidate SHA.

Lifecycle:

1. CI persists quality-gate evidence.
2. Required specialist jobs are queued and the run becomes `specialist_review_pending`.
3. Each read-only worker claims at most one durable job with a bounded lease.
4. Candidate SHA is revalidated before evaluation.
5. Findings and evidence are persisted.
6. Any failed or blocked required lane sets `specialist_review_failed`.
7. When all required lanes pass, the run becomes `preview_ready`.

Expired leases are requeued only below the retry ceiling; exhausted retries become `specialist_retry_exhausted` blockers. This version is deterministic-first and does not call a paid model merely to perform review.

## Adaptive concurrency

The Agent Registry `max_concurrency` is a hard ceiling, not a desired worker count. Before exposing a Direct/Codex matrix to GitHub Actions, the adaptive controller computes an effective concurrency per agent.

V1 inputs are runnable assigned work, latest provider quota pressure, unknown paid cost, recent repair rate, first-pass CI yield and CI queue age. Unknown paid cost or critical/blocked quota yields zero workers. Attention/unknown quota and poor quality/queue signals reduce concurrency conservatively.

Each decision is stored in `factory_agent_concurrency_decisions` with the pressure snapshot and human-readable reasons. The controller does not mutate Agent Registry ceilings and makes no model call.

## Requirement traceability and Definition of Done

After planning is persisted, the runtime derives stable requirement keys from each task's acceptance criteria, links them to materialized tasks, and records a versioned Definition of Done.

Evidence is factual:
- `github_ci` comes from exact-candidate CI;
- `security`, `qa` and `operations` come from independent specialist lanes;
- `preview` and `browser_evidence` come from verified Preview;
- `human_release` is recorded only when the release observer sees a human merge.

Readiness contains explicit satisfied/missing checks; there is no release score. Checks without an implemented evidence provider remain missing rather than being guessed as passed.

## Policy-as-Code and Release Intelligence

The release policy is source-controlled in `config/factory.release-policy.v1.json`. It explicitly forbids automatic merge and requires human production release.

After Preview evidence (or explicit Preview non-applicability), the runtime builds a factual release assessment from current DoD readiness, requirements/evidence, specialist evaluations, changed files, task risk, paid-cost health and rollback evidence. Missing non-human DoD checks, unknown paid cost, or an unverified migration rollback blocks transition to `awaiting_release` and persists `release_policy_blocked`.

A successful automatic decision is only `ready_for_human_release`. The release observer marks the report `released` only after GitHub shows a human merge.

## Codex

Codex is a selective executor, not the orchestrator. Scheduled Direct remains disabled until the independent primary-model readiness gate is proven. Codex workspace WIF requires the real managed-workspace federation rule and audience; never invent them.

The Codex worker is independently gated by `FACTORY_CODEX_ENABLED=true`, one complete official Codex auth path (WIF or `CODEX_ACCESS_TOKEN`), the repository-scoped native `GITHUB_TOKEN`, and Control Plane credentials. WIF has precedence; any partial WIF configuration blocks token fallback. The GitHub Actions token-minting layer also requires `OPENAI_WIF_AUDIENCE` to request the external OIDC assertion. Same-repository work may use the native Actions token; cross-repository work still fails closed unless `FACTORY_GITHUB_TOKEN` is configured. The scheduled/manual Actions job checks readiness before checkout, OIDC minting, Node/Codex installation, or queue claim.

A Codex run is claimed only when `execution_route=codex`. Claiming uses a lease and bounded recovery. Repository code is cloned to a temporary checkout with the GitHub credential held by the parent process; the remote is removed before Codex starts, and GitHub/API credentials are not passed to the Codex subprocess. Codex runs with `workspace-write` and non-interactive approvals, never `danger-full-access`. Output is limited by file count and total bytes, rejects deletions, symlinks, non-UTF-8 files, path traversal, and secret-bearing paths, then enters the same Issue -> branch -> commit -> PR -> CI -> Preview -> `awaiting_release` loop as Direct.

The durable `factory_codex_usage` policy row is created at dispatch with zero invocations. The worker increments it only immediately before a real Codex CLI invocation. Do not fabricate token/cost data when the CLI does not report it. The Agent SQL 63-question benchmark remains explicitly excluded from implicit Codex work.

## Manual Codex fallback

Codex remains a selective executor. When `FACTORY_CODEX_ENABLED` is not true, the scheduled `codex-manual` job may handle Codex-routed work without any OpenAI credential.

The flow is:

1. claim one `execution_route=codex` run as `preparing_codex_manual`;
2. create or reuse a GitHub Issue with the exact marker `Factory run: <run_id>`;
3. persist the Issue binding and move the run to `awaiting_codex_manual`;
4. an operator opens Codex using the managed ChatGPT Business account and asks it to implement that Issue;
5. the Codex-created PR must target `main` and include the exact run marker in its body;
6. the follow-up worker discovers that PR, persists its head SHA/branch as candidate evidence and moves the run to `ci_pending`;
7. normal CI, Preview and human production release semantics resume.

The manual handoff never stores ChatGPT cookies, browser sessions, human tokens, `OPENAI_API_KEY` or `CODEX_ACCESS_TOKEN`. It does not increment the automated Codex invocation ledger because the invocation occurred outside the Factory. Lease recovery covers interrupted `preparing_codex_manual` claims.

Setting `FACTORY_CODEX_MANUAL_FALLBACK_ENABLED=false` disables new manual handoffs. Existing `awaiting_codex_manual` runs may still be followed up. Once `FACTORY_CODEX_ENABLED=true` is safely activated, new queued Codex work is left to the automatic worker and the manual prepare step stops claiming work.

## Failed-run retry

Use `runtime --mode retry --source-run-id <uuid> --retry-reason "<reason>"` only after the root cause of a terminal failed run is understood and fixed.

The retry path is model-free. The Control Plane RPC locks and validates the source run, refuses non-failed sources and duplicate retry-of the same source, creates a fresh queued run on the same task/source commit, strips transient worker/error metadata, persists `retry_of` / `retry_reason`, and records `run.retry_queued` audit evidence. The original failed run is never rewritten.

Creating a retry does not bypass routing, model budget, unknown-cost checks, CI, specialist review, Preview policy or the human production-release gate. Do not use administrative SQL to recycle the original run now that the native retry path exists.

Operational `failed_runs` alerts count only actionable failures: the run is `failed` and the task's current status is also `failed`. Historical failed runs remain queryable for audit but no longer keep an incident open after the task has recovered, integrated, completed or been explicitly blocked.

## Operational alerts

The scheduled alerts job explicitly enables the GitHub Issues sink for that job only. Alert issues are deduplicated by deterministic code. Non-billable GitHub/Supabase usage without cost data must not be treated as unknown paid spend.

The GitHub Issues sink reconciles active and resolved conditions on every alerts cycle. Active codes remain open/deduplicated by their deterministic `<!-- factory-alert:<code> -->` marker. A known code that is no longer active is closed automatically only when an open issue contains that exact marker. Unknown markers, pull requests and ordinary issues are never closed by alert reconciliation.

## Supabase credentials

Server-side code prefers `SUPABASE_SECRET_KEY` (`sb_secret_...`) and keeps `SUPABASE_SERVICE_ROLE_KEY` only as legacy fallback. Modern secret keys are sent as `apikey` only; they are not JWT bearer tokens.

Factory tables intentionally use RLS with no public client policies. Privileged worker/Console operations use backend credentials only.

## Incident handling

- Expired worker lease: recovery may requeue within the bounded attempt limit.
- Exhausted attempts: terminal failure/dead-letter visibility; do not infinite-retry.
- CI failure: return to bounded correction/repair, never merge.
- Browser/e2e failure: persist failure evidence and stop before release.
- Candidate SHA mismatch at CI/Preview/Release: fail closed; do not reinterpret the run.
- Unknown paid cost or exhausted budget: block paid execution.
- Missing external credentials: report blocked readiness; do not fabricate values.

## Production safety invariants

- Production release is always human-gated.
- The release-followup worker has no code-write or PR-merge permission.
- Preview cannot target production.
- Direct is manual-only while primary authentication remains externally blocked.
- The 63-question Agent SQL benchmark is not an implicit Factory task.

## Health checks

Factory Console production health:

`GET https://ai-product-factory-console.vercel.app/api/health`

The response is intentionally minimal and contains only service status and a truncated deployed commit.

## Vercel deployment budget policy

The Console must not create a deployment for every implementation commit.

Active policy:
- `main` remains the production branch;
- implementation branches such as `console/**`, `test/**`, `ci/**` and `security/**` do not deploy automatically;
- after `Console validation` completes successfully for a PR that actually changes `apps/console/**`, the trusted default-branch promotion workflow automatically revalidates the exact PR head plus `test`, `factory-acceptance` and `validate` before moving `preview/pr-<n>` to that SHA; manual `workflow_dispatch` remains an explicit fallback;
- only `preview/**` is allowed to create the final Preview candidate;
- when `preview/pr-<n>` does not exist yet, the promoter seeds it at the candidate parent and immediately advances the same ref to the exact candidate; this produces a real ref update for the Vercel Git integration while the branch-creation event itself remains non-authoritative;
- if `preview/pr-<n>` already points to the exact candidate SHA, the workflow reuses it before any budget check and does not request another deployment;
- Preview promotion does not require a Vercel token: when provider usage credentials are absent, GitHub Actions records actual preview-ref promotions in the rolling 24-hour window as advisory telemetry; this local count never masquerades as provider quota and cannot block an exact final candidate by itself; no-op/stale promoter runs do not count, and a run is observed whenever its ref-update step succeeded even if a later step failed;
- the standard Preview promoter intentionally receives no persistent Vercel token or team id; its local GitHub promotion count is advisory only and never masquerades as provider quota;
- provider API usage collection is a separate optional Control Plane job. When read-only `VERCEL_TOKEN` and `FACTORY_VERCEL_TEAM_ID` are explicitly configured for that collector, it records rolling-24h deployment usage and the 70/85/95% policy inputs without coupling Preview creation to long-lived provider credentials;
- the Vercel Git integration remains authoritative for whether a deployment can actually be created; a real provider refusal still fails the exact-candidate Preview path;
- the workflow never calls Vercel CLI or a Vercel deployment-creation API; deployment creation remains the Git integration's responsibility;
- promotion evidence is retained in the GitHub Actions run summary; normal Control Plane reconciliation remains responsible for project lifecycle evidence;
- ref updates performed by the native `GITHUB_TOKEN` do not recursively start push workflows, so the promoter explicitly dispatches `Exact Preview browser evidence` for the exact candidate and waits for the candidate-scoped `Factory Preview browser evidence` commit status; `evidence/preview/**` is a non-deploying recovery trigger, while only `preview/**` can request Vercel deployment;
- exact browser evidence waits for the Vercel commit status to reach success before using a Vercel check URL; early Preview Comments checks are not sufficient readiness evidence;
- `ignoreCommand` remains a path-based second guard;
- Vercel `api-deployments-free-per-day` remains an external quota: do not retry deployments or buy capacity automatically.

## Resource quota observability

The Control Plane records provider/resource/metric, used value, limit, percentage inputs, measurement quality, source, window/reset and status. The optional Vercel collector runs every six hours only when its read-only provider credentials are already configured; missing credentials skip that collector cleanly. Preview safety does not depend on those credentials: exact-candidate binding, stale-candidate cancellation, ref reuse and path gating remain active, while the GitHub-local promotion count is advisory rather than an invented provider quota. GitHub Actions usage remains unknown until a reliable billing/usage source is connected.

## Preview applicability policy

Preview is fail-closed by default. A project can make non-applicability explicit in `factory_projects.manifest.preview`:

- `required: false` with a reason for projects that have no deployable Preview surface;
- `required_paths: ["apps/web/**", ...]` for monorepos where only specific file changes require a Preview.

The policy is evaluated against the exact PR changed-file list. Skipping a Preview still produces durable release-readiness evidence and never skips the human production merge.

## GitHub credentials across repositories

GitHub Actions `GITHUB_TOKEN` is treated as repository-scoped. Inside Actions it may be used only when the target repository equals `GITHUB_REPOSITORY`.

Cross-repository issue/branch/PR/CI/Preview operations require `FACTORY_GITHUB_TOKEN`. The runtime never falls back to the current repository token for a different repository. Configure that secret only in the Factory execution environment and never expose it to generated code or browser clients.

Minimum target-repository permissions depend on the operation: contents read/write, issues read/write, pull requests read/write, and checks read for full Direct delivery. Follow-up readers can use narrower permissions when separate credentials are used.

GitHub App cross-repo onboarding: after registration, `/gates` derives installation actions for active cross-repository projects whose access is not yet `github_app/ready`. The Factory binds the install attempt to the intended project in an HttpOnly, short-lived cookie, sends the operator to GitHub for the real consent action, and automatically performs server-side verification after GitHub returns to the configured setup URL. The `installation_id` query parameter on the setup URL is never trusted as authorization; verification independently asks GitHub for the installation associated with the exact project repository. Installation should be limited to the intended repository and is not trusted until that verification succeeds with a short-lived installation token.


## 2026-10-15 — On-demand intake wake (fail closed)

After the atomic new-project RPC commits, the Console attempts an immediate GitHub Actions wake without granting the browser any GitHub credential. The preferred explicit `FACTORY_GITHUB_WORKFLOW_DISPATCH_TOKEN` uses the workflow dispatch endpoint. If absent or rejected, the Console may use its **existing, registered GitHub App** (only if that App is already installed on `leandrosilveiradepaula/ai-product-factory`), mint a short-lived installation token scoped to this one repository with **Contents: write**, and invoke the `factory-intake-wake` repository dispatch event. This does not extend the App permission manifest. The runner admits that event only from the authenticated Factory App bot and the expected source marker; its normal queue probe and model/cost gates remain enforced. Installation or access approval, if absent, is an external human permission gate; no code should silently widen permissions.

The Console writes a non-sensitive `project.bootstrap.wake_attempted` audit event with `requested`, `failed`, or `unconfigured`, linked to the committed run. A GitHub HTTP 204 means **accepted by GitHub**, not that the worker executed or completed. Failure to wake or audit does not turn a committed intake into a failed form submission, cause duplicate projects, or authorize paid models. The 17/47-minute native cron remains a best-effort fallback. Check the exact GitHub Actions run and `factory_runs` status before claiming a new project started. Primary model remains disabled until actual billing, quota, operator authorization, and ledger readiness are approved.


## 2026-10-18 — CRM pinned-source planning regression (#940 live retest)

Live run `62498f37-e84e-4ada-a8f0-fa9810dfcea0` on Factory `ce0193f0` completed reconciliation/gap/planning but produced 0 implementation tasks and 0 workers. The exact PR #56 head was verified, but planning still received only historical task text and repo governance, not current code. On the pinned CRM commit `f5f7d91f`, `SettingsService.ts` already calls the atomic pipeline RPC although CURRENT_TASK has older non-atomic notes. This is concrete evidence that task text alone must not determine active product gaps.

Next code path: after exact open PR/head verification, read a bounded list of files explicitly named in the latest authorized CURRENT_TASK section, at the same SHA, with missing/truncated/secret evidence fail-closed or explicitly marked. Expose the proof to Product Stage; never equate sampled source with full audit, CI, E2E, deployed migrations or product readiness. No schema writes or migrations. Re-run a new CRM continuation only after human merge of this production-runtime patch.

## 2026-10-19 — Falha de handoff do Change Set após Work Unit concluída

**Incidente real, não teste sintético.** No piloto CRM, o run Direct
`42aa0d07-a143-4955-a24f-517ef37cdc8b` persistiu a Work Unit
`587b6810-d0de-4099-bbae-83e1e79deb5c` como `completed`, com
commit `b135b920043b4eeac87db9aba597af9142a33b53`. O job GitHub Actions
#39296884202 terminou em erro HTTP 409 no checkpoint de uma lease já
encerrada. A condição `needs.direct.result != 'failure'` suprimiu
`change-set-integration`, mesmo com trabalho durável concluído.
A correção do checkpoint no PR #980 evita a falha conhecida; este segundo
bloco protege também contra outras falhas **após** escritas bem-sucedidas.

O Change Set `552fd082-7c8e-4ed7-a712-2a550bb50a52` continua
`building` no Control Plane, com `source_commit=ca4185c3...` e uma Work
Unit concluída. O pin de Preview já avançou para `852a7824...` e depois
para outros SHAs por merges humanos não produtivos. **Não** tratar o código
das PRs humanas #185/#186 como integração durável automática desse Change
Set, nem chamar retrospectivamente a integração com um SHA desatualizado.

**Comportamento da alteração candidata:**

1. Direct/Codex e integração podem falhar como *jobs* depois de registrar
   trabalho em banco. O job seguinte consulta sua própria fila e só opera
   sob claim/checkpoint transacional. O dispatch após Product Stage mantém
   preflight/gate de orçamento estrito; se Product Stage falhar, materializações
   legítimas continuam para um novo wake, sem autorização implícita de pago.
2. A nova migration
   `20261019193000_guard_stale_change_set_integration.sql` exige projeto
   ativo/running, Work Units da onda realmente concluídas e origem compatível
   com o pin atual antes de anunciar ou tomar uma lease de integração.
   O contador de Change Sets com SHA obsoleto é **diagnóstico**, não fila.
3. `schedule-probe` registra `queue_diagnostics.stale_integration_change_sets`;
   `null` significa que a migration ainda não foi aplicada, **não** que há
   zero registros obsoletos. Falhas de tipo no retorno bloqueiam o probe.
4. A migration **não altera** nenhuma linha histórica, não marca o Change Set
   como integrado, não executa merge e não reexecuta modelo. O Change Set
   antigo deve permanecer auditável e só pode ser encerrado/reconciliado
   por um procedimento oficialmente versionado que confirme provas reais.
5. Production gate separado: merge humano da Factory, CI e isolated-Postgres
   evidence primeiro; **aplicação humana** da migration depois. A verificação
   de SQL usa `scripts/verify_stale_change_set_integration_postgres.py` em
   PostgreSQL 16 descartável, job `change-set-guard-postgres`. Ela valida
   privilégios somente `service_role`, claim de onda completa, pausa,
   inatividade, tentativas esgotadas, pin obsoleto, não alteração de histórico,
   elegibilidade de outro projeto e greenfield; não toca Supabase real. Nunca aplicar
   SQL de produção pelo runtime, usar SQL direto para mudar status de runs ou
   aumentar teto de API para forçar integração.

**Verificação após gate:** ler
`public.factory_scheduler_queue_signals()` e exigir
`integration_work=false` quando o único Change Set elegível for
obsoleto, `stale_integration_change_sets>=1` no incidente conhecido,
`factory_change_sets` histórico intacto e nenhum worker pago acionado.
Para uma nova Work Unit válida, exigir CI, PR e Preview por SHA exato,
com merge de produção exclusivamente humano. Não disparar modelos apenas
para sondar a alteração.
## 2026-10-19 — Higiene do backlog e encerramento auditado de artefatos antigos

Incidente observado: o Change Set CRM 552fd082-7c8e-4ed7-a712-2a550bb50a52
ficou em building depois de concluir uma Work Unit e criar commit real,
enquanto o SHA de origem foi superado por merges humanos no Preview.
Quatro Change Sets em review_ready não têm nenhuma Work Unit; há dez
tarefas queued históricas (Factory e CRM) e havia um gate de planejamento
sobre edição de condições já entregue no CRM. Esse último gate foi
encerrado pela RPC oficial factory_supersede_stale_planning_gates,
preservando auditoria e reduzindo gates humanos pendentes a zero.

Não usar DELETE. A FK de Work Units para Change Sets usa ON DELETE
CASCADE: excluir a linha do Change Set apagaria evidências de trabalho.
Muitos artefatos terminais (blocked, superseded, completed) fazem parte
da trilha de rastreabilidade e não devem ser tratados como fila executável.

A migration 20261019201000_retire_obsolete_factory_artifacts.sql registra
a função factory_retire_obsolete_artifacts_v1 (SECURITY INVOKER,
somente service_role). A migration NÃO retira nenhum registro por si só.
A chamada explícita exige project_key, pin exato (ou o sentinela
platform:no-pinned-candidate para a plataforma), listas limitadas e
sem duplicações de IDs, UUID da operação e justificativa. A função
exige projeto running/quiescent, trava transacional do projeto/controle
e falha integralmente diante de qualquer entrada ou estado inesperado.

Elegibilidade:
- Change Set building: origem diferente do pin atual e Work Units
  todas completed, sem release, lease ou run de execução ativo.
- Change Set review_ready: nenhum SHA, nenhuma Work Unit, root concluído
  e prova de Work Unit concluída de um Change Set mais recente.
- Tarefa queued antiga (mínimo sete dias): parent concluído e trabalho
  posterior concluído no mesmo projeto, sem run/gate/filhos ativos e sem
  associação a um Change Set não terminal.
- Tarefa com run completed passa a completed; outra comprovadamente
  obsoleta passa a cancelled; Change Set passa a superseded.

A rotina registra recibo idempotente e eventos auditados por objeto,
preservando dados de modelo/custo, commits, Work Units e snapshots.
Um request_id repetido com IDs ou justificativa diferentes é rejeitado.
O teste em PostgreSQL 16 isolado é
scripts/verify_retire_obsolete_artifacts_postgres.py, job
retire-obsolete-artifacts-postgres. Ele valida permissões restritas,
origens e gates, listas explícitas, ausência de delete, idempotência,
retenção de evidências, falha integral de lote e diferença entre
plataforma e projeto existente.

Aplicação da nova migration e chamadas de limpeza no Control Plane de
produção exigem gates humanos separados de merge e aplicação. Não
atualizar status manualmente por UPDATE, não retomar tarefas antigas
por modelo nem alegar que a Factory completou automaticamente os
Change Sets entregues por intervenções externas. Não marcar PR #56
como mergeável/publicada por um mero encerramento de registros.

## 2026-10-19 — CI íntegra e execução única do workflow por candidato

Contexto: após a limpeza auditada do backlog, a Factory permaneceu sem filas executáveis. O incidente real do piloto CRM demonstrou que um job pode gravar sua Work Unit e falhar depois, e que intervenção manual não prova que a Factory concluiu sua própria esteira. A validação de CI precisa depender de GitHub Actions no SHA exato, não apenas de um check verde de Vercel.

1. Fonte e identidade: exigir workflow GitHub Actions vinculado ao head SHA e à head branch da PR, acionado por push, pull_request ou workflow_dispatch. Run parcialmente executado ou falho bloqueia avanço; run concluído com apenas skipped/neutral não comprova testes. Quando Check Runs estiver acessível, exigir também ao menos um check de github-actions com sucesso e o mesmo SHA. Inventários incompletos, mais de 100 registros, permissões Actions/statuses ausentes ou respostas malformadas bloqueiam o gate. Vercel e Preview não são CI.
2. CI única: a integração cria Issue/PR e persiste ci_pending, mas não dispara workflow. Somente o ci-followup tem autorização para disparar validate.yml no mesmo repositório. Um workflow GitHub Actions já presente no mesmo SHA impede novo dispatch.
3. Deduplicação durável: o registro factory_tool_usage com operation=dispatch_ci e identidade (run, PR, SHA, branch, workflow) impede disparos repetidos a cada wake se GitHub ainda não mostrar o novo workflow. SHA diferente pode receber novo dispatch; identidade conflitante, lista truncada e formatos inválidos falham fechados. Em outros repositórios, nunca usar validate.yml da Factory como substituto.
4. Operação: depois de 30 minutos de um dispatch registrado, se o run permanecer ci_pending sem avançar, o health reader somente lê o ledger e produz stalled_ci. O adapter de alerts emite um issue deduplicado em futuro ciclo de avaliação. Este alerta nunca relança CI, modelo, Codex, Preview ou merge.
5. Evidências: regressões em test_github_rest, test_runtime_cli, test_ci_followup_queue, test_supabase_operational_health e test_operational_alerts cobrem SHA/branch, workflows parciais/falhos, Vercel isolado, validação de permissões, deduplicação, alerta e não execução de modelos.

Esta mudança não contém migrations, alterações de RLS, Console nem auto-merge. Não altera o teto financeiro de US$10 ou reserva US$0,50. Aplica-se Preview N/A para a própria Factory por não tocar em apps/console/**; não inventar deployment. Gate de merge de produção permanece humano. Mesmo após CI verde, readiness global do produto só pode ser comprovada por um novo fluxo real até o gate de release.

## 2026-10-19 — Verificador de jornada E2E sem disparo nem custo

A proxima comprovacao da autonomia NAO e reabrir tasks historicas nem criar fake run. O procedimento versionado em docs/AUTONOMY_JOURNEY_EVIDENCE.md recebe um Start humano com cutoff UTC, recusa eventos de outro projeto/run, confirma commits e PR no repositorio real e diferencia CI, Preview, release e operacao. A nova GitHub Action e workflow_dispatch manual e usa apenas GET no Control Plane/GitHub; nenhum provider, merge, deploy ou DDL e invocado. Cadastro draft isolado e precondicao de teste, nunca autostart. Somente evidencias futuras de execucao real podem fechar a pendencia de autonomia; mocks e testes unitarios validam o avaliador, nao a Factory inteira.


## 2026-10-19 — Auditor de jornada: aderencia aos eventos reais (#984)

Consulta read-only evidenciou tres incompatibilidades corrigidas no auditor:
nomes de Product Stage distintos entre greenfield e existing, eventos
release.awaiting_human_merge/preview_not_required com project_id NULL, e
release.human_merge_observed moderno contendo candidate_commit+merge_sha
sem pr_number. Eventual NULL-project e aceito apenas pelo run_id exato,
SHA/PR; console human merge requer testemunha extra do mesmo run com PR
e repository. Todas as evidencias de delivery pertencem ao unico run da
create_pr, e cada Work Unit deve ser ancestral do commit candidato.
Nenhuma evidencia posterior permite pular etapas ou rotular uma jornada
como completa. Nao executar Start automatico, modelo pago nem SQL de escrita.

## 2026-10-19 — Auditor de jornada via workflow OIDC JA confiavel

Antes da liberacao da PR #984, a revisao de identidade descobriu que o
workflow independente proposto nao pertencia aos workflow_ref permitidos
pelo broker do Control Plane; GETs e GitHub App token retornariam 403.
Sem ampliar nenhuma permissão OIDC/App, o audit agora usa
autonomous-runner.yml (workflow_dispatch, run_journey_audit=true) no main.
O schedule-probe e TODOS os seus descendentes ficam skipped nesse modo;
o unico job executado e journey-readonly, que usa broker e GitHub App ja
autorizados, com GETs exatos e artifact JSON sanitizado. A antiga Action
independente foi eliminada. Testes regressivos garantem encadeamento dos
jobs e ausencias de modelos, workers, deploy, merge e migrations no modo
auditoria. Para acionar apos Start humano: usar projeto, cutoff UTC, run
UUID e stage minimo; sem Start o retorno e not_started (nao E2E aprovado).


## 2026-10-19 — Auditoria da sintaxe do workflow de jornada (#984)

Revisao do PR apos CI revelou oito expressoes ${{ }} indevidamente precedidas por barra invertida e uma expansao Bash de argumentos escapada. Essa sintaxe pode inviabilizar condition, token, arquivo artifact e argumentos na execucao real. O PR remove esses nove escapes e inclui teste estatico de regressao para o workflow OIDC existente. Nenhum deploy, Start automatico ou modelo pago e disparado por essa mudanca.


### Acionamento seguro do auditor por comentario OWNER, sem workflow_dispatch

Quando o conector GitHub nao oferecer `workflow_dispatch`, o operador
conectado pode publicar o comando **exato** em issue do proprio repo Factory:

```text
/factory-journey-audit ai-product-factory 945c0da5-f36f-46da-a454-072037a988a5 2026-10-20T03:00:00Z
```

O comando usa o job `journey-readonly` do workflow confiavel
`.github/workflows/autonomous-runner.yml` no `main`. A expressao de
job exige `OWNER`, `issue_comment created`, issue real e prefixo
exato; parser Python fail-closed valida os 3 argumentos e escopo antes
de solicitar OIDC. O runner nao expoe API de modelo nem token com escrita,
nao aciona `schedule-probe`, e escreve somente JSON redigido no artifact
`fresh-factory-autonomy-journey-<run_id>` (7 dias).

Nao chamar `/factory-wake` para apenas auditar; isso poderia habilitar
workers. A auditagem nao aprova merge, nao reabre trabalhos historicos e
nao substitui o human release gate. Conferir `status=observed_complete`
E `highest_verified=operations` em run real, no mesmo SHA/PR.


## 2026-10-20 — Evidência operacional de admissão (#987)

Além do modo local `python -m ai_product_factory.runtime_cli --mode admission-diagnose --project-key <key> [--run-id UUID]`, o próprio workflow OIDC confiável `.github/workflows/autonomous-runner.yml` fornece a via owner-only `/factory-admission-diagnose <project_key> [run_uuid]` como comentário em issue real. O comando é validado antes do OIDC e o job `admission-readonly` preserva JSON redigido como artefato. Nenhum agendamento, claim, modelo, CI, Preview ou merge é acionado por esta via. Para detalhes, testes e limites, consultar `docs/ADMISSION_DIAGNOSTICS.md`.

Correção importante: `preview_ready` de auditorias manuais históricas (`source=dogfood_manual_audit`) não representa pendência de Preview real; runs roteadas sem claim não são Product Stage. `in_progress` exige comprovante de claim/início da run. Evidência CI de PR valida código, não substitui prova da execução do diagnóstico no Control Plane; após merge, requer job real com artefato e o SHA da main.


## 2026-10-20 — Continuidade de prontidão global após release (#713)

Releases humanos confirmados podem reconciliar o projeto para `operations`, mas isso **não** certifica o produto inteiro. O reconciliador consulta o `factory_release_reports` pelo `project_id + release_run_id` exatos, verifica `released`, SHA candidato e merge SHA observado, e conserva em `manifest.product_readiness_followup` os domínios que ainda exigem evidência atual. O `factory_project_state_snapshots.gaps` registra seis obrigações de auditoria, em vez de `[]`, quando `product_readiness=not_assessed`. O snapshot não cria tarefas, gates, pagamentos ou modelos.

O próximo ciclo **explicitamente autorizado** recebe `current_state_facts.global_product_readiness` do Control Plane, inclusive em projetos legados por consulta somente leitura do último report. A etapa Planning pode distinguir falta de evidência de defeito de implementação. Não produzir Work Units só porque o domínio não foi auditado; somente falhas atuais e escopo autorizado justificam código novo. Um report `passed` no SHA candidato permanece `candidate_only` até prova independente após merge no HEAD atual. Dados não verificados produzem `status=unknown,ready=false` e deixam o fluxo de release observável sem reexecutar chamadas pagas.

O comando `admission-diagnose` também retorna a obrigação de prontidão quando a fila está vazia e o projeto está em `operations`; isso explica `idle_with_unassessed_global_product_readiness` sem inferir um worker. Não atualizar retroativamente os reports históricos e não transformar esse diagnóstico em `product_ready`. Validação: `tests/test_post_release_readiness.py`, testes de release e runtime, CI exata antes de merge; Preview N/A para este bloco sem `apps/console/**`.


## 20/10/2026 — Auditor global independente pós-CI (candidato da #713)

Nova trilha somente leitura: um `workflow_run` disparado por `validate`
SUCCESS de push em `main` observa HEAD exato, CI, inventário completo
da árvore GitHub e `factory_evaluations` vinculada ao projeto. A avaliação
global permanece `not_assessed` se faltar algum recibo necessário; cada
domínio gera pacote de verificação pendente, não run/task/issue automática.

O token GitHub é somente leitura para o próprio repo do Actions; a identidade
do projeto é resolvida pelo Control Plane, não por client hardcode. Se `main`
mover entre CI e coleta, o observador falha fechado; não publica estado
enganosamente verde nem invoca LLM. A evidência deve ser conferida no
artefato da execução real pós-merge. Consultar
`docs/GLOBAL_PRODUCT_READINESS_EVIDENCE.md`.

## 20/10/2026 — Reparação do auditor global por OIDC sem ampliar credenciais

A execução `39460182317` da PR #1002 falhou: GitHub OIDC token
foi emitido, mas o broker `factory-runtime-control-plane` recusou a
identidade do novo workflow. A causa foi reconciliada com a whitelist
`GENERIC_PROXY_WORKFLOW_REFS` e a regra específica de
`workflow_run`. A solução é realocar o job de auditoria para o workflow
**já confiável** `autonomous-runner.yml`, não adicionar o novo workflow
aos privilégios do broker. Proibir execução de Product Stage/Direct,
integração, CI/release, Preview e Codex a partir do evento `validate`.
A trilha de evidência deve manter jobs de CI exatos e razões de falha
sanitizadas, sem ampliar RLS ou credenciais. Consultar
`docs/GLOBAL_PRODUCT_READINESS_EVIDENCE.md`.


## 20/10/2026 — Console: operação não é prontidão global

O Console não deve tratar a chegada ao stage `operations` como produto
`product_ready`. O próximo passo exibido passa a direcionar o operador para
`#product-readiness`, que mostra os seis domínios exigidos
(segurança/isolamento, operação/recuperação, testes/E2E, UX/a11y/mobile,
documentação/rollback e completude). Domínios sem avaliação global passam
visualmente como `Comprovação pendente`; não inferir `passed` de CI, release,
arquivo estático ou ausência de issues. O detalhe da avaliação histórica e
o SHA permanecem explicitamente separados da prontidão atual.

A configuração de projeto novo não deve conter nomes de piloto como Service
Desk, nem conta GitHub fixada. O proprietário da organização/repo é definido
pelo operador e verificado pela GitHub App server-side; o Console apenas sugere
`project_key` como nome do repositório privado e nunca altera permissão sozinho.

A acessibilidade passa a exigir navegação por teclado com `Pular para o
conteúdo principal`, foco visível, tipografia legível e alvos móveis >=44px.
`scripts/capture_authenticated_console.mjs` coleta apenas medidas de layout,
fontes e alvos, valida seis domínios no detalhe de um projeto, e continua
bloqueando overflow e mutações de projeto durante auditoria.

Mudanças em `apps/console/**` exigem CI e Preview Vercel verificado por
SHA exato com browser evidence; Vercel `Ignored Build Step` não é Preview.
Sem credencial secreta no browser, novas chamadas de modelo, migrations ou
auto-merge. Um deployment de Preview bloqueado por quota mantém gate fechado.

## 20/10/2026 — Coleta global após evidência visual (candidato #713)

A PR #1005 foi mergeada humanamente em
`e6c045cc20ce47040bdbe9d268fa2f1459bb221c`; `validate`,
`Console validation` e `Authenticated Console visual evidence` em
main passaram no mesmo SHA. A Vercel publicou deployment production
`dpl_73fQ8bsAfGUaRXpyB8MqhvgJd7qv` READY e a captura autenticada
`39467414056` gerou artefato criptografado #12284659523; a conta
efêmera foi eliminada pelo workflow. O auditor global #39467480783
executou antes do fim da captura, retornando
`product_ready=false` e seis domínios não avaliados.

O candidato muda apenas o workflow OIDC já confiável e coletores Python:
aciona uma **segunda observação** no término do workflow visual (SUCCESS ou
FAILURE), sem acordar scheduler/workers e sem novos modelos. Os fatos são
correlacionados por SHA exato, run de CI, job `capture`, artifact
criptografado e status Vercel; falha real de navegador/provider bloqueia
qualquer promoção de prontidão. Evidência de CI/UX é parcial, jamais
`product_ready` completo. A saída não contém token/chave. Relatório
disponível em `docs/GLOBAL_PRODUCT_READINESS_EVIDENCE.md`.

## 20/10/2026 — Seletores da fila respeitam o controle humano (candidato)

O Control Plane real revelou que `factory_portfolio_candidates(integer)` e `factory_peek_planned_work(text,integer)` ainda podem enumerar Work Units de projeto `draft`, `pausing`, `paused`, `stopping` ou `stopped`. O claim transacional de produção `factory_dispatch_preapproved_planned_task_v2` já aplica `factory_assert_project_running`, portanto o bloqueio existe no último gate, mas a sinalização anterior do scheduler fica enganosa. A migration `20261020181000_fence_scheduler_eligibility_manual_control.sql` reconcilia as **definições SQL obtidas diretamente da produção** e só adiciona filtro `control.state='running' AND generation>0` aos dois seletores. Não cria runs, não muda prioridades, não reabre trabalho histórico e não toca no ciclo Start/Stop.

Os RPCs antigos `factory_dispatch_preapproved_planned_task` e `factory_dispatch_next_planned_task` foram inspecionados no banco: estão **sem EXECUTE para service_role, anon e authenticated**, não fazem parte do adapter atual (que usa `_v2`). Não reabrir permissões nem duplicar a implementação. As RLS intencionais das tabelas Factory permanecem fail-closed. Essa migration **precisa ser aprovada/aplicada em produção pelo operador**, somente depois de CI e verificação. O plano não aplica SQL automaticamente.

## 20/10/2026 — Sinais de acordar scheduler e controle humano

O RPC `factory_scheduler_queue_signals()` é usado como inventário do probe,
não como autorização de claim. A versão atual em produção não correlacionava
`product_work`, `routed_execution_work`, `codex_manual_work` e três
`specialist_*_work` com `factory_project_execution_controls`. A nova migration
`20261020183500_fence_scheduler_queue_signals_manual_control.sql` exige projeto
ativo, `state=running` e `generation>0` nesses sinais. `integration_work`
já tinha filtro. `ci_work` e `release_work` permanecem indicadores passivos,
não grants de execução; suas mutações continuam sujeitas ao claim/gates
independentes. A migration deve manter apenas `service_role` no EXECUTE e
nenhuma ampliação RLS.

Duas migrations aguardam autorização específica para produção: esta e
`20261020181000_fence_scheduler_eligibility_manual_control.sql` (merge #1007).
Executar em ordem de versão e confirmar após aplicação, via leitura de
`pg_get_functiondef` e chamadas só de consulta, sem criar projetos/runs.
Os testes de PR não são prova de aplicação real.

## 20/10/2026 — Gate humano no agendamento de agentes, especialistas e reparos

As funções de produção `factory_claim_agent_slot`, `factory_schedule_run_agent`, `factory_schedule_next_unassigned_run`, `factory_claim_specialist_lane`, `factory_enqueue_specialist_lanes` e `factory_enqueue_repair_from_specialist` foram reconciliadas pela definição `pg_get_functiondef`. A migration `20261020190000_fence_agent_specialist_and_repair_control.sql` introduz `factory_assert_project_running(project_id)` antes de atribuir agentes, criar lanes ou reparos, e filtra filas globalmente pela linha de controle do mesmo projeto. **Não reintroduzir** chamadas para APIs antigas revogadas nem usar heartbeat como autorização.

O guard `factory_assert_project_running` mantém lock `FOR SHARE` para serializar comandos de pausa/stop com claims. O SQL do candidato não muda grants, RLS nem a implementação do controle humano. Aplicar **somente depois de aprovação explícita**, preservando ordem após `20261020181000` e `20261020183500`, e validar por testes e consulta ao banco. As funções de recuperação serão abordadas separadamente, sem requeue automático de trabalho pago em projetos pausados.

## 20/10/2026 — Implantação das migrations de controle humano / recovery isolado

As três migrations `20261020181000`, `20261020183500`, `20261020190000` foram aplicadas após autorização humana no Supabase `fjplmxfcshhbmzgvyqlm`; consulta direta de `supabase_migrations.schema_migrations` confirmou `20261020185723`, `20261020190213`, `20261020190346` com os nomes correspondentes. Os arquivos Git mantêm timestamps de autoria, **diferentes dos version IDs gerados pelo Supabase MCP**; antes de `supabase db push` reconcile por nome/assinatura para NÃO executar DDL repetida apenas por mismatch de versão. Confira a issue #894 para evidência auditável.

A revisão de recovery encontrou cinco entradas mutantes que não conferiam `running` ou `generation`: recuperação de leases de run, Change Sets, specialists, materialização de decisões já aprovadas e retry manual de run falhada. A migration candidata `20261020194500_fence_recovery_manual_project_control.sql` fortalece o guard `factory_assert_project_running` para projeto ativo + geração positiva e introduz checks transacionais com lock `FOR SHARE`, impedindo requeue/criação de work enquanto paused/stopped. Recovery de recurso expirado/agent slot separado continua limitado à liberação de reserva (não é work requeue) e deve ser auditado como cleanup.

A validação dessa migration usa o script `scripts/verify_recovery_manual_project_control_postgres.py` somente com `FACTORY_RECOVERY_CONTROL_TEST_ISOLATED=true` e DSN localhost `factory_recovery_control_test`; o job de GitHub Actions usa PostgreSQL 16 efêmero. Nenhum credencial, cron, modelo pago, storage ou produção é necessário para essa suite. **Não aplicar a migration candidata antes de CI e autorização específica de produção.**

## 20/10/2026 — Checkpoint de Pause/Stop em followups determinísticos

O estado de controle humano é verificado por `SupabaseProjectFollowupGuard`
antes das continuações effectful `run_ci_once`, `run_preview_once`,
`run_specialist_once` e `run_release_once`. O checkpoint usa somente
Supabase server-side e o RPC existente
`factory_assert_project_running(project_id)`, sem credenciais no browser
nem mudanças de ACL. Também verifica por leitura `is_active=true`,
`state=running`, `generation>0`, recusando ausência, estado desconhecido
ou dados malformados. A corrida em que Pause chega entre a leitura e a
asserção do RPC retorna HTTP 409 e é classificada como
`project_control_waiting`.

`project_control_waiting` é apenas observação de candidato, sem dispatch
de CI, deploy, browser, avaliação Specialist ou reconciliação de release.
A continuation limitada o contabiliza como *waiting*, não como work entregue;
Preview usa skip por run para não bloquear outro projeto autorizado.
Retomar um projeto revalida o estado no próximo wake; não cria novo run,
não substitui idempotência de CI, não libera orçamento, não faz merge
automático.

Limite de atomicidade: não é possível manter lock de banco através de uma
chamada externa GitHub/Vercel, e um request externo já aceito não pode
ser desfeito pela pausa. O checkpoint é uma barreira imediata adicional
aos guards transacionais de claims/leases; são necessários rechecks e
recibos exatos antes de gravar sucesso. A migration de recuperação
`20261020194500_fence_recovery_manual_project_control.sql` de #1011
continua pendente de autorização de produção; não confundir esta entrega
Python com a sua aplicação.

## 21/10/2026 — Revisao complementar da PR #1025 (mesmo candidato)

- **Rollout SQL/Python fail-closed**: antes de registrar merge/release no Control Plane, o observer testa o RPC versionado `factory_pending_release_reconciliations_v1` em modo read-only. Se o SQL nao existe, falha antes da primeira escrita; nao deixa run terminal sem outbox de recovery.
- **Handoff do Change Set**: `factory_reconcile_observed_release_v1` conclui o Change Set `ci_pending` no mesmo commit do manifesto, snapshot e auditoria. O caminho legado `finalize_released_run` passa a receber status `completed` idempotente. Crash entre as chamadas nao deixa Change Set orfao.
- **Controle humano na recuperacao**: outbox ignora projetos pausados/inativos; a RPC serializa `generation` e `running` por lock e recusa replay de outra geracao. Falha por Pause/Stop continua retryable, nao marca needs_review. Projetos elegiveis independentes continuam.
- **Prontidao global**: somente os seis dominios reais geram gaps; subset ou lista fraudada nao pode parecer um produto avaliado.
- Cobertura ampliada no PostgreSQL descartavel: compatibilidade do RPC, Change Set atômico, rollback de snapshot tambem desfaz Change Set, Pause e fairness, stale generation, blocked CS. Nenhuma alteracao em producao, custos ou pilotagem.

## 21/10/2026 — Reparo durável de CI nativa (#1036, candidato)

Uma falha de CI de um candidato Change Set não deve mais ser tratada como
um simples `needs_correction`. O runtime coleta somente metadados
sanitizados de checks GitHub Actions do **SHA exato** do PR e chama a RPC
`factory_enqueue_ci_repair`. A RPC verifica `run`, `project`, Change Set,
PR, branch, recibo `create_pr`, SHA e `execution_generation` no mesmo
commit antes de criar uma Work Unit de reparo limitada no Change Set.

Somente falha classificada positivamente como `code` pode materializar a
Work Unit. Runner, infraestrutura, permissão, quota ou classe desconhecida
ficam registrados como bloqueio durável, sem patch especulativo, sem nova
chamada de modelo e sem tentar contornar a CI. Tentativas de código são
limitadas a duas por padrão (máximo três); ao esgotar, a run fica em
`failed_gate` e o Change Set é bloqueado.

O worker existente Direct/Codex continua dono do lease, escopo, orçamento e
fencing de geração. A integração existente produz o novo SHA no mesmo PR;
triggers do Control Plane registram `integrated`, `awaiting_ci` e `passed`
atomicamente com as transições de Change Set/run. Pausa, Stop, SHA divergente
ou ausência da migration recusam a continuação. Não existe auto-merge,
Preview antes de CI verde, migration automática ou chamada paga de smoke.

**Estado verificado em 22/10/2026:** as migrations
`20261021213414_durable_ci_repair_requests.sql` e
`20261021234500_ci_repair_replay_idempotency.sql` foram executadas no
Supabase `fjplmxfcshhbmzgvyqlm` mediante autorizacao humana e estao
registradas em `supabase_migrations.schema_migrations`. A RPC de enqueue
foi inspecionada quanto a `SECURITY INVOKER`, idempotencia de replay e ACL
`service_role` somente; a fila estava vazia. Regressao E2E PostgreSQL 16
em GitHub Actions concluiu verde; isso NAO prova um reparo real em producao.
Nao reaplicar nenhuma migration nem criar incidencia simulada em producao.

**Validação adicional (candidato, ainda não publicado):** o runtime deve
considerar apenas a execucao mais recente de cada workflow GitHub Actions
para o SHA e branch candidatos, preservando independencia por evento de CI.
Ao usar checks nativos, associar jobs exclusivamente aos check suites dos
workflows selecionados e escolher a tentativa de job mais recente. Uma falha
antiga nao pode sobrepor um retry verde; um sucesso antigo nao pode liberar
um retry novo pendente/falho. Check suites de observadores `issue_comment`
e commit statuses Vercel/Preview nao sao falhas de CI nativa. Identidades de
retries incompletas ou ambiguas bloqueiam a avaliacao. Esse comportamento
passa por testes determinísticos sem modelo pago, deploy ou auto-merge.

## 22/10/2026 — Reparo de CI: paths autorizados em todas as waves (candidato)

`factory_enqueue_ci_repair` não pode determinar write scopes a partir de
`factory_change_sets.metadata.integrated_files` somente: a função de integração
`factory_complete_change_set_integration_epoch` guarda ali apenas o diff da
wave final. Consulte `factory_change_set_work_units.changed_files` de todas
as unidades `integrated` do mesmo Change Set para derivar **somente arquivos
efetivamente integrados**. A nova migration
`20261022125100_ci_repair_cumulative_scopes.sql` reimplementa o RPC já
existente, preservando locks, SHA/PR/epoch, idempotência do replay e ACL
`service_role`. Não cria tabelas nem amplia acesso.

O novo caminho bloqueia em vez de especular em caso de zero units, unidade
não integrada, ausência de array ou entradas vazias, path inválido
(relativo com traversal, absoluto, barras invertidas, control chars) ou mais
de **500 caminhos distintos**. Resultado durável: request `blocked`, run
`failed_gate`, Change Set `blocked` e `ci.repair.blocked` auditado.
Não reabrir automaticamente Change Sets bloqueados ou históricos. Antes de
enfileirar uma wave de repair, os paths são ordenados/deduplicados e
persistidos tanto na nova task quanto no registro do reparo. O
`factory_work_unit_context_source` deve expor a mesma lista ao executor.

**Gate de deploy:** SQL desta migration somente após CI PostgreSQL real no
candidato, merge humano e autorização **específica** para migration de
produção. Uma execução no SQL Editor exige reconciliação oficial posterior
do histórico, sem executar o SQL duas vezes. Não usar `db push` no ambiente
com migrations históricas divergentes. Esse teste não usa OpenAI/Codex e
não demonstra um incidente de CI real. As migrations v1/v2 já estão
registradas e nunca devem ser repetidas.
