# Plano do Projeto - AI Product Factory

## Visao

Construir uma fabrica de desenvolvimento na qual o usuario descreve o produto, responde ao discovery inicial e, a partir dai, a fabrica conduz o desenvolvimento quase autonomamente ate um ambiente validavel.

## Resultado esperado

O usuario deve conseguir iniciar com algo como:

> Quero um sistema que faca X.

A fabrica conduz o discovery, cria a especificacao, decompoe o trabalho, implementa, testa, publica preview e interrompe somente quando houver uma decisao humana real ou um gate de risco.

## Fases

### F0 - Fundacao
- [x] Arquitetura inicial.
- [x] Project Manifest.
- [x] State machine.
- [x] Codex Policy Engine.
- [x] Human Gate Policy.
- [x] Schema inicial do control plane.
- [x] Prompts dos papeis.
- [x] Testes unitarios do nucleo.

### F1 - Control Plane
- [x] Criar repositorio `ai-product-factory`.
- [x] Publicar scaffold.
- [ ] Provisionar/selecionar Supabase dedicado.
- [ ] Aplicar schema.
- [ ] Implementar persistencia de projects/tasks/runs/decisions.
- [ ] Registrar consumo de ferramentas e Codex.

### F2 - GitHub Autonomous Loop
- [ ] Adapter GitHub real.
- [ ] Criar/ler issues.
- [ ] Criar branch de trabalho.
- [ ] Persistir plano tecnico.
- [ ] Criar commits e PR.
- [ ] Ler CI e retornar para correcao quando necessario.

### F3 - Runtime de Desenvolvimento
- [ ] Executor direto para mudancas pequenas/medias.
- [ ] Roteador para tarefas especializadas.
- [ ] Integracao seletiva com Codex quando disponivel.
- [ ] Budget/usage ledger de Codex.
- [ ] Review automatico.

### F4 - Testes, Evals e Preview
- [ ] Padrao de testes por projeto.
- [ ] Padrao de evals de agentes.
- [ ] Adapter Vercel Preview.
- [ ] Adapter Supabase DEV.
- [ ] Evidencias automaticas no PR.

### F5 - Piloto Agente SQL Financeiro
- [ ] Onboarding de `agente-sql-langgraph`.
- [ ] Importar comandos reais de teste/deploy.
- [ ] Conectar benchmark de 63 perguntas.
- [ ] Definir baseline.
- [ ] Executar primeira tarefa real de ponta a ponta.

### F6 - Greenfield Test
- [ ] Criar um produto pequeno do zero somente via factory.
- [ ] Medir intervencoes humanas.
- [ ] Medir tarefas diretas vs. Codex.
- [ ] Revisar gates e ampliar autonomia.

## Metricas do projeto

- percentual de tarefas concluidas sem intervencao humana;
- percentual de tarefas que realmente usaram Codex;
- taxa de sucesso de CI na primeira tentativa;
- numero de regressões detectadas antes do merge;
- tempo entre requisito aprovado e preview;
- custo por run / por tarefa quando mensuravel;
- quantidade de gates humanos realmente necessarios.
