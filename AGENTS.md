# AGENTS.md

## Regra principal

Este repositorio implementa uma fabrica autonoma de desenvolvimento. O objetivo nao e maximizar chamadas de agentes; e maximizar resultado confiavel com o minimo de custo e intervencao humana.

## Ordem de preferencia de execucao

1. Ferramenta direta e deterministica.
2. ChatGPT/orquestrador com acesso direto ao repositorio/servico.
3. Agente especializado de baixo custo.
4. Codex somente quando a complexidade justificar.

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

Nunca executar automaticamente no MVP:
- exclusao ou perda potencial de dados de producao;
- deploy de alto impacto em producao;
- criacao de servico pago recorrente sem aprovacao;
- alteracoes sensiveis de autenticacao/permissao que ampliem acesso;
- mudanca material de requisito de produto.
