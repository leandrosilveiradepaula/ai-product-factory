# Verificação operacional independente — Dark Channel Studio
Data: 18/11/2026 · inspeção somente leitura · **não é certificado de release**

## Resposta direta

**Não há evidência de que alguém consiga usar o Dark Channel Studio em produção hoje.** Há código integrado e um deployment Vercel READY, mas a aplicação não tem uma jornada completa verificada com conta autenticada. O banco dedicado **existe e tem schema aplicado**, contrariando a impressão de "sem banco", porém está **sem usuários, organização ou qualquer projeto editorial real**. A Factory ainda não o vinculou a seu inventário de bancos.

A inspeção não utilizou credenciais em browser, não abriu conta, não fez INSERT, não aplicou migration, não gastou API e não publicou nada.

## Evidências verificadas diretamente

| Pergunta | Observação real | Limite da afirmação |
|---|---|---|
| Existe banco dedicado? | Supabase projeto "Dark Channel Studio - Factory Pilot", ref nsmnmcjzprovxfxkhwxt, ACTIVE_HEALTHY, PostgreSQL 17.11. | A existência do projeto não comprova que Vercel aponte para esse ref. |
| O schema foi instalado? | Oito tabelas studio_*, incluindo organizations, memberships, channels, profiles, projects, documents, review_decisions e audit_events. 18 políticas RLS, todas as oito tabelas com RLS e FORCE RLS. Funções studio_submit_project, studio_complete_review, studio_documents_complete, studio_protect_project_stage, studio_record_project_audit e gatilhos de auditoria/transição existem. | É prova estrutural, não execução funcional. |
| Histórico da migration | supabase_migrations.schema_migrations contém versão 20261117125532. O arquivo versionado do repositório possui prefixo 20261116132000. | O prefixo diferente exige cotejar o conteúdo e sua proveniência antes de afirmar equivalência de migração. Não executar segunda aplicação presumindo ausência. |
| Existem dados de uso? | auth.users=0, studio_organizations=0, studio_memberships=0, studio_channels=0, studio_profiles=0, studio_projects=0, studio_documents=0, studio_review_decisions=0, studio_audit_events=0. | Sem bootstrap/identidade, E2E real autenticado não está provado. A criação de acesso é gate sensível, não tarefa de inventar usuários silenciosamente. |
| Vercel produção? | Projeto dark-channel-studio, deployment dpl_BiUHA8gjB221KHMyU8iRByuCcyrd, READY em main SHA c1719129eaa5b2d7ae3f4afffa1bb70a7d502973. Variáveis com nomes SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, STUDIO_SESSION_KEY, STUDIO_ORIGIN existem em Production; valores **não** foram lidos ou exibidos. | READY é build/deployment, não prova de HTTP funcional, sessão real, schema alvo ou fluxo de uso. A tentativa de alcançar /health no ambiente desta análise falhou por DNS/restrição de rede; não atribuir isso à aplicação. |
| Factory reconhece a conexão? | Zero linhas em factory_project_databases para dark-channel-studio. O cadastro tem lifecycle_stage=operations e controlState=running; isto não é operação nem worker. | O frontend antigo ocultava a seção de banco quando não havia vinculação, impedindo o operador de ver o problema. |
| Escopo de produto? | Issue original da Factory #1414 exige workspace multicanal, briefing/fontes, roteiro versionado, SRT, storyboard, prompts separados [i]/[v] com regras IV, revisão, exportações e operação. Factory tem 57 requisitos ativos com relações e evidências predominantemente CI/QA em SHA anterior. O latest Product Spec v2 no Control Plane é candidate e contém texto de descoberta genérico sem funcionalidades definidas. | A especificação candidata genérica é inconsistente com a issue já aprovada e o código. Corrigir fonte/linhagem, não inventar requisitos nem contar como produto completo. |
| Tarefa atual de reparo? | Repair security findings - cycle 2, status blocked. A run reporta: AGENTS.md autoritativo ausente no contexto do SHA exato. O repositório do Studio em main não contém AGENTS.md. | Antes de retomar, determinar qual arquivo é obrigatório pela política/handoff e obter sua fonte autenticada; não adivinhar nem alterar migration às cegas. |
| Release report | A Factory marcou released após merge humano, mas report.product_complete=false, product_readiness.ready=false; última auditoria global not_assessed. | A UI não deve anunciar fase 6/6 como êxito ou produto entregue. |
| Browser real | CI contém testes unitários de domínio, HTTP e PostgreSQL efêmero; há prova hospedada de login/fundação em branch. | Não equivale a um usuário real criando, revisando e exportando um vídeo na Production. |

## Plano concreto para destravar, preservando gates

1. **Reconciliar conexão:** registrar na Factory o vínculo do banco Studio existente através do fluxo autorizado (sem duplicar projeto), validar sua identidade e migração aplicada. Nenhum SQL de escrita deve ser executado apenas por esta verificação.
2. **Preparar acesso funcional de teste com gate adequado:** identidade de teste, organização, membership e RBAC com perfil mínimo. O banco está vazio. Se a criação for no ambiente de produção ou ampliar acesso, o proprietário aprova.
3. **Corrigir o reparo de segurança:** recuperar instruções exatas AGENTS.md requeridas pela run ou esclarecer origem caso o Studio não possua o arquivo; reconciliar contexto de trabalho sem reabrir Change Sets terminais.
4. **Verificar E2E na aplicação hospedada:** login, cadastro de canal e projeto, roteiro, SRT, mapa de cenas e referências, prompts IV [i]/[v], revisão, aprovação e exportações. Capturar evidência durável da mesma versão/ambiente.
5. **Auditar cobertura da issue #1414:** confrontar 57 requisitos, especificação candidata desatualizada e funções reais; corrigir o que faltar. Só depois avaliar DoD de produto, liberar gate humano para produção quando cabível e observar release.

## Correção na interface da Factory — PR #1516

A interface antiga concentrava frases defensivas, seis "fases" e logs, mas escondia dados decisivos. A revisão desta PR:
- abre com diagnóstico curto de entrega, não ciclo teórico;
- exibe **código, banco vinculado no inventário, aceite de uso e requisitos** como dimensões independentes;
- exibe próximos trabalhos ordenados e causa específica da run sem reproduzir texto bruto inseguro;
- sempre mostra a seção de banco, mesmo que não exista vínculo na Factory;
- mantém fases, logs e custos dentro de detalhes expandidos sob demanda;
- funciona genericamente para qualquer projeto, sem hardcode do Studio, SHA, credenciais ou resultados da auditoria no frontend.

**Limitação explícita:** enquanto não houver vínculo/recebimento auditado na própria Factory, o Console só pode dizer "banco não registrado na Factory". O relatório desta data confirma externamente que há banco e schema. Não mentir dizendo "não há banco" nem "banco integrado". A auditoria pontual fica aqui como evidência com data, não como indicador em tempo real.
