# Fencing de geração nos followups da Factory

**Status:** código candidato, não equivale a release ou produto globalmente pronto.
**Escopo:** CI, Preview e avaliações Specialist de runs roteadas Direct/Codex;
observação de merge humano sem replay de claims antigas.

## O defeito observado

O comando humano `pause` bloqueia novas claims. Ao executar
`resume`, `factory_project_execution_controls.generation` aumenta.
No runtime anterior, o followup de uma run antiga checava apenas o
estado `running`, permitindo que um candidato CI/Preview ou Specialist
de uma geração anterior fosse processado após a retomada.

A prova de geração já existe em
`factory_runs.metadata.execution_generation` e é preenchida pelas
claims `factory_claim_next_agent_direct_run` /
`factory_claim_next_agent_codex_run`. O RPC
`factory_assert_project_execution_epoch(uuid,bigint)` já existe em
produção e foi confirmado como **SECURITY INVOKER**, com EXECUTE
para `service_role` e sem EXECUTE para `anon/authenticated`.
Nenhum DDL novo é necessário.

## Contrato de um novo efeito externo

1. Ler o item com `project_id`, `execution_route` e metadados da
   claim. `direct/codex` exigem `execution_generation` inteiro
   positivo; ausência não significa autorização.
2. Revalidar projeto ativo, identidade do projeto, `running` e
   geração positiva no Control Plane.
3. Comparar a geração de origem com a atual; divergência retorna
   `project_execution_epoch_revoked` e nenhum novo efeito externo.
4. Chamar `factory_assert_project_execution_epoch` via acesso
   privilegiado server-side, com `project_id` e geração exatos,
   para falhar fechado se Pause/Resume ocorrer entre as consultas.
5. Revalidar nos checkpoints anteriores a dispatch CI, deploy
   Preview e persistência de Specialist; preservar gates de CI,
   qualidade, Preview SHA-exato e merge humano.

`project_execution_epoch_revoked` entra na lista de estados
`waiting`, não em `processed`. O lookahead Preview pula um
candidato revogado sem bloquear outro projeto autorizado. A
retomada de uma run antiga exige nova claim ou reconciliação
explícita/auditada, **nunca reutilização silenciosa** de seu token.

## Exceção de observação de ato humano já consumado

A observação de um PR **já mergeado humanamente** não é um
novo claim. O release observer continua exigindo projeto
atualmente running, PR/candidate/merge SHA exatos e os
gates de release existentes; pode registrar o fato humano
mesmo que a geração da run original seja antiga. Isso não
despacha CI, não faz deployment, não executa modelos, e
não autoriza merge automatizado.

## Evidência e limites

Executar `python -m unittest tests.test_followup_execution_epochs
tests.test_project_followup_guard tests.test_ci_followup_queue
tests.test_preview_followup_queue tests.test_release_followup_queue -v`
e a suite geral `validate`. Os cenários incluem projeto diferente,
claim missing, geração anterior depois de Pause/Resume, corrida HTTP 409
no RPC e fair continuation cross-project.

Não há chamadas pagas, migration, aumento de privilégios ou
alteração de RLS. A migration de recuperação
`20261020194500_fence_recovery_manual_project_control.sql`
continua pendente e exige autorização específica de produção.

O RPC fornece apenas um checkpoint transacional; não mantém lock
sobre chamadas externas GitHub/Vercel. Essas chamadas não podem
ser desfeitas retroativamente e as reconciliações duráveis,
receipts e lease/epoch guards existentes permanecem necessários.

## Fairness: projetos pausados nao ocupam o lookahead de CI/Release/Preview

O checkpoint transacional continua obrigatorio depois da selecao. Antes desta
correcao, CI e Release observavam no maximo oito runs por wake, sempre comecando
das mais antigas. Oito runs pausadas podiam esconder indefinidamente um nono
candidato de outro projeto ativo. Preview tinha limite inicial de 50.

Agora, os tres seletores usam os FKs existentes factory_runs -> factory_tasks
-> factory_projects -> factory_project_execution_controls com PostgREST
!inner em todos os relacionamentos. O banco filtra is_active=true,
state=running e generation>0 ANTES do order/limit. Nenhuma run e alterada;
projeto pausado/stopped/draft nao gasta janela de observacao nem quota GitHub.
O RPC de epoch no worker ainda confere a identidade e a geracao exatas
antes de qualquer efeito. Falha de relacao/REST e fail-closed, sem fallback
para o FIFO antigo. Todos project_kind, inclusive platform, greenfield,
existing e ai_agent, seguem o mesmo contrato.

O teto de oito observacoes permanece intencional entre candidatos que estao
running mas esperam CI externo ou merge humano. Esta correcao elimina a fome
especificamente causada por projetos nao executaveis; nao altera o gate
humano de release nem autoriza replay de epoch revogada.

Regressao offline: python -m unittest tests.test_followup_active_project_query
tests.test_followup_execution_epochs -v. Validar CI + acceptance no SHA exato.
Nao exige DDL, novo grant/RLS ou credencial. Migration de recovery 20261020194500
continua pendente de autorizacao separada.

## Fairness cross-wake para CI e Release

Um limite de oito observacoes que sempre reinicia no inicio da fila pode
mascarar indefinidamente um nono projeto elegivel quando oito projetos
ativos aguardam CI, ou um merge humano. O filtro de projetos nao-running
da #1015 e necessario, mas nao resolve esses waits legitimos.

Os workers CI e Release agora tem cursor **advisory** em eventos
append-only ja permitidos pelo Control Plane (`factory_audit_events`,
`followup.fair_scan_reserved`). Cada wake reserva sua proxima janela
de oito posicoes *antes* da primeira consulta externa; o wake seguinte
inspeciona a janela seguinte. Se a fila encolheu, a varredura retorna
a primeira janela no mesmo wake. Os registros permanecem FIFO com
ordenacao estavel `created_at,id`, sem alterar run status ou requeue.

`wait_dispatched_ci` (CI ja solicitado) e `candidate_drift_blocked`
(SHA de PR divergente) sao **waiting**, nao trabalho concluido.
Em CI ou Release, drift gera diagnostico, sem adotar SHA inesperado,
registrar sucesso ou bloquear outra run. Erros de API desconhecidos
continuam fail-closed.

O cursor e apenas ordenacao, nao transacao/lease/claim nem garantia
de exactly-once contra operacoes externas. A serializacao global do GHA
continua vigente; RPCs e gates por geracao, custo e merge humano
sao as unicas autoridades para efeitos. Falha na persistencia do
cursor bloqueia a nova varredura antes de consultar GitHub.

Testes gratuitos: tests.test_followup_round_robin_fairness,
tests.test_followup_fair_continuation e acceptance/CI SHA-exato.
Sem Console, migration, ampliacao RLS, API paga ou auto-merge.
A migration de recovery 20261020194500 permanece independente.

## 21/10/2026 — Preview: fairness entre wakes e binding Probe→Execucao

O worker Preview antes escaneava somente os primeiros 12 candidatos.
Doze runs antigas com epoch revogada apos Pause/Resume poderiam
impedir indefinidamente um 13o projeto de chegar a Preview. Alem
disso, o GitHub Actions executa preview-probe antes de instalar o
browser e relia a fila para executar; uma mudanca da fila durante
instalacao poderia preparar o browser para a run A e tentar a run B.

Corrigido: Preview herda o cursor advisory em factory_audit_events
com stride 12; CI e Release continuam stride 8. O preview-probe reserva
a proxima janela uma unica vez antes de qualquer efeito externo e
seleciona ate 12 itens, respeitando Pause/Stop, geracao original,
quota e audit-only. Se todos estao revogados, retorna work=false;
o proximo wake avancara a janela. Fila encolhida retorna ao inicio
na mesma rodada. Falhas de persistencia impedem trabalho externo.

O probe fornece run_id UUID canonico e candidate_commit SHA exato.
O workflow valida os dois antes de preparar browser e passa os valores
somente via env; o worker Preview seleciona unicamente esse run_id,
revalida geracao e SHA e NUNCA usa outra run encontrada no topo da
fila. Handoff indisponivel = sem delivery, mudanca de identidade =
erro fail-closed, nao fallback para candidato diferente. Preview
N/A, release policy e merge humano seguem independentes.

Invocacoes manuais nao vinculadas mantem selecao segura por cursor.
Este bloco nao instala browser por candidata revogada, nao altera
schema, nao consome creditos de modelo, nao modifica Console/pilotos
e nao executa auto-merge. Tests/CI por SHA sao obrigatorios.
Migration recovery 20261020194500 continua pendente.
