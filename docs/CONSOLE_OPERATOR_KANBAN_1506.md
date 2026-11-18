# Console orientado a trabalho — jornada e quadro de entregas (#1506)

## Decisão do responsável (18/11/2026)

O responsável rejeitou o Preview anterior da PR #1516 após inspecionar quatro telas autenticadas: não sabia o que deveria fazer, qual botão usar, quais bloqueios exigiam ação ou como acompanhar desenvolvimento. Em seguida, aprovou explicitamente a proposta de **Início → Projetos → Entregas (Kanban) → Decisões**, com ferramentas avançadas preservadas. Não se trata de nova certificação nem de licença para automatizar merge.

## Jobs to be done

| Intenção | Caminho executável | Política |
| --- | --- | --- |
| Tenho uma ideia | Início → Criar produto → `/projects/new` | O usuário fornece objetivo; a Factory só inicia mediante intake e controles vigentes |
| Quero corrigir / melhorar | Início → Melhorar → Projetos → Projeto → Pedir melhoria ou correção | Usa a RPC de continuação idempotente existente; nenhum agente é escolhido manualmente |
| Quero acompanhar | Início → Entregas → filtro por projeto → cartão → projeto/execução | O estado é lido de tarefas, runs e gates do Control Plane |
| Precisa de mim | Início ou Decisões → `/gates` | Exibe apenas gates acionáveis e acesso por projeto; confirmações/release não são automáticas |

## Kanban: apresentação, não autoridade de despacho

O quadro agrupa tarefas por raiz real `factory_tasks.parent_task_id`, preservando as tarefas e execuções vinculadas. Nunca cria tarefas ou novos runs. Leituras server-side usam credenciais privilegiadas **somente no servidor** após `requireConsoleOperator`, sem RLS pública nem efeitos de escrita. O inventário é paginado até um limite verificado; dados incompletos causam erro explícito, não estado vazio.

Seis lanes: **A fazer** (sem atividade comprovada), **Em execução** (run ou tarefa com estado de execução), **Validando** (CI, revisão ou Preview indicados pelo Control Plane), **Aguardando você** (gate realmente acionável), **Bloqueado** (falha técnica, não necessariamente ação humana), **Encerrado** (trabalho técnico concluído ou cancelado). `completed` e `integrated` **não** equivalem a publicação; `preview_ready` **não** libera produção. O conjunto de statuses do último run de cada tarefa prevalece sobre tentativas anteriores para evitar reabrir falhas históricas como atuais.

Tarefas do protocolo de certificação `product-readiness:<digest>` são **rotinas internas**; para não inundar o quadro com dezenas de jobs repetidos, ficam fora da visualização padrão, mas a interface apresenta sua contagem e opção explícita de exibi-las. O histórico permanece integral no Control Plane e na tela de Execuções. Essa categorização se baseia no namespace técnico e não em nomes de clientes ou produtos.

Não há drag-and-drop, edição de status, publicação nem recuperação de run pelo Kanban. Apenas ações já permitidas e links governados. Filtros por projeto modificam somente a leitura da tela.

## Problemas reproduzidos e corrigidos na apresentação

- O badge “1 ação pendente” e o KPI “0 aprovações pendentes” tinham fontes semânticas diferentes. A consulta indicou zero gates humanos pendentes e uma dependência de acesso GitHub para Agente SQL Financeiro. A página inicial agora usa a **mesma combinação de fontes do endpoint de atenção** e discrimina gate versus acesso, com nome do projeto, sem fingir publicação pendente.
- O bloco de falhas históricas com mensagens brutas em inglês dominava a página inicial e redirecionava o usuário à investigação técnica. Essas mensagens deixaram de ser a ação principal e a observabilidade passou para uma seção expansível, sem apagar evidência.
- Selo “ativo” e fase “implementação” pareciam significar trabalho em execução. A apresentação distingue participação no portfólio, etapa registrada e run real.
- As ações para continuar produto agora aparecem antes de diagnósticos: melhorar/corrigir, acompanhar entregas e, quando aplicável, revisar decisão.

## Evidências e bloqueios reais para aceitar a mudança

1. Testes de política TypeScript **executando funções reais** (não só grep), testes de contrato, `validate/test`, `factory-acceptance`, `Console validation` e scanners/QA aplicáveis precisam passar no **SHA exato**.
2. Vercel Preview deve identificar o commit real da PR. Playwright/axe devem verificar rota Início, Projetos, Entregas, Decisões, fluxo de pedido, estados vazios/bloqueados, foco/teclado, mobile e contraste.
3. A pessoa responsável deve revisar **telas internas autenticadas** de desktop e mobile; um login protegido retornando 200 não certifica a experiência interna. A reprovação anterior segue válida até nova revisão.
4. A prova independente de reutilização de evidência autenticada pode falhar quando o bundle externo estiver indisponível; não contornar 500 nem declarar que houve captura. Reconciliar ou capturar via canal oficial e seguro.
5. Merge em `main` publica produção: **sempre gate humano**, independentemente de CI/Preview. Sem auto-merge, API paga para smoke, migration, novas credenciais, bypass de Auth/RLS ou alteração de política.

**Estado deste documento:** descrição do candidato na PR #1516; não é laudo de CI verde, aprovação visual ou certificação automática do SHA.
