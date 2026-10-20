# AGENTS.md

## Regra principal

Este repositorio implementa uma fabrica autonoma de desenvolvimento. O objetivo nao e maximizar chamadas de agentes; e maximizar resultado confiavel com o minimo de custo e intervencao humana.

## Ordem de preferencia de execucao

1. Ferramenta direta e deterministica.
2. ChatGPT/orquestrador com acesso direto ao repositorio/servico.
3. Agente especializado de baixo custo.
4. Codex somente quando a complexidade justificar.

Enquanto a autenticacao autonoma do Codex nao estiver disponivel, uma tarefa realmente classificada para Codex pode usar handoff manual duravel: a Factory prepara a GitHub Issue, espera o PR produzido pelo operador no Codex e retoma automaticamente em CI. Isso nao transforma complexidade em gate de produto e nao bloqueia tarefas Direct/API independentes.

## Nao usar Codex para

- discovery;
- PRD;
- documentacao;
- operacoes GitHub simples;
- operacoes Supabase simples;
- deploy/configuracao simples no Vercel;
- alteracoes pequenas e localizadas;
- leitura de logs e consolidacao de resultados.

## Considerar Codex para

- refatoracao grande em muitos arquivos;
- debug profundo com varias camadas;
- implementacao complexa com muitos ciclos editar/testar/corrigir;
- migracao mecanica extensa;
- investigacao de codebase muito ampla quando o executor direto nao for suficiente.

## Gates humanos

Nunca executar automaticamente:
- exclusao ou perda potencial de dados de producao;
- deploy de alto impacto em producao;
- criacao de servico pago recorrente sem aprovacao;
- alteracoes sensiveis de autenticacao/permissao que ampliem acesso;
- mudanca material de requisito de produto.

## Disciplina de commits e consumo de CI

Para reduzir GitHub Actions e Vercel sem reduzir cobertura:

- agrupe alteracoes relacionadas em um unico commit antes de atualizar uma branch remota quando a ferramenta suportar tree/commit atomico;
- nao publique um commit intermediario por arquivo apenas para montar a mesma mudanca;
- quando commits sucessivos forem inevitaveis, mantenha apenas o head mais recente como candidato e deixe CI/Preview cancelar ou ignorar trabalho obsoleto;
- abra/atualize PR somente quando existir um candidato coerente; evite churn de head que dispare validacoes e Previews sem valor;
- nunca contorne o budget de Preview para compensar excesso de commits; corrija a origem do churn.

## Regra de merge e release

O operador/orquestrador esta autorizado a executar diretamente merges de PRs elegiveis quando o merge **nao publica producao** e todos os gates aplicaveis estiverem verdes. Nesses casos nao e necessario pedir confirmacao humana a cada PR.

Condicoes minimas para merge operacional autonomo:
- CI e acceptance aplicaveis verdes;
- PR mergeable e head SHA ainda igual ao SHA verificado;
- nenhuma mudanca material de requisito;
- nenhuma perda/destruicao de dados;
- nenhuma ampliacao de acesso sensivel;
- nenhuma criacao de servico pago recorrente;
- o merge nao dispara release de producao.

Isso e autorizacao do operador, nao capacidade do runtime. O adapter GitHub da Factory continua sem funcao de merge automatico e o recurso GitHub auto-merge nao deve ser habilitado como atalho.

CI verde, quality gate e Preview verificado nao autorizam merge de producao. Quando o merge do PR publica producao, a Factory deve parar em `awaiting_release`. Esse merge continua sendo uma acao humana explicita.

A acao humana pode acontecer no GitHub ou, quando o Console de producao estiver explicitamente ativado com credencial dedicada e allowlist, pelo botao administrativo de merge do proprio Console. Isso nao e auto-merge: nao existe scheduler, agente, runtime Python ou adapter capaz de acionar esse caminho. O Console revalida release report, PR aberto, branch base, repository allowlist e SHA candidato exato antes de chamar o GitHub. O release observer continua reconciliando uma acao humana ja realizada.

Migrations de producao seguem a mesma fronteira humana. Quando um gate duravel declara `requested_action=apply_control_plane_migration`, um administrador pode aplicar a migration pelo Console somente por clique explicito. O Console busca o SQL apenas do arquivo versionado no SHA candidato, revalida PR/checks/politica, usa credencial Supabase Management dedicada somente server-side e aplica pelo endpoint oficial de migrations. Scheduler, runtime Python e agentes nao podem acionar esse caminho automaticamente.

## Semantica de prontidao

Nunca use "pronto", "concluido", "100%" ou equivalente para um produto inteiro com base apenas em uma tarefa, PR, CI verde, Preview, release candidate ou fluxo parcial validado.

A Factory deve distinguir explicitamente quatro escopos:

1. **work_item_complete**: a tarefa/change set atual cumpriu seus criterios e evidencias;
2. **release_candidate_ready**: o SHA candidato cumpriu os gates aplicaveis para chegar ao gate humano de producao;
3. **release_completed**: um release humano foi observado e reconciliado;
4. **product_ready**: o produto inteiro passou por auditoria global e possui evidencias atuais de seguranca, autorizacao/isolamento, observabilidade/operacao, estrategia de testes, experiencia de produto (quando aplicavel), documentacao/runbook e ausencia de blockers criticos conhecidos.

`release_candidate_ready` e `release_completed` **nao implicam** `product_ready`. A ausencia de issues abertas tambem nao prova prontidao do produto. Quando nao houver uma auditoria global recente e duravel, o estado de produto deve ser `not_assessed` ou `not_ready`, nunca inferido como pronto.

Antes de declarar um app/projeto pronto, reconciliar o produto como um todo e registrar explicitamente os blockers e as evidencias. Para produtos existentes importados, a auditoria inicial deve procurar divida herdada (mocks/no-ops, seguranca/RBAC/RLS, observabilidade, testes/E2E, UX/a11y/responsividade, documentacao e operacao), mesmo que a tarefa atual nao toque essas areas.

## Regra obrigatoria: cinco blocos por ciclo de desenvolvimento

Ao receber "prossiga", "continue" ou pedido equivalente para desenvolver a Factory, tratar a rodada como um **ciclo de entrega**, nunca como um unico commit, teste ou ajuste.

1. Antes de editar, identificar **cinco blocos substanciais** ligados a prioridade atual (por exemplo: fluxo operacional, workers, seguranca/concorrencia, interface, testes/evidencias).
2. Executar os cinco blocos na mesma rodada, de forma autonoma. Um bloco deve produzir mudanca funcional, integracao, correcao ou evidencia verificavel; consultar status de CI, isoladamente, nao conta como bloco.
3. Agrupar mudancas relacionadas em uma PR e minimizar commits/workflows desnecessarios. Nao abrir PR para cada pequena correcao.
4. Validar testes e CI, investigar falhas e corrigir quando possivel. Para Console, exigir Preview verificado no SHA exato quando aplicavel.
5. **Nao encerrar a rodada apos o primeiro commit, primeira verificacao ou primeiro bloco.** Entregar um relatorio consolidado apenas apos os cinco blocos ou diante de um bloqueio externo real.
6. Se um bloco depender de credencial, permissao, custo ou gate humano, registrar o impedimento e prosseguir nos blocos independentes.
7. Nunca afirmar que os cinco blocos foram concluidos sem evidencias. Distinguir claramente implementado, testado, pendente e bloqueado.
8. Os gates existentes prevalecem: nao realizar merge de producao, migration de producao, ampliacao sensivel de acesso, compra ou outra acao irreversivel sem autorizacao humana especifica.

**Criterio de encerramento:** cinco blocos substanciais concluidos e verificados, ou impossibilidade real de continuar com seguranca. Respostas de progresso e commits isolados nao substituem esse criterio.


## Política de testes: offline-first antes de modelos pagos

Em toda evolução da Factory, executar primeiro testes unitários, regressões,
contratos, simulações determinísticas, PostgreSQL local, CI e Preview/browser
quando aplicável. Nunca consumir API de modelo apenas para smoke, readiness,
credenciais/quota ou tentativa de resolver falha reproduzível sem modelo.
Usar modelo pago somente para capacidade que realmente necessita de semântica
de LLM, após preflight estrutural e dentro do ledger/budget/reserva real.
Custo pago desconhecido bloqueia; nenhuma compra automática.

O auditor separado \`scripts/audit_offline_product_preflight.py\` é somente
leitura e nunca reabre runs. \`source_preflight=verified\` não significa
Product Stage concluído nem E2E verificado. \`docs/OFFLINE_PRODUCT_PREFLIGHT.md\`
é o procedimento operacional.

## Execucao direta de auditorias gratuitas

Se o conector GitHub da conversa nao expuser workflow_dispatch, preferir o
canal owner-only de issue_comment com o comando exato
`/factory-offline-preflight <project_key> <run_uuid>` na issue da Factory.
O job usa workflow main ja autorizado, apenas GET, parsing estrito e
permissoes read-only de GitHub. Nao converter isso em Start/retry/merge
automaticos ou autorizacao para uso de modelo pago.


## Admissao de fonte antes de qualquer modelo pago

Em continuacoes `platform` com `reconciliation`, verificar governanca,
SHA exato e escopo por GET antes de enviar prompt ao modelo.
Recibos estruturalmente invalidos ou contraditorios bloqueiam consumo
pago com motivo fixo redigido; nao gravar erros vindos do provedor.

Arquivos ausentes podem ser novos arquivos a desenvolver; trechos omitidos
ou truncados podem representar trabalho complexo, nunca gate humano automatico.
Classificar escopo como `complete`, `partial`, `new_files_only` ou
`unscoped`, sem afirmar codigo verificado quando nao foi inspecionado.
Sem chamadas LLM de sondagem, sem hardcodes de cliente, nem auto-merge,
migrations ou alteracao de budget.

## Evidencia executada versus simulacao em Product Stage

Nunca considerar `requires_model=true`, `deferred=true` ou modos
`placeholder/mock/fixture/simulated/dry_run` como Discovery,
Specification, Planning ou Reconciliation concluidos. O worker deve
falhar fechado antes de gravar status `completed` ou avançar a run.
Modelos pagos so podem produzir progresso real dentro do ledger; resultados
deterministicos genuinos continuam possiveis sem esses marcadores.

Planning nao pode concluir uma run sem um array `tasks` e pelo menos
uma tarefa acionavel ou decisao material ainda nao resolvida. Se nao houver
trabalho, registrar o impedimento tecnico como evidencia: nunca fabricar
tarefas nem marcar a implementacao ou E2E como realizada.


## Change Set para projeto platform

`factory_projects.project_kind='platform'` e classe operacional valida,
distinta de `existing` importado (exige PR Preview fixado) e de
`greenfield`. O Product Stage, o work-unit builder, o claim de
integracao e o integrador devem aceitar somente este tipo explicito
gravado no Control Plane. Para platform, capturar `main` no SHA exato,
congelar a fonte do Change Set e rejeitar deriva do SHA antes de
materializar integracao; PR final tem base `main` protegida.
Nunca escrever/mergear diretamente em `main` pelo runtime.

Quando uma run real ficar blocked ANTES de produzir qualquer commit,
nao pagar Discovery/Planning novamente sem necessidade. Uma recuperacao
pontual so pode ocorrer por RPC versionada, explicitamente autorizada,
com provas de escopo, identidade do run, generation, work unit sem
base/output e blocker imutavel. Proibido retry generico ou repassar a
mesma run de Product Stage ao modelo.
