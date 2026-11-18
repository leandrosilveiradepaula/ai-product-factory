# Auditoria UX/UI do Console — solicitação #1506

- **SHA inspecionado:** `a6733c1d27a422769da7869b1c4121ae0b93786d`
- **Solicitação:** UX/UI #1506
- **Escopo da auditoria:** Console autenticado da Factory, a partir dos arquivos-fonte disponibilizados neste Change Set.
- **Natureza:** auditoria versionada de fonte; não altera rotas, código de produção, permissões, dados, banco, workflows, configurações de release ou comportamento operacional.
- **Estado de prontidão:** esta auditoria não declara `product_ready`, `release_candidate_ready` nem prontidão global do produto.

## 1. Limites, método e classes de evidência

### 1.1 Método

A inspeção foi estática e limitada ao conteúdo fornecido para o SHA acima, em especial:

- `apps/console/app/nav.tsx`;
- `apps/console/app/page.tsx`;
- `apps/console/app/theme.css`;
- `apps/console/app/globals.css`;
- governança registrada em `AGENTS.md`.

As conclusões distinguem observação verificável no código de interpretação de UX. Onde a rota, o componente ou o comportamento não pôde ser confirmado pela fonte disponibilizada, o relatório registra a lacuna em vez de inferir resultado.

### 1.2 Classes de evidência

| Classe | Significado neste relatório |
| --- | --- |
| **Fato de fonte** | Observação diretamente verificável nos arquivos inspecionados no SHA indicado. |
| **Hipótese de UX** | Interpretação de impacto, compreensibilidade ou comportamento esperado; precisa de validação com pessoas e/ou navegador. |
| **Evidência histórica** | Informação presente em comentários, notas ou governança histórica; não é confirmação do estado em execução neste SHA. |
| **Evidência indisponível** | Dado necessário para concluir uma afirmação que não foi fornecido no pacote de inspeção. |

### 1.3 Limitações explícitas

**Evidência indisponível:** não foi fornecida evidência de navegador, screenshots, pesquisa com usuários, telemetria, CI, Preview, execução de testes de acessibilidade, validação responsiva ou validação externa para o SHA `a6733c1d27a422769da7869b1c4121ae0b93786d`.

Consequentemente:

- não foi possível confirmar renderização real, carregamento, estados de erro, foco, leitura por tecnologias assistivas, contraste calculado, alvo de toque ou ausência de overflow;
- não foi possível confirmar que as consultas ao Control Plane retornam os dados esperados em uma sessão autenticada;
- não foi possível medir descoberta de rotas, taxa de conclusão, tempo de decisão, erros operacionais ou satisfação;
- menções no CSS a auditorias, Figma, Playwright, axe-core ou execuções anteriores são **evidência histórica**, não prova atual para este SHA;
- uma auditoria de fonte não substitui teste real de navegador, revisão humana de design ou avaliação global de prontidão do produto.

## 2. Inventário da arquitetura de informação observada

### 2.1 Destinos primários

**Fato de fonte:** `ConsoleNav` define três destinos em `primaryItems`, sob o grupo **“Seu trabalho”**:

| Destino | Rota | Papel operacional observado |
| --- | --- | --- |
| Visão geral | `/` | Página inicial para projetos, decisões humanas, ocorrências e atividade técnica divulgável. |
| Projetos | `/projects` | Portfólio e entrada para acompanhar o ciclo de cada produto. |
| Aprovações | `/gates` | Decisões humanas pendentes e seus motivos. |

**Fato de fonte:** o item “Aprovações” pode exibir contagem de atenção humana (`attentionCount`) quando há itens positivos.

**Hipótese de UX:** a redução da navegação de primeiro nível para trabalho, projetos e aprovações favorece uma orientação inicial baseada em intenção: acompanhar, localizar produto ou decidir. A adequação dessa taxonomia precisa ser validada com operadores reais.

### 2.2 Ferramentas avançadas

**Fato de fonte:** o restante da navegação está agrupado em um `<details>` denominado **“Ferramentas avançadas”**, aberto automaticamente quando a rota atual pertence a esse conjunto.

| Grupo observado | Destinos |
| --- | --- |
| Acompanhar execução | Execuções (`/runs`), Fila de trabalho (`/queue`), Agentes (`/agents`), Orquestração (`/orchestration`) |
| Qualidade e entrega | Avaliações e testes (`/evals`), Implantações (`/deployments`) |
| Administração | Modelos e custos (`/usage`), Auditoria (`/audit`), Configurações (`/configuration`), Operadores (`/admin/operators`) |

**Fato de fonte:** cada `Link` da navegação usa `prefetch={false}`; o comentário no código atribui isso à necessidade de evitar prefetch especulativo de páginas autenticadas e assegurar transição iniciada pelo usuário.

**Hipótese de UX:** o agrupamento reduz concorrência visual na navegação inicial, mas pode diminuir encontrabilidade de itens usados com frequência por especialistas, como Execuções e Auditoria. A decisão depende de frequência de uso e perfis de operador, dados indisponíveis nesta auditoria.

### 2.3 Página inicial

**Fato de fonte:** `Home` busca em paralelo dados de dashboard, saúde operacional, uso, gates humanos, execuções e auditoria.

**Fato de fonte:** a página tem uma lógica explícita de “onde começar”, em ordem:

1. aprovações acionáveis pendentes;
2. ocorrências operacionais;
3. criação/importação do primeiro projeto quando não há projetos;
4. acompanhamento de projetos quando o portfólio existe.

**Fato de fonte:** a página inicial apresenta, em seguida:

- seção “Seus projetos”, limitada aos quatro primeiros projetos;
- resumo operacional com projetos, execuções, aprovações pendentes e falhas/fila de erro;
- seção “Acompanhamento de atenção” para gates acionáveis e incidentes recentes;
- detalhes técnicos recolhíveis para custos, eventos, Codex, custo desconhecido, fila e leases;
- atividade técnica recente recolhível, incluindo execuções e auditoria.

**Hipótese de UX:** a ordem favorece ação humana excepcional antes de telemetria técnica. Isso é apropriado para operação orientada a exceções, desde que os títulos e a distinção entre “pendente”, “acionável”, “histórico” e “incidente” sejam compreendidos pelos operadores.

### 2.4 Hierarquia de atenção operacional

**Fato de fonte:** somente gates com `status === "pending"` e `actionable` são tratados como decisões que exigem intervenção (`requiresDecision`). O comentário afirma que linhas históricas ou substituídas não são ações do operador.

**Fato de fonte:** incidentes aparecem após decisões pendentes; a página restringe incidentes a dois e execuções/auditoria recentes a oito itens.

**Fato de fonte:** o estado sem itens chama explicitamente a atenção para a ausência de “decisão humana acionável ou ocorrência recente” e informa que demais bloqueios continuam nas telas de projeto.

**Hipótese de UX:** a hierarquia evita que ruído histórico concorra com decisões reais. Há risco residual de interpretação excessiva do estado calmo como “tudo está saudável”, apesar do texto limitar a afirmação à consulta atual.

**Evidência indisponível:** não há sessão real, dados reais do Control Plane, telemetria ou observação de tarefas para confirmar se a priorização corresponde ao impacto operacional efetivo.

## 3. Achados priorizados

A prioridade considera impacto operacional potencial, não uma métrica observada de uso. “Confiança” expressa a confiança na leitura da fonte, não validação de usuários.

### P0 — Preservar a distinção entre decisão humana acionável e histórico

- **Classe de evidência:** Fato de fonte + hipótese de UX.
- **Fonte/áreas afetadas:** `apps/console/app/page.tsx`; rotas `/` e `/gates`.
- **Observação:** a página inicial filtra gates por `pending && actionable`, chama-os de “decisões pendentes” e afirma que registros históricos ou substituídos não são ação do operador.
- **Impacto esperado:** alto. Misturar pendências históricas, bloqueios técnicos e decisões reais poderia induzir aprovações erradas, fadiga de alerta ou perda de contexto de governança.
- **Confiança:** alta para a implementação observada; média para o benefício em uso real.
- **Risco de regressão:** alto se uma reformulação tratar todos os statuses como equivalentes ou ocultar razões, projeto, tarefa e execução associada.
- **Recomendação:** manter uma camada de atenção separada para decisões humanas acionáveis, exibir motivo suficiente antes de decidir e preservar acesso à execução relacionada. Não introduzir linguagem que sugira que o operador deve aprovar sem revisar evidências.

### P0 — Não converter indicadores de atividade em afirmação de prontidão

- **Classe de evidência:** Fato de fonte + evidência histórica.
- **Fonte/áreas afetadas:** `page.tsx`, textos de saúde operacional e `AGENTS.md`.
- **Observação:** a página já informa que valores do Control Plane não são prova de execução em tempo real. A governança proíbe inferir `product_ready` de CI, Preview, PR, fluxo parcial ou ausência de issues.
- **Impacto esperado:** alto. A linguagem de interface pode influenciar decisões de release e confiança indevida.
- **Confiança:** alta.
- **Risco de regressão:** alto se badges como “verde”, “sem incidentes” ou “completo” passarem a significar prontidão global ou autorização de merge/release.
- **Recomendação:** preservar qualificadores de escopo (“nesta consulta”, “registro observado”, “não prova execução em tempo real”) e usar a taxonomia de governança: `work_item_complete`, `release_candidate_ready`, `release_completed`, `product_ready` e estados `not_assessed`/`not_ready` quando aplicável.

### P1 — Explicitar progressivamente ferramentas avançadas sem reduzir acesso de especialistas

- **Classe de evidência:** Fato de fonte + hipótese de UX.
- **Fonte/áreas afetadas:** `apps/console/app/nav.tsx`, estilos `.navAdvanced` em `globals.css`.
- **Observação:** ferramentas técnicas são recolhidas sob “Ferramentas avançadas”, mas a seção abre quando uma rota interna está ativa e mostra “Você está aqui”.
- **Impacto esperado:** médio a alto. Pode melhorar foco do operador ocasional e, simultaneamente, criar um passo extra para especialistas.
- **Confiança:** alta para o comportamento definido; baixa a média para a adequação por perfil, sem dados de uso.
- **Risco de regressão:** médio. Reordenar ou esconder rotas pode prejudicar descoberta, atalhos mentais e suporte operacional.
- **Recomendação:** preservar URLs e rótulos estáveis; validar com pelo menos operadores iniciantes e especialistas se “Execuções”, “Fila” e “Auditoria” devem permanecer recolhidas, receber atalhos contextuais ou ser promovidas em contextos de incidente.

### P1 — Tornar a orientação da página inicial verificável em navegador

- **Classe de evidência:** Fato de fonte + evidência indisponível.
- **Fonte/áreas afetadas:** `apps/console/app/page.tsx`, `.homeFocus`, `.homeSummary`, `.homeAttention` em `globals.css`.
- **Observação:** a fonte define uma área inicial destacada, cards de projeto, resumo e seções técnicas recolhíveis. A ordem visual real, o foco inicial e o comportamento de quebra não foram observados.
- **Impacto esperado:** médio a alto. A primeira tela determina se o operador encontra a próxima ação sem varrer indicadores secundários.
- **Confiança:** alta sobre a intenção do código; baixa sobre a experiência entregue.
- **Risco de regressão:** médio. Alterações de espaçamento, breakpoint ou conteúdo podem fazer a ação prioritária ficar abaixo da dobra ou competir com cards técnicos.
- **Recomendação:** validar em navegador autenticado em larguras móvel, tablet e desktop; testar estados com gate acionável, incidente, portfólio vazio e portfólio populado.

### P1 — Manter detalhes técnicos divulgáveis, legíveis e acessíveis

- **Classe de evidência:** Fato de fonte + hipótese de UX.
- **Fonte/áreas afetadas:** `page.tsx`; `.technicalDetails`, `.overviewActivityDetails`, tabelas e media queries em `globals.css`.
- **Observação:** custos, auditoria e atividade técnica recente estão dentro de elementos `<details>`. O CSS contém múltiplas regras de foco visível, redução de movimento e ajustes responsivos.
- **Impacto esperado:** médio. A divulgação progressiva reduz carga cognitiva para o fluxo diário, mas não deve tornar diagnóstico crítico difícil de alcançar.
- **Confiança:** média. A estrutura de fonte é favorável, mas acessibilidade e responsividade reais não foram executadas.
- **Risco de regressão:** médio a alto em teclado, leitor de tela e dispositivos estreitos, especialmente com tabelas e conteúdo de execução longo.
- **Recomendação:** conservar semântica nativa de `<details>/<summary>`, testar ordem de tabulação e foco, conferir nomes acessíveis e assegurar que tabelas tenham alternativa compreensível em tela estreita sem remover dados.

### P2 — Revisar densidade e consistência do sistema visual

- **Classe de evidência:** Fato de fonte + hipótese de UX + evidência histórica.
- **Fonte/áreas afetadas:** `theme.css` e `globals.css`.
- **Observação:** os estilos definem tokens de cor, tipografia, espaçamento, estados de foco e numerosos refinamentos específicos. Comentários citam passagens anteriores de “fidelity”, “audit”, Chromium e axe-core.
- **Impacto esperado:** médio. Um sistema consistente facilita escaneamento, mas sucessivas sobreposições de CSS podem aumentar custo de manutenção e gerar diferenças entre rotas/breakpoints.
- **Confiança:** alta sobre a densidade de regras; média sobre efeito visual, pois não há screenshots nem navegador.
- **Risco de regressão:** médio. Consolidar tokens ou regras sem verificação visual pode alterar contraste, tamanhos de alvo, overflow ou hierarquia.
- **Recomendação:** em uma fatia futura, inventariar componentes e tokens efetivamente usados, reduzir duplicações somente após regressão visual por rota e manter testes de contraste, foco e tamanho de alvo.

## 4. Arquitetura de informação proposta

A proposta preserva todas as funcionalidades e não recomenda remover rotas, autenticação, controles de segurança, dados do Control Plane, gates humanos ou o marco de certificação 19/19.

### 4.1 Modelo de três camadas

| Camada | Objetivo | Conteúdo recomendado | Regra de segurança/operabilidade |
| --- | --- | --- | --- |
| **1. Operar agora** | Permitir ação humana correta no menor número de passos. | Visão geral, Projetos, Aprovações; próximo passo, decisões acionáveis, incidentes contextualizados. | Nunca transformar alerta em autorização automática; decisões continuam humanas e auditáveis. |
| **2. Investigar execução** | Diagnosticar um projeto, run ou bloqueio. | Execuções, Fila, Agentes, Orquestração, links contextuais de projeto/run. | Preservar proveniência, SHA, estado, motivos e fences de geração; não iniciar/repetir trabalho por mera navegação. |
| **3. Governar e comprovar** | Examinar qualidade, entrega, custo, auditoria e configuração. | Avaliações, Implantações, Modelos e custos, Auditoria, Configurações, Operadores. | Exibir evidência como evidência; não inferir release, produção ou prontidão global. |

### 4.2 Home proposta: narrativa operacional

1. **Cabeçalho:** onde o operador está e qual é o escopo da consulta.
2. **Próxima ação:** uma ação principal, apenas quando houver decisão humana acionável, ocorrência relevante ou início de projeto.
3. **Projetos:** carteira como objeto central de trabalho, com etapa observada e ligação para detalhes.
4. **Atenção operacional:** decisões humanas primeiro; incidentes em seguida; estado calmo explicitamente limitado à consulta.
5. **Diagnóstico sob demanda:** custos, eventos e atividade técnica em divulgações progressivas.

**Hipótese de UX:** esse encadeamento atende tanto o operador que precisa agir imediatamente quanto quem precisa acompanhar portfólio, sem retirar rotas de diagnóstico.

### 4.3 Princípios de redesign

- **Preservar semântica operacional:** “pendente” não é sinônimo de “acionável”; “sem ocorrência recente” não é sinônimo de saudável ou pronto.
- **Mostrar o porquê antes do controle:** gate humano deve incluir motivo, projeto, tarefa/run relacionada e consequências observáveis antes do botão de decisão.
- **Usar divulgação progressiva para complexidade, não para ocultar evidência:** detalhes técnicos devem continuar alcançáveis por teclado, URL estável e links contextuais.
- **Manter estabilidade para especialistas:** não deslocar Execuções, Fila, Auditoria ou Configurações sem pesquisa e validação de tarefas reais.
- **Proteger controles de alto impacto:** nenhum redesign deve relaxar autenticação, RBAC/RLS, proveniência, gates humanos, regras de merge/release, políticas de custo ou constraints de produção.
- **Separar estado de produto de estado de interface:** o Console pode explicar evidências sem declarar o produto pronto.

## 5. Recomendações de conteúdo e interação

### 5.1 Linguagem de estados

| Situação | Formulação recomendada | Formulação a evitar |
| --- | --- | --- |
| Gate humano | “Decisão humana necessária para continuar” | “Aprovar para concluir” sem contexto |
| Sem gate acionável | “Nenhuma decisão humana acionável encontrada nesta consulta” | “Tudo resolvido” |
| Saúde operacional | “Ocorrência registrada; investigar evidência” | “Sistema saudável” sem escopo e período |
| Evidência técnica | “Registro observado no Control Plane” | “Comprovado em produção” sem prova correspondente |
| Prontidão | “Não avaliado” / “não pronto” quando faltar auditoria global | “Pronto” derivado de CI, Preview ou atividade |

### 5.2 Padrões de interação a preservar ou validar

- **Fato de fonte:** os links de navegação autenticada não usam prefetch especulativo.
- **Recomendação:** conservar essa proteção até que uma decisão técnica e de segurança específica aprove outra estratégia de carregamento.
- **Fato de fonte:** há regras para foco visível e `prefers-reduced-motion`.
- **Recomendação:** preservar esses requisitos em componentes novos e validar o resultado em navegador, não apenas por inspeção de CSS.
- **Hipótese de UX:** badges de contagem para atenção humana ajudam triagem quando acompanham rótulo textual e não são a única indicação de estado.
- **Recomendação:** testar leitores de tela, zoom e alto contraste; não confiar em cor, ícone ou posição como único canal.

## 6. Plano de implementação fatiado

Nenhuma fatia abaixo está autorizada por este relatório a alterar produção, permissões, dados, workflows, release ou comportamento operacional. Cada uma exige reconciliação da governança vigente, escopo explícito e evidência correspondente.

### Fatia A — Baseline de pesquisa e tarefas operacionais

- **Objetivo:** confirmar perfis, tarefas, vocabulário e frequência de uso de destinos primários e avançados.
- **Mudanças potenciais:** nenhuma antes da pesquisa; somente documentação de cenários e critérios de êxito.
- **Validação exigida:** pesquisa com operadores, revisão humana de design e decisão posterior sobre prioridades de navegação.
- **Não comprovado por esta auditoria:** perfis de usuário, frequência de Execuções/Auditoria, compreensão de “acionável”, e adequação dos rótulos.

### Fatia B — Validação de navegação e hierarquia em navegador

- **Objetivo:** verificar o fluxo “visão geral → próxima ação → projeto/gate/run” em sessão autenticada.
- **Mudanças potenciais:** ajustes de rótulo, ordem visual, atalhos contextuais ou divulgação progressiva, preservando URLs e todas as rotas existentes.
- **Validação exigida:** navegador no SHA candidato, screenshots comparáveis, teclado, foco, estados sem dados/com dados e testes em desktop/tablet/mobile.
- **Gate necessário:** Preview vinculado ao SHA exato quando aplicável; nenhuma inferência por SHA isolado.

### Fatia C — Acessibilidade e responsividade

- **Objetivo:** confirmar que os padrões observados em fonte funcionam na interface renderizada.
- **Mudanças potenciais:** semântica de tabelas, labels, ordem de foco, tamanho de alvo, contraste, comportamento de `<details>`, overflow e layouts estreitos.
- **Validação exigida:** testes automatizados de acessibilidade em navegador, inspeção manual com teclado, leitor de tela quando disponível, zoom e breakpoints responsivos.
- **Gate necessário:** CI e evidência de browser/Preview no SHA exato; falhas de infraestrutura, permissão, quota ou evidência desconhecida devem bloquear reparo especulativo.

### Fatia D — Consolidação do sistema visual

- **Objetivo:** reduzir sobreposição de regras e manter tokens coerentes sem degradar superfícies existentes.
- **Mudanças potenciais:** racionalização incremental de CSS e componentes visuais compartilhados.
- **Validação exigida:** regressão visual por rota, contraste calculado, testes de foco e responsividade; Preview do SHA exato.
- **Risco:** alto risco de regressão transversal; deve ser fatiada por componente ou padrão, não como reescrita ampla.

### Fatia E — Instrumentação e avaliação de eficácia

- **Objetivo:** avaliar se a IA proposta melhora descoberta, tempo para decisão e diagnóstico sem coletar dados indevidos.
- **Mudanças potenciais:** somente após desenho de telemetria minimizada e revisão de privacidade/segurança.
- **Validação exigida:** decisão humana posterior sobre finalidade, retenção, acesso, custo e dados coletados; nenhuma telemetria deve ser introduzida para contornar consentimento ou controles existentes.

### Fatia F — Governança de estados e conteúdo

- **Objetivo:** padronizar textos de evidência, prontidão, incidente, decisão e histórico entre rotas.
- **Mudanças potenciais:** cópia e componentes de estado, sem mudar critérios de autorização ou regras de negócio.
- **Validação exigida:** revisão humana de conteúdo operacional e segurança; testes de regressão que assegurem que a interface não sugira merge, release, migration ou chamada paga como ação automática.
- **Preservação obrigatória:** autenticação, segurança, dados do Control Plane, gates humanos e o marco 19/19.

## 7. Matriz de evidência por conclusão

| Conclusão | Classe | Confiança | Evidência ausente para confirmação plena |
| --- | --- | --- | --- |
| Há três destinos de trabalho primários. | Fato de fonte | Alta | Nenhuma para existência; uso real indisponível. |
| Ferramentas técnicas estão agrupadas em divulgação progressiva. | Fato de fonte | Alta | Descoberta e frequência de uso em pessoas reais. |
| A home prioriza gates acionáveis antes de incidentes e portfólio. | Fato de fonte | Alta | Renderização, dados reais e adequação operacional. |
| A hierarquia reduz carga cognitiva para operadores. | Hipótese de UX | Média | Pesquisa, testes de tarefa e telemetria ética. |
| Foco, contraste e responsividade estão conformes. | Evidência indisponível | Não aplicável | Browser, scanner a11y, revisão manual e dispositivos reais. |
| Comentários sobre Figma, Playwright, Chromium ou axe representam validação atual. | Evidência histórica, não confirmação atual | Baixa para estado atual | Run, artifact e Preview ligados ao SHA exato. |
| O Console ou produto está pronto para produção. | Evidência indisponível | Não aplicável | Auditoria global independente, durável, atual e íntegra dos domínios exigidos. |

## 8. Conclusão

A fonte inspecionada descreve um Console que procura concentrar o trabalho diário em projetos, decisões humanas e exceções operacionais, deixando ferramentas diagnósticas acessíveis por divulgação progressiva. A principal força observada é a separação explícita entre uma decisão humana acionável e registros históricos ou técnicos. O principal risco de UX e governança é perder essa distinção em futuras simplificações visuais e transformar indicadores parciais em sinais indevidos de prontidão.

Este documento é evidência de auditoria de fonte para a solicitação UX/UI #1506 e para o SHA `a6733c1d27a422769da7869b1c4121ae0b93786d`. Ele não substitui teste de navegador, testes de acessibilidade, validação responsiva, Preview de SHA exato, pesquisa com usuários, CI, revisão humana de design, avaliação externa ou auditoria global de prontidão do produto.
