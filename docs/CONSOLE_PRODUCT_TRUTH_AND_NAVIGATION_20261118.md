# Reconciliação de seis projetos e auditoria de navegação — 18/11/2026

Escopo: trabalho read-only no Supabase Control Plane, GitHub e Vercel. Alterações somente na PR #1516 em dev/Preview. Nenhum merge, produção, migration, execução de modelo ou ampliação de acesso. O último Preview autenticado do responsável foi reprovado, e CI verde não constitui aprovação de UX.

## Fonte de verdade, por projeto

| Projeto | Cadastro e controle | Evidência técnica e lacunas de entrega |
|---|---|---|
| AI Product Factory | implementation, running | 117 tarefas, 126 runs; último run failed_gate; nenhum ativo no snapshot. Vercel produção READY em fc24a857. Certificação independente 19/19 existe para SHA 705e517d, não para toda revisão posterior. Último relatório antigo: product_complete=false. PR #1516 permanece sem merge. |
| CRM Infodive | implementation, running | 87 tarefas, 99 runs; último run integrated, zero ativos. Preview registrado; release report blocked, product_complete=false. Main b1935c8; PRs #213 e #215–218 abertas. |
| Dark Channel Studio | operations, running | 14 tarefas, 16 runs; último run blocked (reparo de segurança). PR #2 mergeada em main=c171912; Vercel produção dpl_BiUHA8 READY nesse SHA. Entretanto o relatório released do Control Plane contém product_complete=false e product_readiness.ready=false. A PR do produto informa falta de configuração de backend hospedado, migration e E2E autenticado real. Não confundir build/deploy com produto pronto. |
| Agente SQL Financeiro | planning, running | 4 tarefas, 2 runs; último completed, nenhum ativo ou release/deploy no Control Plane. Caminho oficial n8n, LangGraph offline shadow e Preview não aplicável. Acesso GitHub cross-repo exige consentimento específico; não executar benchmark de 63 perguntas. |
| Infodive Service Desk | implementation, stopped | 20 tarefas, 22 runs; última falha, um Preview histórico, nenhum release. Projeto independente aposentado, evolução pertence ao CRM. Não reiniciar automaticamente. |
| Factory Wake Canary | discovery, stopped | 0 tarefas/runs, sem repositório, manifesto qa_canary=true. Registro técnico de teste, não produto de cliente. |

Leitura correta dos campos: is_active = cadastro; control running = habilitação, não worker; lifecycle_stage = marco no cadastro; run iniciada com lease vigente = execução observada; deployments = registros de implantação; relatório product_complete, readiness e certificado no SHA exato = evidências de completude, nunca substituídas por merge ou Vercel READY. A posição de fase nunca verifica a conclusão das fases anteriores. Registros ausentes devem ser mostrados como falta de evidência, não como sucesso ou falha comercial. O ambiente de produção externo foi inspecionado no Vercel por metadata; a aplicação privada em execução não foi validada por navegação humana nesta análise.

## Auditoria completa do menu lateral

| Destino | Rota | Tarefa e limitação |
|---|---|---|
| Início | / | Situação real resumida dos produtos e próximo passo; sem painel de logs dominante |
| Projetos | /projects | Consultar, criar e abrir produto; etapa declarada não é avanço comprovado |
| Entregas | /deliveries | Escolher produto e visualizar tarefas no Kanban; pacote encerrado não é release |
| Decisões | /gates | Gates realmente humanos e permissões específicas; falha técnica não cria aprovação |
| Execuções | /runs | Histórico de tentativas técnicas; etapa cadastrada não gera checks verdes |
| Fila de trabalho | /queue | Tarefas aguardando; fila não libera execução |
| Agentes | /agents | Especialistas registrados; existência de agentes não comprova atividade |
| Orquestração | /orchestration | Motor, incidentes e recuperação técnica; não é operação do cliente |
| Avaliações e testes | /evals | Resultados técnicos; ausência de falha não comprova produto completo |
| Implantações | /deployments | Preview e produção registrados; READY de build não comprova app funcional |
| Modelos e custos | /usage | Ledger e quota; não autoriza gasto novo |
| Auditoria | /audit | Trilha durável de eventos; não exige monitoramento cotidiano |
| Configurações | /configuration | Políticas e circuit breakers, não controle da jornada do cliente |
| Operadores | /admin/operators | Gestão de operadores autenticados, nunca criação pública de acesso |

Rotas contextuais: /projects/new é cadastro, não Start automático; /projects/new/review revisa proposta; /projects/[key] evidencia o estado do produto; /projects/[key]/request recebe mudança; /deliveries/[id] mostra pacote; /runs/[id] mostra execução; /decisions redireciona para /gates. Login e unauthorized controlam autenticação.

## Defeitos observados e correção

1. Dark Channel Studio aparecia como Fase 6/6 porque o campo de cadastro era operations, mesmo com produto incompleto. A lógica de evidência agora lê release reports, completude, Preview, deployment e certificado no SHA associado, falhando fechado em ausência ou contradição.
2. O detalhe da execução exibiu nove checks verdes de fases concluídas a partir de um único projeto classificado como operations, embora a execução estivesse bloqueada. A barra agora não mostra certificação fictícia; indica somente marco cadastrado.
3. Início repetia seis fases grandes em cada cartão e enterrava todos os projetos. Agora o resumo é compacto, com status de entrega, condição de execução e próxima ação; o passo a passo está no detalhe.
4. Service Desk aposentado e canary técnico estavam no portfólio do mesmo modo que produtos vivos; agora aparecem separadamente e com explicação.
5. Menu lateral tinha 14 destinos sem finalidade explícita. Foi adicionado subtítulo a todos, orientação de página e diagnóstico como área opcional. Os títulos de avaliação, Preview, agentes e criação foram revistos para não induzir segurança ou prontidão fictícias.
6. Sem alterações de banco ou semântica de runtime; sem custos pagos, auto-merge ou gates forçados.

## Refinamento de mensagem e prioridade de bloqueios

Na tela de um produto com execução técnica bloqueada, a primeira ação deve ser a correção do bloqueio real, seguida da reconciliação de banco e verificação E2E. Ausência de evidência de uso não é rejeição de aceite humano: a interface indica **uso funcional não comprovado** e **entrega não comprovada**, reservando decisões humanas aos gates acionáveis. Teste determinístico cobre a prioridade da execução interrompida e a distinção de aceite.

## Gates de aceite

Concluir testes reais de política em TypeScript, verificação estrutural de todas as 14 rotas, Next build e Chromium/axe desktop-mobile sem violation/incomplete, QA e CI exatos, Preview Vercel READY no mesmo SHA. A prova de browser hospedado que visita o login não valida a sessão privada por dentro. A experiência ainda exige revisão humana autenticada. Somente o usuário pode autorizar o merge que altera produção.
