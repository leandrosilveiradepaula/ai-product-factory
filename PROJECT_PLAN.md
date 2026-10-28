> **Diretriz vigente de finalização (27/10/2026):** [Contrato de finalização](docs/FINALIZATION_EXECUTION_CONTRACT.md). Priorizar verificações independentes dos seis domínios da [#713](https://github.com/leandrosilveiradepaula/ai-product-factory/issues/713) e E2E existente do CRM somente em jornada real autorizada. **F6 greenfield permanece pendente de produto legítimo novo e autorizado**, não do antigo Service Desk standalone, agora módulo CRM e projeto parado. As seções abaixo são registros históricos e não concedem permissão de recuperação, Start, custos, migration nem merge humano de produção. Não repetir Provas 1/2 ou cenários aprovados da 3; evitar PRs sem defeito ligado a critério de aceite. `product_ready=false` até avaliação independente.

## 26/10/2026 — Captura visual autenticada pós-#1109: fixar imagem do runner (candidato)

Evidência de produção: PR #1109 mergeada humanamente em `main=d463a602d7f2ee712f071cfa249035014b30390c`, CI `validate` [#40327176914](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/40327176914) SUCCESS, `Console validation` [#40327176920](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/40327176920) SUCCESS, Vercel produção `dpl_69x3K2Shy9udQpxJU44Rq7iY86PA` READY e aliased à URL oficial no SHA exato. Auditor global [#40327234064](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/40327234064) `product_ready=false`, seis domínios não verificados, captura `pending`.

A captura autenticada auto-iniciada [#40327176953](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/40327176953) terminou **cancelada por timeout**, sem evidência de telas: a imagem `ubuntu-latest` mudou para **Ubuntu 26.04**, `npx playwright install --with-deps chromium` parou nos downloads lentos APT `fonts-ipafont-gothic`/`fonts-wqy-zenhei` e esgotou `timeout-minutes: 12`. O último run autenticado confirmado [#39467414056](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/39467414056) utilizava **Ubuntu 24.04**, com a mesma versão Playwright `1.63.0`, e passou. O log desta falha confirmou `No ephemeral operator was provisioned.`; Control Plane não contém registro para run 40327176953.

**Correção candidata fail-closed:** pin `runs-on: ubuntu-24.04`, conferir `/etc/os-release`, manter `playwright@1.63.0` e instalação de Chromium/com deps, exigir smoke local de browser **antes** de provisionar operador. Os testes Python protegem a ordem, o gate e a ausência de autoprovisionamento em mudanças apenas de workflow. Esta PR altera workflow/scripts/testes/docs apenas: **Preview Console N/A**, nenhuma alteração a Supabase, Auth, WIF, modelo pago ou produto piloto. CI unitária não equivale a uma nova prova autenticada; um novo workflow_dispatch explícito depende da autorização humana de acesso temporário após o merge. Não adicionar o workflow aos paths automáticos para evitar criação involuntária de operador. `product_ready=false`.

## 26/10/2026 — Indicação de estado confiável no Console (candidato)
 
Revisão do componente compartilhado StatusPill da main 144de442: a correspondência por fragmentos de texto fazia os estados inactive, unhealthy e not_ready herdarem a cor de sucesso de active, healthy e ready. Esta era uma apresentação objetivamente enganosa, não uma falha de banco. O candidato elimina sucesso por substring, trata estados incertos e negativos antes de qualquer PASS, usa estados conhecidos de forma explícita, mantém desconhecidos neutros e adiciona nomes acessíveis quando uma legenda personalizada encobre o estado. A regressão executa o TSX real com TypeScript pinado no Console CI, além dos testes Python de contrato. A certificação global segue product_ready=false; Preview e evidência de navegador no SHA do candidato continuam obrigatórios por alterar apps/console/**. Nenhum gate, Supabase, modelo pago, CRM ou merge foi alterado nesta branch.

## 26/10/2026 — Auditoria do deployment ignorado versus GitHub status de sucesso

Evidência independente do merge humano #1107 (Factory main `c44f060939e21eb56e410cf137248f652202e02d`): GitHub Actions `validate` #40261691299 SUCCESS, observador global #40261727445 SUCCESS com `product_ready=false` e `unverified_domains=6`. A integração GitHub anexou status Vercel `success` com `target_url` do projeto/equipe corretos; porém a API autenticada Vercel informa para o deployment `dpl_9sXYWPdP5Lbxobt7uiGh8rCqJA8k` **`CANCELED`** e `errorLink=ignored-build-step`. A commit continha oito arquivos de Python, testes e docs, sem `apps/console/**`; portanto é **Preview N/A**, não um deployment READY. Isso não representa falha do Console: o último deployment de produção listado como READY é `dpl_FXR4ohGZ7mgUmVz7n89TM8S8Wqao` em SHA anterior `d3e6ae1685e2e44118881f94a4bbf0152ebe7bdc`.

**Correção candidata:** a observação `global-readiness-post-ci` consulta o diff de primeiro pai de commit GitHub exato, verifica SHA e parents, checa renames de caminho antigo/novo e pagina o inventário GitHub em lotes de até 100 arquivos, com limite de 30 páginas e bloqueio em inventários incompletos. Status Vercel de SHA sem mudança Console vira `not_applicable` (ainda que GitHub diga success/failure). Se Console realmente mudou, `success` vira `provider_status_success_unverified`, nunca READY verificado apenas pelo contexto GitHub. Falha/pending relevante continua bloqueando avaliação previamente aprovada, sem contornar Preview. Nenhum deployment, migração, credencial ou chamada paga foi disparado. Validar CI do candidato e só então merge humano.

## 26/10/2026 — Evidências atuais e limite de certificação global (candidato)

- A PR #1105 foi mergeada humanamente em `main=112ec58d2043b07426c4c498cd278bb6c888da05`. A migration versionada `20261025214000_repin_terminal_repair_history.sql` foi aplicada com autorização explícita no Supabase Factory; versão registrada `20261025235649`. A função segue `SECURITY INVOKER`: `service_role` pode executar, `anon` e `authenticated` não podem.
- Reconciliação real `project.delivery_target.reconciled` em `2026-10-26T00:26:07Z`: `updated`, `github_actions_exact_sha`, SHA `0429872652e8cb2bc0e9cde618bf5e848190e186` → `08257c0d545bf98c7f34ae40d8b2e221468764ab`, geração `12→13` e versão `11→12`. Não reabrir o Change Set concluído `673a2fc7-5f8c-40da-8bec-18ff6bb7eeed`.
- A auditoria global antiga `#40211772093` era `product_ready=false`, seis domínios não verificados. CI, homologação real CRM e um scheduler verde **não** criam uma avaliação independente atual do produto inteiro.
- Neste candidato, o observer global rejeita status `Vercel` de projeto/tenant não pertencentes à Factory e impede `product_ready=true` enquanto o status do deployment exato está `pending`. Esse é um controle de integridade da evidência, **não** uma certificação de UX, segurança ou operações. CI exata é necessária antes de qualquer merge humano.
- As seções anteriores documentam *candidatos históricos*; não devem ser interpretadas como estado atual de migration, merge ou prova. Nenhuma alteração de Console, RLS, API paga, CRM ou produção é feita nesta branch.

## 25/10/2026 — Corrigir repin do CRM sem reativar histórico (candidato)

- [x] PR #1104 mergeada humanamente em `4585ef50ccee5dcb6740cda7221af0f58990b0f4`; CI `validate` pós-merge SUCCESS, Preview Console N/A.
- [x] Causa do scheduler #40234666427: a RPC CAS retorna HTTP 409 quando dois runs `repair_pending` históricos pertencem a tarefa e Change Set já `completed`, ambos sem lease, embora `factory_control_quiescent=true`. Sem Change Set ativo e sem trabalho atual. O worker registra `error` em vez de mostrar código seguro de conflito.
- [x] Preparar migration somente arquivo SQL `20261025214000_repin_terminal_repair_history.sql`, sem aplicação; excluir da proteção apenas histórico terminal vinculado exatamente ao mesmo CS/projeto/root concluídos, jamais estado ativo.
- [x] Estender PG16 descartável `verify_nonproduction_candidate_repin_postgres.py`: 2 runs históricos, vinculação CS errada, tarefa em andamento, CS aberto, lease ativo, run `ci_pending`, Change Set `review_pending`, CAS concorrente/epoch/SHA forjados. Migrar e testar somente no PG16 isolado.
- [x] Expor apenas `reason_code` fechado de HTTP 409 no job summary; nunca erro SQL bruto/token, não converter bloco em sucesso.
- [ ] Aprovar CI de PR `test`, `factory-acceptance` e `candidate-repin-postgres` no HEAD exato; corrigir regressões. Console Preview N/A.
- [ ] Merge da PR da Factory é humano. Após merge, aplicar migration no Supabase de produção **somente com autorização explícita e preflight de ACL**; registrar versão e verificar exatamente um CAS do projeto autorizado e job scheduled, sem reiniciar qualquer Change Set histórico.
- [ ] Certificação global de seis domínios permanece independente. A prova CRM Preview já passou em auditoria OWNER `#40211815474`; não reexecutá-la.

## 25/10/2026 — Certificação de segurança do Console autenticado (bloco fail-closed)

- [x] P2 certificada por auditor independente `#40211815474` sem produzir release de produção; six-domain global readiness ainda `product_ready=false`.
- [x] Identificado bypass potencial: workflow de operador temporário aceitava qualquer `*.vercel.app` e um host externo podia imitar `/api/health`.
- [x] Preparar controle de origem vinculado ao tenant/projeto Vercel oficial antes de enviar OIDC/auth, verificar status de deployment GitHub, impedir disparo credencial por mudanças somente em scripts/YAML e testar spoofing adversarial com mocks.
- [ ] Validar `node --test scripts/test_console_visual_deployment.mjs` no job `validate` exato, `factory-acceptance` e revisão de PR. Merge da Factory em produção continua humano.
- [ ] Após aprovação de acesso temporário em produção, executar captura autenticada oficial com SHA servido realmente verificado e cleanup e revisar evidências de mobile, teclado, estados e navegação. Sem credenciais novas nesta PR.
- [ ] Só concluir `product_ready` após evidências independentes reais de segurança, observabilidade, test_strategy, UX/a11y, documentação e completude/greenfield, sem usar a auditoria P2 como substituto.

## 25/10/2026 — Bloco final de certificação: auditor externo de Preview multi-wave (candidato)

**Baseline comprovada:** CRM #197 mergeada humanamente apenas em `preview/hardening-release-candidate`, merge SHA `08257c0d545bf98c7f34ae40d8b2e221468764ab`, CI de merge #40205496275 4/4, Vercel READY, Playwright #40205752751 PASS, observer #40205844090 `integrated_nonproduction`, Change Set `673a2fc7-5f8c-40da-8bec-18ff6bb7eeed` completed, produção intacta. A Prova 2 passou em homologação; a Prova 3 confirmou cenários de resiliência PG16 descartável e reparos reais sem completar os seis domínios globais.

- [x] Localizar bloqueio real no auditor OWNER #40206537474: `merged_candidate_without_verified_release` ao exigir release de produção num PR legítimo `preview/**`, e comparação incorreta de Work Units intermediárias com último SHA após reparos.
- [x] Preparar alteração fail-closed para ligar cada Work Unit ao primeiro SHA de integração subsequente, com recibos e comparação byte-a-byte, corrigir deployment-ref Vercel/Preview, observar snapshot pós-merge e adicionar escopo `scope=nonproduction` distinto de `operations`.
- [ ] Testes negativos unitários/CI `validate` no SHA final, revisão da PR e merge **humano** em produção da Factory. Sem migrations, mudança no CRM, APIs pagas ou Console deploy.
- [ ] Após merge, emitir um único OWNER `/factory-journey-audit crm-infodive 7a4a88ac-2ad2-42bc-bc6b-5135035b0d84 2026-10-24T23:40:00Z scope=nonproduction`; exigir `integrated_nonproduction` e artefato real. O comando legado sem sufixo permanece exigindo produção, não pode produzir falso PASS.
- [ ] Certificação global separada em #713/#266: seis domínios, greenfield externo autorizado, papel Codex/capacidade real e UX/segurança/observabilidade de HEAD atual. `product_ready` permanece false sem evidência completa.

Ver `docs/JOURNEY_NONPRODUCTION_EVIDENCE.md`.

## 23/10/2026 — J7: GitHub candidate witness em dois snapshots (candidato)

A auditoria `SupabaseJourneyReader` consultava uma PR antes de inspecionar arquivos, código dos Work Units e CI; `GitHubRestAdapter.get_ci_state` faz outro GET da PR. Se head/base/branch mudassem entre leituras, o relatório poderia combinar evidências de SHAs diferentes. O candidato adota testemunho read-only com identidade completa da PR, SHA exato da branch quando aberta e segunda confirmação após CI. Para PR já mergeada, não exige branch deletada: verifica `state=closed`, `merged=true`, merge SHA e recibos de release. Diff vazio/fork/draft/ref drift falham fechados. Testes offline e runbook: `docs/JOURNEY_GITHUB_EVIDENCE_FENCE.md`. Nenhum Start, SQL, modelo pago, Preview novo ou merge de produção. A prova externa J3/J7 permanece pendente de sandbox autorizado; CI no SHA final é condição de revisão, não de `product_ready`.

## 23/10/2026 — Product Stage: corrigir checkpoint JSON vazio e replay pago idêntico (candidato)

A auditoria read-only encontrou 130 runs sem metadata.stage_evidence, apesar de eventos \`run.stage.recorded\`. A causa reproduzida é \`jsonb_set\` sobre caminho de dois níveis quando falta o pai: a operação antiga retorna \`{}\` sem persistir o estágio. A migration privada \`20261023151218_preserve_runtime_stage_evidence.sql\` cria o pai sob row lock, conserva irmãos e demais metadados, recusa pai malformado, mantém função SECURITY INVOKER/service_role somente, sem RLS permissiva e **sem backfill histórico**.

O runtime agora carimba SHA confirmado no recibo tipado \`planning_non_actionable\`. Antes de uma retomada paga \`stages=['planning']\`, consulta limitada a 40 runs do mesmo task, só bloqueia quando existe recibo terminal completo com origem, snapshot, request original, epoch, mesma instrução e SHA iguais. Guarda fixa: \`planning_resume_no_current_eligible_work_same_sha\`. Uma alteração real de código, pedido, snapshot ou geração continua possível. Recibo legado ausente nunca vira prova inventada de no-work; indisponibilidade de leitura bloqueia modelo por preflight.

Testes Python offline e PostgreSQL 16 descartável validam a nova RPC, concorrência de etapas, ACL e histórico malformado. A \`main\` da Factory não mudou até merge humano; aplicar migration em produção **é gate separado**. Nenhum uso pago, login não oficial, deploy, alteração no CRM, auto-merge ou Preview Console.

## 23/10/2026 — QA operacional isolada: reparo CI até awaiting_release (candidato)

- Reconciliada `main=c613668b9683877cc95e1f922f1c16c4bb5e2ea4`, PR #1065 mergeada; CI pós-merge verde. O Control Plane real está com **zero** registros em `factory_ci_repair_requests`; não inventar um incidente de CI de produção. Os dois runs `failed` dos últimos três dias pertencem a Product Stage histórico, não a reparo de CI.
- Lacuna de evidência: `verify_ci_repair_e2e_postgres.py` exercia a RPC de enfileiramento, tentativas, replay e escopos, mas **não** validava num mesmo cenário a execução `run_ci_once`, commit/resume, recibo verde, especialistas e Preview N/A até `awaiting_release`.
- Novo `ci_repair_disposable_full_journey.py` é importado exclusivamente no runner PG16 descartável existente. Usa `run_ci_once` e `ChangeSetIntegrator` reais da Factory com `factory_enqueue_ci_repair` e `factory_record_ci_repair_result` reais no PostgreSQL isolado; GitHub e persistência de especialistas são dublês sem rede. Simula queda após commit antes de persistir SQL, reconcilia mesma árvore/parent/trailer e bloqueia duplicação de commit e RPC de reparo; comprova recibo `passed` gravado antes dos especialistas e Preview explicitamente N/A com recibo `awaiting_release` sem merge. Projeto pausado bloqueia processamento mesmo com CI verde.
- Não houve migration, alteração do banco real, chamada de modelo paga, edição de piloto, novo preview/deployment ou merge de produção. **Não confundir** prova isolada com um incidente real de CI em operação: issue #1036 permanece pendente até evidência de evento legítimo em produção.

## 23/10/2026 — Retomada do Product Stage sem repetir chamadas pagas (candidato)

- [x] Confirmada execução real Start Github OWNER CRM root `090cd768-b6e5-44ce-9d77-92f9ffe9620d`, falha em `planning` por ledger/reserva (US$ 9,5020792 de US$ 10, reserva US$ 0,50). Duas chamadas reais de modelo geraram reconciliação e gap analysis já duráveis; 7 gaps e 6 trabalhos recomendados.
- [x] Corrigir via RPC versionada `factory_resume_failed_product_planning_v1` que atesta source/snapshot/generation/audit/ausência de supersessão e cria apenas `planning`, sem invocar API nem modificar source run.
- [x] Preparar parser e job GitHub OWNER com broker OIDC restrito e wake pós-commit; adaptar ProductStageExecutor para aproveitar checkpoint e remover duplicidade no prompt.
- [ ] Testes offline e PostgreSQL isolado verdes no SHA final; corrigir regressões sem paid probes.
- [ ] Merge humano da PR da Factory, deploy broker e migration ambos autorizados, verificação de grants. Usuário repôs US$ 10 reais na API OpenAI, mas teto **interno** ainda exige nova decisão humana.
- [ ] Retomada real por OWNER após orçamento interno suficiente; PR de implementação CRM issue #24, CI nativa, Preview browser quando aplicável e `awaiting_release` até merge humano.

## 22/10/2026 — Canal Owner Start sem Console (candidato em desenvolvimento)

- [x] Diagnóstico: Console é atualmente única entrada de continuation com par auditado; GitHub OWNER possui OIDC já utilizado nos audits.
- [x] Interface GitHub dedicada: issue #1055; comando exato OWNER com briefing e validação de event/repo/actor/issue.
- [ ] CI da RPC owner e regressoes PostgreSQL concurrency, idempotência, autorização, epoch e fallback após falha.
- [ ] CI da rota OIDC restrita ao evento owner, leitor de jornada aceitando recibos GitHub autênticos e wake local sem jobs pagos de sondagem.
- [ ] Merge humano, deploy broker e migration de produção explicitamente autorizados, com provas read-only de grants.
- [ ] Um novo Start real `crm-infodive` pela issue #1055, run/task/audit verificáveis; monitorar a jornada até review, CI/Preview e `awaiting_release`, sem auto-merge.

# Plano do Projeto - AI Product Factory

## Visao

Construir uma fabrica de desenvolvimento na qual o usuario descreve o produto, responde ao discovery inicial e, a partir dai, a fabrica conduz o desenvolvimento quase autonomamente ate um ambiente validavel.

## Resultado esperado

O usuario deve conseguir iniciar com algo como:

> Quero um sistema que faca X.

A fabrica conduz discovery, especificacao, planejamento, implementacao, review, testes/evals, preview e release, interrompendo apenas em decisoes humanas reais ou gates de risco.

## Fases

### F0 - Fundacao
- [x] Arquitetura inicial.
- [x] Project Manifest.
- [x] State machine.
- [x] Codex Policy Engine.
- [x] Human Gate Policy.
- [x] Prompts dos papeis.
- [x] CI da propria factory.

### F1 - Control Plane
- [x] Repositorio `ai-product-factory`.
- [x] Supabase dedicado.
- [x] Schema seguro + RLS/server-side boundary.
- [x] Persistencia de projects/tasks/runs/decisions.
- [x] Ledger de ferramentas e Codex.
- [x] Adapter Supabase server-side.
- [x] Registro real de execucoes no control plane.

### F2 - GitHub Autonomous Loop
- [x] Adapter GitHub REST server-side.
- [x] Criar/ler issues.
- [x] Criar branch.
- [x] Persistir plano tecnico.
- [x] Criar commits atomicos e PR.
- [x] Ler CI.
- [x] CI failure evidence.
- [x] Bounded auto-repair.
- [x] Reparo duravel de CI: evidencia SHA-exata, Work Unit limitada, tres
  tentativas, recuperacao idempotente de commit de integracao e recibo verde
  persistido antes de especialistas/Preview. A prova de incidente real segue
  pendente e nao autoriza auto-merge.
- [x] Verified Preview para em `awaiting_release`; merge de producao e exclusivamente humano.
- [x] Release follow-up observa o merge humano, registra evidencia e fecha a issue depois da acao humana.

### F3 - Runtime de Desenvolvimento
- [x] Direct Executor para mudancas pequenas/medias.
- [x] Roteador Direct vs Codex.
- [x] Worker Codex fail-closed: claim atomico, checkout isolado, limites de saida, ledger de invocacao e job OIDC/WIF inerte sem readiness.
- [x] Fallback temporario de Codex manual: handoff duravel em GitHub Issue, PR identificado por marcador de run e retomada automatica em CI sem armazenar credencial humana.
- [x] Provider-neutral Model Executor.
- [x] Budget por tarefa para modelo principal e Codex.
- [x] Pipeline Engine ponta a ponta.
- [x] Project Memory versionada.
- [x] Review/evaluation quality gates.
- [x] Provider OpenAI Responses implementado e ativado via API key com billing real comprovado, budget total interno aprovado de US$ 10.00 em 15/10/2026 (vigora somente após merge humano), reserva mantida de US$ 0.50 e ledger fail-closed por custo.
- [x] OpenAI API WIF implementado no runtime e GitHub (`openai-api`); GitHub OIDC real foi validado. O exchange OpenAI continua bloqueado por mapping administrativo incompatível com o subject imutavel (`invalid_grant`, issue #250), mas agora e hardening de autenticacao externo e nao bloqueia o caminho operacional API key.
- [ ] Provider real do Codex/ChatGPT entitlement (Factory suporta WIF preferencial e fallback oficial `CODEX_ACCESS_TOKEN`; falta criar/configurar a credencial e validar preflight antes de habilitar o worker. WIF beta continua issue #240).

### F4 - Testes, Evals e Preview
- [x] CI deterministico por projeto via manifest.
- [x] Contrato de evals obrigatorios/opcionais.
- [x] Evidence bundle.
- [x] Preview adapter Vercel com configuracao por projeto e fail-closed.
- [x] Browser/E2E command adapter com evidencia estruturada e URL exata.
- [x] Verified Preview runtime com evidencia duravel e fronteira `awaiting_release`.
- [x] Release observer por plataforma GitHub, sem capacidade de merge automatico.

### F5 - Piloto Agente SQL Financeiro — adiado por decisao do usuario
- [x] Onboarding de `agente-sql-langgraph`.
- [x] Importar comando real de regressao: `python scripts/check_all.py`.
- [x] Importar CI real: `Offline validation`.
- [x] Preservar n8n como caminho oficial.
- [x] Preservar LangGraph como offline shadow.
- [x] Registrar projeto no control plane.
- [x] Escolher proxima linha semantica de planned_filters: suporte generico offline a bindings multi-valor (`IN`) concluido no piloto, sem ativacao semantica.
- [ ] Benchmark de 63 perguntas permanece postergado por decisao registrada no projeto.
- [x] Primeira tarefa funcional nova executada integralmente pela factory (#430 dogfood real ponta a ponta, com Direct, CI, specialist lanes, Preview N/A durável, awaiting_release, merge humano e release observer).

### F6 - Greenfield Test
- [x] Validar lifecycle greenfield offline sem chamadas externas.
- [x] Validar que fluxo low-risk pode chegar autonomamente ate Preview; producao permanece sempre sob gate humano.
- [x] Validar greenfield offline com 0 chamadas de Codex/modelo.
- [x] Rejeitar saltos de Preview/Blocked direto para Release/Operations na maquina de estados; caminho seguro fica em `human_gate` (#713). Este teste offline **nao comprova** merge humano observado ou E2E greenfield real.
- [x] Corrigir a continuidade do Start OWNER ate o worker Direct: o wake autenticado agora propaga `run_direct=true` para a mesma workflow, e a matriz do runner prioriza somente receipts de atribuições recém-confirmadas sem ignorar epoch, ledger ou limites de concorrência (#1068). Testes unitários e PostgreSQL16 descartável cobrem a fronteira; isto ainda **não** é a prova GitHub externa de branch/PR/CI.
- [ ] Demonstrar o ciclo greenfield completo com issue/branch/Direct/CI/Preview verificado/gate humano/merge observado/release/operacoes, guardando evidencias SHA-exatas. Contrato de estado sozinho nao substitui esta prova.
- [x] Revisar gates e ampliar autonomia ate o limite seguro: non-prod low-risk autonomo; apenas riscos definidos e producao exigem humano.

### F7 - Factory Finalization
- [x] Definir matriz formal de aceitacao da Factory.
- [x] Criar acceptance gate executavel cobrindo lifecycle, roteamento, Preview, release, operacao, custos e invariantes de seguranca.
- [x] Adicionar check dedicado `factory-acceptance` ao CI da propria Factory.
- [x] Reconciliar migration do worker Codex entre Git e Supabase de producao.
- [x] Separar completude interna de ativacao administrativa de providers externos.
- [x] Validar Control Plane real por smoke transacional com rollback.
- [x] Implementar redesign operacional do Console com dados reais do Control Plane.
- [x] Centralizar design tokens, tipografia, cores semanticas e primitivas reutilizaveis do Console.
- [x] Validar CI/factory-acceptance no GitHub Actions: janela publica temporaria habilitou runners hospedados; `validate` run #1041 passou e o rerun exato do candidato do Console tambem passou.
- [x] Validar build do Console por Preview exato Vercel do candidato `10f593d7d169d30fe5048eac9d98a94b8be1e151` (deployment `dpl_CNFAo32v4DHzjCzgmx1xZUsKFkwX`, `READY`).
- [x] Validar browser/Playwright evidence em Preview exato protegido: GitHub OIDC Trusted Source foi configurado na Vercel e o candidato final pt-BR do PR #269 (`505c712864950d94638c874d8e267531fb544d62`, deployment `dpl_J9kneq8tf9bouJ3StBPyh4UNd7GX`) passou `page_load`, `http_status`, `body_visible`, `expected_text` e `console_clean` no run `36376673624`. O corpo observado confirmou a navegacao principal em portugues. O candidato historico `10f593...` permanece apenas como divida arquivistica; nao e a evidencia do release atual.


### F8 - Orquestracao multiagente adaptativa
- [x] Agent Registry configuravel com perfis, capabilities, ferramentas, budgets e concorrencia.
- [x] Scheduler com assignments atomicos, scope locks e fan-out de workers especializados.
- [x] Execution Team Plan deterministico derivado do engineering plan e do Agent Registry, sem chamada adicional de modelo.
- [x] Selecao explicavel do menor conjunto de especialistas, workers planejados, ondas, exclusoes e blockers.
- [x] Persistencia versionada do Execution Team Plan e audit trail no Control Plane.
- [x] Visualizacao da equipe planejada nos detalhes do projeto.
- [x] Lanes independentes read-only para Security Review, QA/Evals e Operations, com SHA exato, lease/retry bounded, findings estruturados e gate antes do Preview.
- [x] Change Set com work units isoladas por onda, source SHA imutavel, integration branch, conflito de arquivos fail-closed e um unico PR candidato de release.
- [x] Telemetria planned-vs-actual, critical path, rework, conflitos e eficiencia paralela, com replay/provenance e base para comparacao shadow.
- [x] Concurrency adaptativa v1 baseada em trabalho executavel, quota, custo conhecido, repair rate, first-pass yield e latencia de CI, com decisoes auditaveis.
- [x] Corpus offline de evals do Team Planner cobrindo 10 classes de trabalho e penalizando overstaffing, under-staffing e papeis indevidos.

## Gate atual

Em 2026-09-29 o release cumulativo multiagente/Console foi concluido com autorizacao humana explicita: PR #400 mergeado em `a07c9d96e8d1f64861e928c5c361f5b93f8c6d05` e PR #407 mergeado em `54f3ed0445ffda2c8d0974d0d5b5741065294108`. O deployment de producao do #407 `dpl_EskSGj2T7Z6xjtN8KLNV2yAeeX19` esta READY; `/api/health` respondeu HTTP 200 com `54f3ed0445ff`; validate, factory-acceptance, npm ci, typecheck e build pos-merge ficaram verdes; a Vercel nao registrou runtime errors na janela de observacao. A issue visual #309 foi encerrada. O hardening #402 permanece externo/pendente ate a publicacao real do Next.js 15.5.27.

A Factory core esta funcionalmente implementada. O fluxo de Preview protegido esta verificado com Trusted Source GitHub Actions OIDC. O PR #269 foi liberado por autorizacao humana explicita em 2026-09-28 e mergeado em `98d81dee46c7ffc7ae4ae0662712fadcda3258b3`; o deployment de producao `dpl_KEEZQTBxLTcVJCzF42skk4V8kUAf` chegou a `READY`, `GET /api/health` retornou HTTP 200 com o commit correto, a interface pt-BR foi observada em producao e a Vercel nao reportou erros de runtime na janela de verificacao. As migrations de anexos privados, reconciliacao e Current State Snapshot foram aplicadas e verificadas no Supabase de producao. O acceptance gate executavel e a matriz em `docs/FACTORY_ACCEPTANCE.md` definem o criterio objetivo de completude interna. O piloto Agente SQL nao faz parte do fechamento atual e esta explicitamente adiado.

O provider OpenAI Responses esta implementado e ativo. Em 2026-09-28, apos o usuario adicionar US$ 5 de credito ao OpenAI API Platform, o caminho `OPENAI_API_KEY` passou em um smoke bounded real: GPT-5.6 Luna, `reasoning=none`, 35 tokens de entrada, 9 de saida, 44 totais, resposta exata `FACTORY_SMOKE_OK` e custo estimado de US$ 0.0000178, abaixo do teto de US$ 0.01. A evidencia foi persistida no Control Plane. O Primary foi entao ativado explicitamente via API key com budget Factory de US$ 4.00 e reserva de US$ 0.50 por chamada/run, deixando US$ 1.00 do saldo comprado fora do budget como margem. Cada chamada faz pre-reserva duravel, substitui pela medicao real em sucesso e transforma custo nao mensuravel em evento desconhecido que bloqueia novas chamadas.

A estrategia operacional e: ferramentas deterministicas primeiro, API/Direct como caminho principal e Codex apenas quando a complexidade justificar. Billing/quota, budget e ledger do Primary estao ativos com API key explicita; o mapping WIF (#250) permanece um hardening de autenticacao externo independente. A autenticacao autonoma do Codex (#240) nao bloqueia o fluxo: enquanto WIF/access token nao estiverem disponiveis, tarefas Codex podem usar handoff manual e a Factory retoma a partir do PR. Tokens ChatGPT nao oficiais continuam rejeitados.

## Metricas do projeto

- percentual de tarefas concluidas sem intervencao humana;
- percentual de tarefas que realmente usaram Codex;
- taxa de sucesso de CI na primeira tentativa;
- numero de regressoes detectadas antes do merge;
- tempo entre requisito aprovado e preview;
- custo por run / por tarefa quando mensuravel;
- quantidade de gates humanos realmente necessarios.


## Validacoes adicionais

- Auth resolver: mecanismos oficiais apenas; API key para o modelo principal e WIF oficial para Codex, sem expor valores secretos.
- Usage observability: provider/model/tokens/custo conhecido ou explicitamente desconhecido.
- Greenfield offline: lifecycle completo low-risk validado com 0 chamadas externas; producao para corretamente em human gate.


## Auditoria pos-ativacao - 2026-09-28

- [x] Reconciliar 19 migrations Git x Supabase producao.
- [x] Confirmar Control Plane sem runs abertos/falhos ou gates pendentes.
- [x] Versionar o broker OIDC de evidencia visual e proteger seus claims no acceptance.
- [x] Remover atalhos legados de chamada paga fora do ledger/budget.
- [x] Corrigir documentacao que ainda sugeria merge automatico apos CI.
- [x] Preservar API key como auth Primary explicita enquanto WIF #250 permanece hardening externo.
- [x] Fechar #309 apos Preview exato, comparacao visual autenticada contra `Esteira.zip`, release #407 e observacao pos-release sem runtime errors.
- [ ] Leaked Password Protection permanece hardening opcional condicionado a upgrade pago (Supabase Pro+); nao e blocker tecnico no plano Free e nao deve gerar compra automatica.
- [ ] Resolver API WIF #250 quando o mapping administrativo puder ser corrigido.
- [ ] Resolver Codex auth #240 quando houver credencial oficial/enablement.
- [x] Repositorio retornado a private e revalidado com GitHub Actions saudavel (#426).


### F9 - Project Intelligence
- [x] Project Brain v1 deterministico e versionado: tarefas, scopes, capabilities, componentes e fontes/evidencias com provenance.
- [x] Impact Engine v1: blast radius por task_key/grafo, confidence/unknowns explicitos e evidencia duravel antes do builder.
- [x] Requirement Traceability e Definition of Done compilavel (#376).
- [x] Context Packets/sandboxes/repair loops (#377).
- [x] Policy-as-Code/Release Intelligence/rollback (#378).
- [x] Incident Mode/Portfolio Scheduler (#379).
- [x] Replay/Shadow/provenance completo/self-improvement controlado (#380).
- [x] Architecture Guardian v1 com scanners determinísticos, lineage factual e API/dependency surfaces (#381).


### F10 - Operacao, aprendizagem e rastreabilidade
- [x] Test collection guard: nenhum teste `test_*` pode ficar invisivel ao `unittest discover`; 30 checks historicamente ocultos foram reconciliados e a suite real ultrapassa 465 testes.
- [x] Console de Orquestracao em PT-BR para portfolio, incidentes, repairs, release readiness, Replay/Shadow e propostas de melhoria.
- [x] Execution Router v2 baseado em impacto, unknowns, first-pass historico e custo comparativo, sem chamada extra de modelo.
- [x] Proveniencia duravel de run e provenance pointers seguros nos commits/work units.
- [x] Preview final por promocao de candidato exato: branches de implementacao nao geram Preview; somente `preview/**` pode construir o candidato final.
- [x] Validar o candidato cumulativo em Preview exato + browser evidence autenticada: PR #407 head `54b275fbafd7e035fdce983fb2bc976af8b08f64`, Preview `dpl_GB3pzQtX3QHS9Fw5Y9zd7AeRS3zH`, authenticated evidence run `36610828751`.
- [x] Release cumulativo autorizado pelo usuario e mergeado em `54f3ed0445ffda2c8d0974d0d5b5741065294108`; producao `dpl_EskSGj2T7Z6xjtN8KLNV2yAeeX19` READY, health HTTP 200 no commit correto, CI pos-merge verde e zero runtime errors na janela de observacao.


## Atualizacao operacional - 2026-09-30

- PR #423 foi mergeado humanamente em `406fe0023266152aab1cc3d2c45a610ba1e2595b`; Vercel producao esta READY e o health reporta o commit correto.
- OAuth Supabase do CRM e o preflight cross-repo read-only foram concluidos e verificados.
- O repositorio voltou temporariamente a public porque a conta GitHub Free esgotou 2.000/2.000 minutos de Actions para repositorios privados; o usuario decidiu migrar para GitHub Pro no proximo ciclo e entao retornar a private.
- Apos o retorno temporario a public, `validate`/factory-acceptance e CRM cross-repo preflight voltaram a passar, confirmando que o bloqueio era de capacidade/feature da conta e nao regressao da Factory.
- #427 passa a ser prioridade operacional: reduzir runners ociosos do autonomous runner por meio de probe deterministico read-only e server-side skip de jobs sem trabalho.
- Depois do Pro/private, revalidar GitHub Actions, environments, Control Plane OIDC, CRM cross-repo e Vercel.
- O primeiro trabalho funcional novo executado integralmente pela Factory continua como proxima prova end-to-end de produto; o benchmark de 63 perguntas do Agente SQL continua explicitamente postergado.


## Atualizacao operacional - pos-dogfood 2026-09-30

- [x] Dogfood real end-to-end #430 concluido: Direct grounded no repositorio real, Structured Outputs, Change Set multi-wave, CI, specialists, Preview N/A, `awaiting_release`, merge humano e release observer.
- [x] Criacao de PR same-repo via GitHub Actions validada com `GITHUB_TOKEN` nativo; probe PR #465 fechado sem merge; auto-merge continua desabilitado.
- [x] Retry nativo auditavel #443 concluido: RPC fail-closed + CLI `runtime --mode retry`, migration aplicada e historico do source run preservado.
- [x] Alertas operacionais corrigidos para contar apenas falhas acionaveis; runs falhos historicos continuam preservados para auditoria.
- [x] Schedule-probe com telemetria duravel `work_detected/work_classes` sem novo schema e sem alterar semantica de dispatch.
- [ ] Codex WIF #240 continua externo: o suporte confirmou o desenho, mas ainda nao confirmou habilitacao do recurso no workspace Infodive nem forneceu federation rule/audience reais.
- [ ] OpenAI API WIF #250 continua hardening externo; Primary permanece em API key enquanto o preflight WIF nao estiver verde.
- [x] Next.js/dependency hardening #402 concluido e revalidado.
- [x] Repositorio privado/Actions #426 concluido sem compra automatica.


## Atualizacao operacional - 2026-10-01

- [x] Sequencia de UX operacional consolidada ate o PR #514 e guarda-chuva #483 encerrada com evidencia de CI, producao, health e ausencia de erros de runtime.
- [x] `main` reconciliada em `582322059cf564a454c8e7c9cdfda262bbe2459a`, sem PRs abertos no checkpoint.
- [x] GitHub Actions confirmado saudavel no estado publico atual: `validate` e `Console validation` verdes no commit atual.
- [x] Control Plane reconciliado: 3 projetos ativos, 0 runs abertos, 0 falhas acionaveis, 0 gates pendentes, 0 invocacoes Codex e custo conhecido acumulado de US$ 0.3478338.
- [x] Console producao confirmado no deployment `dpl_59HGsseu5UdcXFZip4dPFW7VeMgc`, `READY`, health HTTP 200 no commit atual e zero runtime errors na janela verificada.
- [x] #426 encerrada: repo private e Actions revalidado com sucesso.
- [ ] #240 e #250 continuam dependencias externas de autenticacao e nao devem ser contornadas com valores inventados ou enfraquecimento de gates.
- [x] #474 concluida com ruleset ativo na main, checks obrigatorios e bypass vazio.
- [ ] Leaked Password Protection do Supabase permanece hardening opcional condicionado a plano Pro+; no Free nao e blocker tecnico. Os avisos RLS sem policy publica permanecem intencionais.
- [x] Production merge continua exclusivamente humano; runtime sem auto-merge e `allow_auto_merge=false`.

## Atualizacao operacional - 2026-10-02 GitHub App e Preview

- [x] GitHub App oficial da Factory registrada via Manifest flow, com PEM/client secret armazenados somente no Supabase Vault.
- [x] Registro da App aparece como acao humana real no Console; nenhum repositorio recebe acesso silenciosamente.
- [x] Preview promotion automatico corrigido e validado: novo ref e semeado no parent e avancado ao SHA exato para disparar uma unica promocao observavel pela integracao GitHub/Vercel.
- [x] PR #595 preparado para centralizar em `/gates` a instalacao/verificacao da App por projeto; candidato exato esta com CI, Preview e browser evidence verdes e aguarda exclusivamente merge humano de producao.
- [x] Fase 3 do runtime preparada no PR #599: token de instalacao efemero e restrito ao repository_id verificado, sem persistencia de PEM/token e sem fallback silencioso quando um projeto ja migrou para `github_app`.
- [x] GitHub App instalada e verificada no CRM Infodive por consentimento humano explicito; Control Plane em github_app/ready.
- [x] Fase 3 do runtime liberada e autenticacao cross-repo real comprovada sem `FACTORY_GITHUB_TOKEN` no preflight Actions run 37209692130 (`github_app_only`, token efemero, sem persistencia).
- [ ] Validar a primeira escrita cross-repo real via GitHub App na proxima tarefa funcional do CRM; nao criar mutacao sintetica nem ampliar workflows confiaveis apenas para teste.
- [ ] Avaliar separadamente a instalacao no Agente SQL; nao ampliar acesso junto com o CRM.

## Atualizacao operacional - 2026-10-04
- [x] Fluxo de continuidade de projetos consolidado no Console: pedido duravel, anexos privados, contexto do ultimo pedido, download autenticado e historico bounded baseado em auditoria.
- [x] CRM Infodive reconciliado em `operations`, sem PRs/issues abertos no checkpoint e com Vercel verde no `main` `23b4992727adb768a7a5b513cd0a181ea5d1e2d5`.
- [x] Factory reconciliada em `main` `c1e003ad8a6f7cf0192c6ec65e95d31ec9c651fe` apos merge humano do PR #633; release de producao deve ser verificado separadamente antes de ser declarado concluido.
- [x] Control Plane no checkpoint: zero tarefas abertas, zero runs abertos e zero gates pendentes para Factory e CRM.
- [ ] #240 Codex WIF continua externo e depende de enablement/federation values oficiais.
- [ ] #250 OpenAI API WIF continua hardening externo; nao substituir o caminho operacional selecionado sem preflight verde.
- [x] #426 encerrada: repositorio esta private e GitHub-hosted Actions voltaram a executar com CI verde, sem compra automatica nem reducao de isolamento.
- [x] #474 concluida: protecao da `main` reforcada no GitHub; runtime permanece sem auto-merge.
- [ ] Leaked Password Protection do Supabase permanece hardening opcional condicionado a plano Pro+; no Free nao e blocker tecnico. RLS fail-closed sem policies publicas permanece intencional.
- [ ] Benchmark de 63 perguntas do Agente SQL continua postergado.
## Atualizacao operacional - 2026-10-04 protecao da main
- [x] #474 concluida: ruleset `Protect main - human release` ativo para a default branch, sem bypass, com PR obrigatorio, bloqueio de deletion/force-push e checks `test` + `factory-acceptance`.
- [x] Gate humano de producao reforcado no proprio GitHub sem reintroduzir auto-merge no runtime.
- [ ] #240 permanece externo: aguarda enablement/valores oficiais de Codex WIF para o workspace Infodive.
- [ ] #250 permanece hardening externo: aguarda correcao administrativa do mapping OpenAI API WIF.
- [ ] Supabase Leaked Password Protection permanece hardening opcional condicionado a plano pago e nao bloqueia o encerramento tecnico no Free.

## Reconciliacao operacional - 2026-10-14 apos #807

- Core deterministico e observabilidade evoluiram; nao declarar Factory `product_ready` por CI verde. Exigir E2E greenfield/existing, gates, operacao e auditoria #713.
- `main` verificada `10016635fdd09a87e598220df1b7ecf733fd4d71`, CI #38629927087 SUCCESS. Hotfix #805, comprovacao de scheduler #806 e paginacao de runs #807 integrados por merges humanos.
- Scheduler: alert-only #38628800312 SUCCESS e #809 `scheduler_pipeline` aberta; aguardando duas execucoes nativas consecutivas completas. Nao confundir heartbeats, backups e verificacoes manuais.
- Continuacao transacional #786 esta bloqueada para release por Preview SHA-exato indisponivel. Migration foi aplicada (versao `20261014192321`), nao repetir SQL. Registrar provas antes de qualquer merge.
- Vercel: novo rate limit sobre SHA #786 as 19:42:26 UTC do dia 14/10. Evitar novos Preview desnecessarios, novas tentativas sem evidencias de liberacao e deploy em producao automatico.
- WIF Codex/OpenAI dependencias externas separadas; modelo primario pago permanece desligado e qualquer alteracao de billing exige aprovacao explicita.

## Prova pendente depois da limpeza operacional de 19/10/2026

- [x] Integracao de CI passa a exigir workflow GitHub Actions completo no SHA exato e deduplicar dispatch (PR #983, merge humano 3da90ed2628d240c47163f7ce3ec676c4f59e86e).
- [x] Control Plane reconciliado sem Change Sets pendentes e com registros antigos aposentados sem perda de auditoria.
- [ ] Novo projeto explicitamente iniciado por pessoa completar o E2E real sem reparos manuais: Product Stage, Change Set, Direct, PR, CI, Review, Preview aplicavel (ou N/A duravel), awaiting_release, merge humano observado e operacao.
- [ ] Publicar auditor somente leitura por Start/run exato, sem reativar itens antigos e sem chamar modelos pagos para sondagem; validar com CI no candidato e depois com evidencias do ciclo real.


## Pós-E2E 20/10/2026 — Próximo salto de autonomia (#713)

A jornada E2E real da Factory foi comprovada em 12/12 etapas até operação; a release `#997` e o auditor de issue `#987` são evidência de entrega, **não** de produto universalmente pronto. `product_ready=false` e `not_assessed` permanecem verdadeiros.

- [x] Diagnóstico de admissão por projeto/run executado no Control Plane sem modelos, #999/#1000, workflows #39455676878 e #39455945061 (read-only).
- [ ] Preservar gap auditável de prontidão global após release, associando relatório, project/run e merge exato, sem fabricar tarefas nem apagar gaps no snapshot de `operations`; validar CI e observação operacional pós-merge.
- [ ] Completar auditor global de seis domínios com evidência atual por SHA, inclusive experiência Console/móvel, segurança, E2E representativo e operação; até lá `product_ready` é `not_assessed`/`not_ready`.
- [ ] Com autorização de execução já vigente no projeto, garantir que a Factory use gaps verificados como contexto para trabalho subsequente sem rodar modelos apenas para verificar disponibilidade ou gerar replays de tarefas encerradas.


## Continuidade pós-#1001 — Auditor global verificável (#713, candidato)

- [x] PR #1001: emissão de handoff de lacunas `not_assessed` após release e
  inclusão no contexto de futuras reconciliações. Após merge no
  `772183c169976c78d4a073ba9d5d4b202e8c1874`, CI #39458416997
  SUCCESS e read-only live #39458546205 comprovou
  `idle_with_unassessed_global_product_readiness`.
- [ ] Implementar e executar automaticamente auditor read-only de produto
  **no HEAD exato validado**, com recibo de CI, Git tree completo, projeto
  autêntico, avaliação durável de seis domínios e baseline adicional para
  existentes. PR candidata com testes negativos; não supor implementada
  até merge e artefato real pós-main.
- [ ] Conduzir verificação real de segurança/isolamento, UX/artefatos visuais,
  E2E críticos, rollback/ops, documentação e funcionalidade em diversos
  tipos de projetos, produzindo avaliações independentes antes de
  declarar `product_ready`.

## 20/10/2026 — Auditoria global: correção do OIDC real (#713)

- [x] #1002: código e contrato global de seis domínios integrados à main, CI #39460100571 SUCCESS.
- [ ] Execução real pós-main falhou no broker OIDC (#39460182317). Reutilizar `autonomous-runner.yml` confiável sem ampliar allowlists; `validate` main push só dispara auditoria, nunca scheduler/workers pagos.
- [ ] Exigir recibo exato com `test` + `factory-acceptance` do próprio run `validate`, HEAD ainda corrente e `product_ready=false` até avaliações globais independentes. CI/Preview/merge humano obrigatórios antes de registrar sucesso.


## 20/10/2026 — Bloco de operabilidade do Console (#713, candidato)

- [x] Auditor de prontidão global `global-readiness-post-ci` comprovado de
  forma independente no workflow #39462579687, SHA de `main`
  `393d91fe4dbd4542e0e73b5a10827bc6bd21bd45`, 6 domínios pendentes.
- [ ] Resolver lacunas concretas no Console: próximo passo `operations`
  deve destacar auditoria global; setup não pode conter nome/owner fixos;
  tipografia/touch/mobile/teclado devem ser verificáveis; seis domínios
  devem continuar visíveis mesmo sem avaliação durável. Candidato precisa
  CI completo e Preview/browser evidence no SHA exato antes de merge.
- [ ] Consolidar produto globalmente pronto só após **execução real** da
  auditoria de segurança/isolamento, E2E de projetos de naturezas diferentes,
  recuperação/idempotência, operações, UX/a11y e runbooks em HEAD atual,
  sem alterar gate humano ou política financeira.

## 20/10/2026 — Gate pós-browser de prontidão, sem custo (#713)

- [x] #1005 mergeada em `e6c045cc20ce47040bdbe9d268fa2f1459bb221c`:
  GitHub validate, Console build, Preview e browser no SHA candidato; após
  release, Vercel production READY, captura autenticada #39467414056
  SUCCESS com artifact criptografado, e global observer #39467480783 SUCCESS.
- [ ] Bloqueio estrutural factual: o observer pós-CI executou **antes** da
  captura autenticada, então o snapshot não inclui a evidência operacional
  mais recente. Candidato reconcilia conclusão do browser no mesmo workflow
  OIDC confiável, sem iniciar scheduler, ampliar acesso ou gerar billing.
- [ ] Após merge humano do candidato e próxima mudança autorizada no Console,
  observar dois recibos independentes (CI e browser), comparando sha, jobs,
  artifact e Vercel; manter `product_ready=false` até avaliação formal
  de seis domínios e cenários greenfield/existing.

## 20/10/2026 — Elegibilidade de scheduler e comando humano (#894)

- [x] Verificado no Supabase real: controle por projeto, generation/version, RPC transacional de claim v2, outbox e observador de wake já existem. Não duplicar scheduler.
- [ ] Migration proposta: acrescentar filtro por `running` e `generation>0` aos seletores `factory_portfolio_candidates` e `factory_peek_planned_work`. A ausência desse filtro anunciava elegibilidade falsa, embora o claim v2 bloqueasse execução indevida.
- [x] RPCs legados sem esse filtro não têm grant para `service_role`, `anon` ou `authenticated` e o adapter atual usa v2: não reativar APIs antigas.
- [ ] CI e aprovação humana para migration de produção, depois conferir contratos reais sem iniciar runs/modelos. Não misturar auditoria histórica de E2E com novo bootstrap.

## 20/10/2026 — Sinais de fila obedecem execução humana (candidato)

- [x] Produção inspecionada: scheduler signals ainda anunciam Product Stage,
  Direct/Codex manual e specialists em projetos sem `running`; filtros
  de dispatch `#1007` estão versionados, mas não aplicados no Supabase.
- [ ] Corrigir `factory_scheduler_queue_signals()` para ignorar projetos
  draft/paused/stopped/pausing/stopping e geração zero nos seis sinais ativos,
  preservando observação read-only e claims/gates existentes.
- [ ] Exigir CI, depois **autorização humana separada para migrations de
  produção** e verificação SQL no banco antes de declarar correção ativa.

## 20/10/2026 — Fencing dos caminhos de agente/especialista (#894)

- [x] Seis funções de produção sem guard próprio foram identificadas na consulta `pg_get_functiondef`; scripts antigos já revogados não foram reativados.
- [ ] Versionar migration `20261020190000` para atribuições, specialist claims, specialist lane creation e repair sem execução em paused/stopped, preservando locks da assert de projeto.
- [ ] Exigir CI, testes de integração isolados e gate de migration de produção; não inferir instalação no banco pelo merge.
- [ ] Revisar recovery de lease/change set e continuidade de decisões sob pausa antes de declarar controle do ciclo integralmente concluído.

## 21/10/2026 — Retomada sem replay implicito de execucao (#894)

- [x] Codigo de producao investigado: recuperacao de lease e claim antigo nao vinculavam metadata.execution_generation a geracao atual apos Resume.
- [ ] Provar com PostgreSQL isolado as 5 funcoes do candidato cross-epoch, incluindo Product/Direct, Change Sets e retry explicito.
- [ ] Apos merge humano e gate SQL individual, aplicar migration `20261021021000_quarantine_cross_epoch_recovery_replay.sql` sem usar `db push` historico; registrar version ID real.
- [ ] Validar recuperacao de especialista e operacoes externas nao idempotentes como risco residual separado.

## 21/10/2026 — Fechamento do Pause/Stop para terminal-descendant recovery (#894)

- [x] Auditoria read-only verificou migration de recovery aplicada no Control Plane e identificou RPC terminal-descendant sem controle humano.
- [ ] Deploy protegido da unica funcao `factory_reconcile_terminal_task_descendants()` apos CI/PR e autorizacao especifica da nova migration.
- [ ] Validar nenhuma mutacao em paused/stopped durante Pause concorrente; manter cleanup e deduplicacao em projeto running no PostgreSQL isolado.

## 20/10/2026 — Recovery de leases após controle humano (#894)

- [x] Três migrations do scheduler/agent-specialist aplicadas e verificadas no Control Plane real, com ACL/RLS preservados, histórico registrado sob versões MCP `20261020185723/20261020190213/20261020190346`.
- [ ] Bloquear **mutação de recovery** em paused/stopped: cinco RPCs de leases, Change Sets, especialistas, decisões e retry de failed run. Não reexecutar runs históricas ou modelos em teste.
- [ ] Verificar concorrência com pausa usando locks de controle `FOR SHARE`; teste PostgreSQL isolado real, CI, e só então solicitar merge de produção e nova autorização de migration.
- [ ] Reconciliação de `supabase db push` deve comparar version IDs MCP por nome/assinatura, sem replays automáticos; origem Git permanece fonte de verdade do SQL.

## 20/10/2026 — Sem efeitos determinísticos após Pause/Stop (#894)

- [x] #1011 mergeada em `dde76b4a402be98eea26acac2302c7b6c0b5a941` com CI main #39483075109 verde. Migration de recovery aguarda autorização/aplicação, não pressupor banco atualizado.
- [ ] Proteger side effects pós-claim: despacho de CI, deploy/browser de Preview, review specialist e release observer com checkpoint current state + geração ativa; retornar espera sem inventar delivery ou false-green.
- [ ] Garantir fair continuation: candidata pausada não pode mascarar outro projeto em `run_ci_once`, `run_release_once` e `run_preview_once`, com limites de observação e sem loops.
- [ ] Executar testes offline e CI, testar pausa concorrente HTTP 409, autorização desconhecida, dados adulterados, nenhuma escrita/dispatch para paused. CI sucesso não remove gates de Preview/produção/migração.
- [ ] Autorizar migration de recuperação #1011 separadamente; depois validar cenários greenfield/existing em PostgreSQL isolado e Control Plane leitura.

## 21/10/2026 — Fencing final de especialistas apos Resume (#894)

- [x] Confirmadas no Control Plane real as migrations terminal-descendant e cross-epoch com historico versionado e privilegios restritos.
- [x] Identificada ausencia de protecao transacional em `factory_complete_specialist_lane`; queue/recover tambem nao vinculavam epoch do job.
- [ ] Validar migration de quatro funcoes e worker Python no PostgreSQL 16 isolado, com dois interleavings Pause/complete, lease token, dedupe e fair selection.
- [ ] Apos CI + merge humano, obter autorizacao especifica para `20261021030000_fence_specialist_epoch_and_lease_token.sql` e aplicar em producao. Sem credenciais de modelo ou auto-merge.

## 21/10/2026 — Handoff atomico entre review e reparo

- [x] Falha entre `factory_complete_specialist_lane` e `factory_enqueue_repair_from_specialist` delimitada; close-recheck sem controle de geracao tambem identificado.
- [ ] Certificar transacao unica de reviews, reparos e close no PostgreSQL isolado, rollback e idempotencia HTTP.
- [ ] Apos merge e autorizacao separada, ativar as migrations `20261021030000` e `20261021040500` na ordem, reconciliando IDs de historico do Supabase antes de aplicar.

## 21/10/2026 — Conclusao especialista com Definition of Done sem transacao parcial

- [x] Reconciliacao main + migrations anteriores aplicadas e ausencia de work ativo no Control Plane.
- [x] Detectada chamada de evidencia fora da transacao de review/reparo. Novo RPC fail-closed para nao haver sucesso parcial durante rollout.
- [ ] Validar PostgreSQL isolado com DoD ligado/erro/rollback e auditoria unica; certificar CI da PR.
- [ ] Merge humano e gate de migration separado para `20261021041000_atomic_specialist_traceability_evidence.sql` (nenhum paid test).

## 21/10/2026 — Observação transacional e recuperação de releases humanos (#894/#713)

1. [x] Identificar defeito funcional no Control Plane real: release humana #997 em `operations` com snapshot sem gaps e sem follow-up auditável, proveniente de múltiplas escritas REST independentes.
2. [x] Preparar função SQL versionada que comprova run/report/merge SHA e grava operações, manifest, gaps e auditoria atomicamente.
3. [x] Preparar outbox a partir de marcação `released` comprovada, com reparo autônomo somente de releases previamente observados, sem agir sobre merge/CI/modelo.
4. [x] Isolar registros de proveniência definitivamente inválida com `needs_review`, preservando fairness e idempotência; manter erros transitórios reexecutáveis.
5. [ ] Confirmar testes Python e PostgreSQL 16 isolado em CI; somente depois submeter PR única ao gate humano de merge. Migration `20261021090000_atomic_release_state_and_replay_outbox.sql` só pode ser aplicada com autorização específica posterior.

A release antecipada do Service Desk permanece bloqueada, não é prova para promoção retroativa; `product_ready=false` continua.


### 21/10/2026 — Complementos obrigatorios ao handoff de release #1025
- [x] Preflight versionado sem writes antes de converter run em merged/released.
- [x] Change Set completado na mesma transacao de estado do projeto, snapshot e audit.
- [x] Pause/Stop + geracao impedem reconciliacao atrasada e starvation entre projetos.
- [ ] Exigir PostgreSQL isolado, Python e CI verdes apos este conjunto antes de merge humano; migration continua gate separado.

## 21/10/2026 — Recuperação seletiva de readiness histórico (#713/#894)

1. [x] Reconciliar a versão aplicada da RPC atômica (#1025) no Supabase real sem repetir SQL e registrar falha remanescente na release #997.
2. [x] Projetar seletor de provenance sobre `last_release` atual, merge humano auditado, projeto ativo e geração, sem admitir Change Set antecipado.
3. [x] Preparar wrapper que reconcilia manifesto/snapshot/gaps e auditoria na mesma transação com idempotência, seleção limitada e revisão durável de inconsistências.
4. [x] Integrar caminho Python/CLI/workflow offline-first independente do outbox recente, validando página inteira e sem model calls, deploy, merge ou bootstrap.
5. [ ] Executar QA unitário + PostgreSQL 16 isolado + CI; corrigir bugs reais antes de submeter uma única PR ao gate humano. Nova migration `20261021135000_recover_latest_legacy_release_readiness.sql` exige autorização específica posterior. Control Plane real permanece inalterado até tal gate.


## 21/10/2026 — OWNER /factory-wake e settlement real (#894/#713)

1. [x] Reconciliar `main`, Supabase e scheduler. Migration legado registrada; candidato #997 comprovado via RPC read-only.
2. [x] Acionar /factory-wake com login GitHub do OWNER e constatar `schedule-probe` real + OIDC verde; notar 4 steps determinísticos `skipped` por filtro de evento.
3. [x] Preparar gate redundante exato owner+comando, sem abrir via issue_comment genérico ou bot.
4. [x] Permitir apenas nos 4 passos existentes: controle manual, outbox de release humano, readiness legado, project-control wake. Manter fila de modelos/CI/Preview independente e sem auto-merge.
5. [ ] CI + QA de 6 contratos offline e merge humano em produção; depois repetir wake e observar evidence SQL verdadeira para release #997. Se o cron entregar primeiro, não criar jobs redundantes nem duplicar reparo.


## 21/10/2026 — Diagnóstico verídico de Change Set terminal #713

1. [x] Auditar a continuação real #987 da Factory: 12/12 etapas verificados por job read-only e merge observado, produto inteiro ainda not_assessed.
2. [x] Auditar CRM `8b607...`: 5/12; apontar implementação não vinculada, sem considerar outras runs como prova.
3. [x] Reconciliar diagnóstico `run_completed/no_new_action` com evidências do Change Set `552fd082...` marcado superseded e geração antiga, protegendo origem por projeto/root.
4. [x] Preparar leitor e classificador offline-first, bounds, rejeição de identidades cruzadas e inferência zero de entrega; testes para CRM, Service Desk, epoch, múltiplas linhagens e sanitização.
5. [ ] CI Python/Factory Acceptance no SHA exato, merge humano de produção e repetir auditoria de admissão CRM para verificar sinal correto. Sem migration, modelos pagos ou Preview do Console.


## 21/10/2026 — Five-block exact candidate gate auditor (#713)

1. [x] Provar scheduler native com gap real e backup funcional, sem apagar alertas.
2. [x] Preparar reader cross-repo project/PR SHA e controle operacional com bounds.
3. [x] Preparar CI de repositorio de destino, diferenciando skipped/retry e QA de outro repo.
4. [x] Preparar avaliacao Preview por politica e diff e historico de Change Sets bloqueados, sem release/replay.
5. [x] Preparar owner-only trigger, artefato de evidencia e regressao offline; [ ] CI e merge humano, seguido de auditoria real do Service Desk #5 sem mudancas de banco.

