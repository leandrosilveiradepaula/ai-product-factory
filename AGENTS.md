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
