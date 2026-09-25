# Politica de Uso do Codex

## Principio

Codex e capacidade premium. Deve ser utilizado onde o ganho marginal e alto.

## Nivel 0 - Nao usar
Planejamento, PRD, documentacao, operacoes simples, consultas, configuracoes triviais.

## Nivel 1 - Evitar
Alteracao pequena/localizada, uma ou poucas funcoes, baixo risco e contexto claro.

## Nivel 2 - Permitido se necessario
Modulo novo de complexidade media ou alteracao multifile moderada. Preferir execucao direta primeiro.

## Nivel 3 - Recomendado
Refatoracao ampla, debug profundo, mudanca com muitas dependencias ou varios ciclos de implementacao/teste.

## Nivel 4 - Essencial/especializado
Migracao arquitetural extensa, investigacao muito ampla ou tarefa que o executor direto nao consegue realizar com confianca.

## Regras

- estrategia padrao: `conservative`;
- minimo para acionar Codex automaticamente: nivel 3;
- no maximo uma chamada de Codex por tarefa no MVP, salvo aprovacao explicita;
- contexto deve ser pre-processado antes: objetivo, arquivos, restricoes e criterios de aceite;
- se Codex estiver indisponivel, outras tarefas devem continuar;
- toda utilizacao deve gerar evento de auditoria e, quando mensuravel, custo/uso.
