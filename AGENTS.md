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
