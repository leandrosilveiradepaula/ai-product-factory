# Governanca greenfield e preflight de recuperacao (21/11/2026)

## Evidencia operacional real (sem reabrir runs)

A Factory VPS Direct esta ativa no SHA e2ad0362; os dois timers
Product Stage/Direct foram verificados no systemd, mas a fila de Direct
atribuidos estava vazia. Isso NAO prova uma implementacao ponta a ponta
da SQL InfoDive na tarefa real.

No Dark Channel Studio, o run historico
\`8eae8dc6-3d58-4941-93db-4b857fac040b\` foi bloqueado por alegada
ausencia do texto de AGENTS.md no contexto exato do Change Set
\`0bccb423-cacb-49fa-b238-c8baba27e372\`. Leitura GitHub GET
comprovou que AGENTS.md nao existe no main atual nem no SHA
\`9290634e647a381712b4b1b5bbd1ba0159969ff1\` daquele reparo.
O contrato de \`greenfield_source_context.py\` permite explicitamente
greenfield SEM AGENTS/CURRENT_TASK, desde que haja README,
source SHA e autorizacao de escrita limitada.

Causa de falsa recusa pelo modelo: \`implementation_producer.py\`
tratava AGENTS.md como obrigatorio universal. Agora o pacote de
contexto inclui \`repository.project_kind\` de origem Control Plane
(e \`unspecified\` para desconhecidos) e o prompt distingue AGENTS
realmente fornecido do ausente em greenfields. Em todo caso, se
fornecido, AGENTS e autoridade no SHA exato. A ausencia nunca amplia
\`write_scopes\` nem dispensa README, evidencias, RLS, gate de
migration, seguranca, custo ou gate humano de producao.

## Recuperacao de operator Restart: por que o run falhou

A recuperacao \`02f156ba-4593-4876-96da-9cfa96949485\`, criada
pelo comando humano Restart no Console, terminou \`failed\` com
\`reconciliation_context_preflight_failed\`. O Control Plane registra
\`operator-blocked-work-recovery\`, mas o manifesto greenfield nao
possui \`continuation_request.source=github-owner\`, exigido pelo
preflight antes de reconciliar source main/README/paths. Nao converter
o comando Restart em OWNER Start, forjar ator, usar stale source SHA
ou reabrir Change Set terminal.

O preflight agora devolve codigo DURAVEL e sanitizado
\`reconciliation_greenfield_owner_continuation_required\` ao
identificar esse contrato ausente, antes de GET GitHub, tokens pagos
ou escrita. Esse codigo e diagnostico, NAO autoriza automaticamente
a continuacao. Para dar novo Start real, o broker OWNER-first deve
verificar novo evento autentico no canal operacional oficial ou outro
caminho humano ja autorizado; nao criar Start por SQL ad hoc.
Nova linhagem deve avaliar a migration SQL em novo source SHA,
com CI/Preview/gates, sem reutilizar evidencias terminais antigas.

## Aceite

Testes offline cobrem ausente/presente AGENTS em greenfield, fail
closed em existing/unknown, imutabilidade de write scopes,
preflight sem GET sem OWNER, settlement de claim com razao tipada
e rejeicao de codigo arbitrario. Nao ha migration, modelos pagos,
benchmark de 63 perguntas, novo run, override de producao,
alteracao de Console nem merge automatico. Preview da Factory NA
(apenas Python, testes e documentacao).
