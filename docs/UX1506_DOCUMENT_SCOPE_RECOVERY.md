# Recuperação do relatório UX/UI #1506 — escopo documental exato

Run direta `6e021307-b11c-4870-8d46-06ec4c730196` bloqueada na inspeção do repositório:
`exact new-file scope lacks a verified populated parent: docs/UX_UI_1506_AUDIT.md`.

A Factory concluiu reconciliação, gap analysis e planning por checkpoint; o bloqueio não
é um problema de custo ou de semântica. O executor permitia novos `.py/.ts/.tsx`
em pastas povoadas, mas não um **único novo arquivo Markdown** no `docs/` já povoado.

A correção do worker concede **apenas o nome literal** de um novo `.md` em
`docs/` com pai comprovadamente povoado na árvore Git do SHA fixado.
Não libera `docs/**`, não cria subdiretórios nem permite SQL, segredos ou
escrita fora do escopo já autorizado pela tarefa.

A migration `20261118014500_retry_verified_document_scope_preflight.sql`
reutiliza a recuperação de preflight existente, com novo caso tipado
exclusivamente `platform`, `ui`, projeto em execução e mesma geração,
run/workunit/task bloqueados, parent planning completo com origem Console
e mesmo escopo `docs/<arquivo>.md` na tarefa. Preserva o caso legado de
arquivos de contexto excessivamente grandes. ACL invoker/service_role-only.

Após testes PostgreSQL isolados e merge humano, **não aplicar a migration
sem autorização explícita de produção**. Conferir função e ACL no Supabase,
depois executar uma única recuperação tipada para o change set
`5d0656f0-aec3-42f2-93e2-bee0e2155fbf`, verificar o recibo e acordar
o scheduler pelo canal OWNER. Nunca rodar `factory_retry_failed_run`
nem repetir as etapas pagas da demanda.

A tarefa é documental; o relatório precisa distinguir inspeção de código,
hipóteses e evidência de navegador ausente. Não modificar Console ou fazer
merge automático para concluir a auditoria.
