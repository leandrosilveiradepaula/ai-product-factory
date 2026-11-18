# Blueprint: Console como central de produtos autonomos

Data: 2026-11-18  
Estado: proposta de arquitetura de informacao e experiencia, **NAO implementada nem aprovada**.  
Escopo: toda a AI Product Factory e todos os projetos do portfolio, sem hardcode por produto.  
Demanda: issue #1506; PR de trabalho #1516. Esta proposta **substitui a direcao de UX anterior como criterio de desenho**, sem apagar evidencias nem autorizar merge.

## 1. Tese e pesquisa

O Console nao deve ser um painel das ferramentas internas. Deve mostrar a entrega dos produtos e a atividade autonoma: o usuario descreve um objetivo, a Factory prossegue automaticamente enquanto e seguro, o Console relata o que aconteceu e so solicita intervencao quando ha gate real.

Referencias oficiais consultadas em 18/11/2026:
- Linear Projects (visao consolidada, propriedades, marco e objetivo): https://linear.app/docs/projects
- Linear Updates (saude, progresso, desafios e proximos passos): https://linear.app/docs/initiative-and-project-updates
- GitLab Value Stream Analytics (duracao de etapas e gargalos de ponta a ponta): https://docs.gitlab.com/user/group/value_stream_analytics/
- GitHub Projects (referencia direta entre issues, PRs e roadmap): https://docs.github.com/en/issues/planning-and-tracking-with-projects
- Vercel Deployments (ambiente, versao, release e evidencias de build): https://vercel.com/docs/deployments
- Atlassian Internal Developer Platform (catalogo unico, integracoes, scorecards): https://www.atlassian.com/developer-experience/internal-developer-platform
- NN/g Visibility of System Status: https://www.nngroup.com/articles/visibility-system-status/
- NN/g Progressive Disclosure: https://www.nngroup.com/articles/progressive-disclosure/
- NN/g Complex Application Design: https://www.nngroup.com/articles/complex-application-design/
- Google Cloud Human-in-the-loop: https://docs.cloud.google.com/architecture/choose-design-pattern-agentic-ai-system

Interpretacao para a Factory: status e progresso devem acompanhar evidencias do produto, nao quantidade de telas, PRs ou tarefas; detalhes tecnicos nao competem com a informacao principal. Indicadores de entrega de software como DORA e duracao de etapas ficam em analise tecnica secundaria, nao como placar de prontidao do cliente.

## 2. Perguntas que a interface precisa responder sem cliques tecnicos

1. Quais produtos existem e quais estao utilizaveis?
2. O que a Factory esta efetivamente fazendo neste momento?
3. O que foi demonstrado (e onde posso abrir/experimentar)?
4. Qual e a proxima entrega verificavel e o que falta para ela?
5. Se algo bloqueou, o que esta acontecendo automaticamente e qual dependencia e real?
6. Existe alguma decisao minha? Qual o impacto, evidencias, projeto e commit exatos?

## 3. Nova arquitetura da informacao

Menu principal, com somente tres destinos:
- **Visao geral**: resumo de portfolio, trabalho verificado, entregas recentes, mudancas desde ultima visita e atencao humana acionavel.
- **Produtos**: lista e detalhe de produtos por necessidade do cliente; controles e tarefas aparecem apenas nos detalhes.
- **Decisoes**: aprovacoes reais, com motivo/impacto/versao/evidencias, e dois comandos somente no momento de decidir.

Uma acao global discreta, **Novo pedido**, inicia intencao; para produto existente, o mesmo fluxo vira pedido de melhoria. Nenhum botao "Prosseguir" apos pedido valido: a Factory continua sem cliques intermediarios enquanto a politica permitir.

**Diagnostico do sistema** (area secundaria e recolhida, acesso conforme papel): execucoes, fila, agentes, orquestracao, testes, ambientes, uso/custo, auditoria, configuracoes e operadores. Preservar rotas existentes para deep links, nao transformar todos os destinos em itens do menu principal.

### Visao geral

Topo: titulo "Sua Factory hoje", data de observacao e estado da sincronizacao. Se nao houver gate, dizer "Nenhuma decisao sua agora" sem alerta artificial. Caso haja gate, um bloco compacto com produto, consequencia e link.

Cada cartao de produto deve conter:
- Nome + objetivo (uma linha), estado do produto (entrega provada/nao provada) e situacao da Factory (trabalhando com lease, aguardando, verificando, bloqueada, parada).
- **Agora**: atividade observada ou "Nenhuma execucao ativa comprovada"; responsavel tecnico/Factory.
- **Ja entregue**: funcionalidade demonstrada e ambiente/candidato com prova; se inexistente, "Uso nao comprovado".
- **Proxima entrega**: marco e criterios de saida; indicar dependencias tecnicas em linguagem humana.
- **Sua acao**: so aparece se houver gate humano realmente pendente; caso contrario, "Nenhuma".
- Ultima observacao de dados, sem afirmar atualizado se cache estiver vencido.

Separar produtos ativos, produtos parados/aposentados e registros tecnicos (canary) sem promover um canary a produto.

### Detalhe de um produto: pagina unica

1. Resposta inicial: "O produto funciona hoje?", "A Factory esta trabalhando?", "O que falta para o proximo marco?".
2. **O que foi solicitado**: objetivo, escopo e requisitos rastreaveis com fonte.
3. **O que ja existe**: codigo, banco/integracoes, autenticação, testes ponta a ponta, Preview, producao e operacao, cada um com evidencia independente e rotulo desconhecido se apropriado.
4. **Linha de entrega**: Entender -> Especificar -> Planejar -> Construir -> Revisar -> Testar -> Preview (ou N/A justificado) -> Decisao humana -> Publicar -> Operar. Mostrar posicao declarada separada de fases comprovadas; nao deixar fases anteriores verdes por heranca do lifecycle_stage.
5. **Agora e a seguir**: uma unica explicacao priorizada pelo bloqueio efetivo e pela dependencia concreta, com dono (Factory, tecnico, operador). Somente gate real permite CTA de aprovacao.
6. **Atualizacoes**: linha do tempo do que mudou, com timestamps e transicoes comprovadas, nao logs brutos.
7. **Detalhes tecnicos** recolhidos: tasks, run ids, GitHub SHA, CI, politica de preview, custos, auditorias, integrações, comandos administrativos de pausa/reinicio.

Em telas pequenas, topo e cards empilhados, com as mesmas respostas; evitar tabelas horizontais como eixo central.

## 4. Contrato de verdade: nao existe um unico "status do projeto"

Exibir dimensoes independentes, calculadas por regras deterministicas:

| Dimensao | Fonte e sinal | Proibicao |
| --- | --- | --- |
| Etapa declarada | lifecycle_stage / Product Spec, com data | Nao usar etapa 6/6 como 100% completo |
| Execucao observada | run iniciada, lease vigente e identidade verificavel | control=running nao significa worker ativo |
| Trabalho tecnico | tarefas/run/PR/CI no SHA | PR mergeada nao significa produto utilizavel |
| Prova funcional | E2E autenticado real + requisitos e aceite versionados | test unitario ou login sozinho nao basta |
| Infraestrutura | vinculo registrado, acesso minimo, schema e ambiente observados | banco nao inventariado != banco inexistente |
| Publicacao | merge humano + ambiente + deployment no SHA + teste hospedado | Vercel READY nao significa app funcional |
| Gate humano | registro pendente e acionavel, vinculado ao alvo correto | falha de worker nao cria gate |
| Integridade/frescor | fonte, observado_em, verificado_em, SHA e validade | evidencias antigas nao certificam novos commits |

A interface precisa diferenciar explicitamente:
- "Comprovado" (fonte/verificacao atual);
- "Registrado, nao validado" (evento declarativo, sem prova independente);
- "Nao comprovado" (sem evidencia suficiente);
- "Nao aplicavel" (politica explicita, com justificativa);
- "Inconsistente/desatualizado" (fonte divergente ou stale).

Nao apresentar percentuais artificiais de produto. Se houver denominador confiavel de requisitos aceitos, ele pode ser mostrado como cobertura de escopo, com denominador e versao — jamais como promessa de produto pronto. Certificado de 19/19 de um SHA da Factory nao se transfere para outro SHA ou para outro produto.

**Regra de prioridade da mensagem**: gate humano real > risco/incident grave > execucao ativa com lease > erro tecnico recuperavel sendo tratado > dependencia de integracao > aguardando fila > pronto comprovado > sem evidencias. Separar claramente o que o operador faz daquilo que o sistema executa autonomamente.

## 5. Experiencia autonoma (nao um conjunto de botoes)

Apos Start/novo pedido valido:
1. Supabase Control Plane registra o evento duravel e o estado do trabalho.
2. Python segue a orquestracao e reconcilia tarefas, GitHub/CI, Preview, testes, gates e release sem "prossiga".
3. O Console consome um read model de situacao por projeto; atualiza automaticamente via eventos/revalidacao periodica resiliente, com horario da observacao e tratamento explicito de dados stale.
4. Um evento material muda a frase de contexto e atualiza a linha do tempo: "Especificacao registrada", "Implementacao em teste", "CI falhou e recuperacao solicitada", "Preview verificado", "Revisao de producao pendente".
5. Falhas tecnicas recuperaveis podem seguir apenas caminhos idempotentes e autorizados; limites de custo, lease, cross-repo e segredos continuam fail-closed.
6. Se a acao requer producao, acesso ampliado, custo novo, migracao irreversivel ou alteracao material de requisito, pausar no gate apropriado, com evidencia e efeito claro da decisao. Nunca auto-merge.
7. Depois de decisao humana registrada, retomar automaticamente pelo mecanismo existente, com observacao da liberacao humana; sem criar run duplicada.

Primeiro mapear os eventos e snapshots ja disponiveis. Nao criar nova tabela, servico, fornecedor pago ou canal de notificacao antes de provar necessidade. Preferir mensagens de interface geradas por templates tipados, sem chamada paga a LLM para resumir status. Operador nao deve receber alerta quando o trabalho tecnicamente pode prosseguir sem ele.

## 6. Sistema visual proposto

Aparencia limpa e profissional, com superficies neutras, contraste AA e espacamento regular. Texto principal de leitura ~16 px; secundaria legivel (nao 8-10 px). Uma unica acao principal contextual por tela. Uso de cor apenas em estados com diferenca operacional significativa; nao colorir "desconhecido" como sucesso. Foco visivel, teclado e alvo de interacao de no minimo 44 px. Retirar a duplicacao do mesmo menu e reduzir longas explicacoes de precaucao: manter prova e detalhes sob demanda.

Microcopy: preferir "A Factory esta verificando testes da versao X" a "worker review_pending". Nunca dizer "operando" quando ha apenas marco cadastrado, ou "aprovacao pendente" quando existe somente falha tecnica. O produto efetivamente demonstrado deve ter link/Preview destacado quando autorizado e verificado.

## 7. Execucao em bloco consolidado (mesma PR #1516, sem mini-PRs cosmeticas)

**A. Modelo e inventario de informacao**
- Reconciliar os seis registros de projeto com GitHub, Control Plane, Supabase e Vercel; separar dados factuais, contradicoes, ausencia de prova e dados historicos.
- Definir contrato de leitura/frescor, prioridades e transicoes com fixtures reais sanitizadas.
- Estabelecer criterios de saida por fase sem inferir conclusao pelo cadastro.

**B. Navegacao e linguagem**
- Substituir menu técnico dominante pelas 3 rotas de uso; preservar profundidade administrativa sem competir pelo foco.
- Redesenhar Visao geral e Produtos com respostas em uma leitura; restaurar orientacao de local/contexto.
- Redesenhar detalhe com linha do tempo de produto e "agora/proximo", entregas verificaveis e explicacoes concisas.

**C. Atualizacao e autonomia**
- Fazer o read model refletir eventos de execucao/CI/Preview/gate sem atualizacao manual; validar reconciliacao idempotente e stale.
- Remover botoes de continuidade que nao deveriam existir; conservar somente Novo pedido, controles de administracao secundarios e gate humano legitimo.
- Se um evento automatico nao existir no runtime, registrar a lacuna e corrigir a integracao real, nunca simular trabalhador ativo.

**D. QA de produto e avaliacao humana**
- Testes de contrato Python/TypeScript e fluxos autenticados em Next/Chromium reais.
- Percorrer os 6 projetos (inclusive parado e registro de teste) e os 5 cenarios: localizar/provar, solicitar melhoria, acompanhar sem clique, compreender erro/autorreparo, aprovar release exato.
- Visual desktop 1440, notebook 1024, mobile 390, axe/teclado, hidratação e tratamento de loading/error/offline.
- Preview READY no SHA exato + checagem de rotas autenticadas; somente entao apresentar uma experiencia para avaliacao humana; merge em main e producao permanecem gate humano.

## 8. Criterios de aceite observaveis

- Em ate uma tela, a pessoa identifica por projeto o que existe, o que esta em andamento, o que falta, e se depende dela.
- Nenhum produto sem E2E e DoD versionados aparece como "concluido" por causa de lifecycle, PR ou deployment.
- Nenhuma falha tecnica se converte em pedido humano de aprovacao.
- O fluxo normal depois do pedido nao exige clique "prosseguir"; cada transicao automatica deixa recibo observavel.
- Contradicoes (banco existente fora do inventario, Preview N/A, build READY sem E2E, lease vencido, certificado em outro SHA) produzem estado nao comprovado / inconsistente com proximo passo correto.
- Links de entregas estao associados a projeto, ambiente, commit e validade; nada inventado.
- As 3 rotas principais e os detalhes preservam acesso teclado/mobile e nao exigem navegar 14 menus para responder a uma pergunta.
- Tela principal e dados tecnicos ficam separados sem perder auditoria, seguranca, budget e recuperacao.
- Criticos de acessibilidade zerados na medicao real; nenhum "incomplete" de axe escondido.
- Mudanca visual material aceita apenas depois de Preview autenticado demonstravel; sem auto-merge.

## 9. Decisao de implementacao

**Nao fazer merge da PR #1516 na forma atual.** O codigo de UX existente pode ser reutilizado onde cumpre este desenho, mas nao deve determinar a arquitetura. Este documento e a base da proxima implementacao consolidada, em vez de novas revisoes cosmeticas de um caso isolado. Prototipo/Preview com tarefas reais e verificacao humana encerram a rodada de design; producao continua protegida.
