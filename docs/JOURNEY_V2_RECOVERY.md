# Recuperação nativa de jornadas V2

## Escopo

Este procedimento recupera uma única falha de planejamento sem tarefas
acionáveis em uma jornada V2 já autorizada. Ele não é um retry legado, não
aceita uma nova solicitação e não cria uma nova jornada.

O incidente de referência é a jornada CRM `88e94d11-4ada-4630-aa6a-fbf2c5665b2b`,
run `27d71826-4527-4dc4-b727-870bb5687c4e`, tarefa
`07837b7f-3fc1-43b9-8f5f-41dc65731810`, no SHA
`fea4669258fcd832c7e187e7b00c1c5fb4d90a76`.

## Causa e correção

O binding V2 inicial já preservava `journey_id`, requisição, SHA e destino,
mas `factory_retry_failed_run` é legado: não reconstrói essa capacidade nem
carrega o checkpoint V2. A recuperação anterior de planejamento também só
aceita proveniência legada. Assim, uma falha por plano vazio não tinha um
caminho transacional para reinspecionar o commit imutável após a correção
runtime de #1167.

`20261031120000_native_journey_v2_recovery.sql` cria
`factory_resume_failed_journey_v2`. Sob lock do projeto e da jornada, ela:

- exige controle `running`, a mesma geração autorizada, o mesmo binding e
  SHA, sem candidato/Change Set/filhos;
- aceita somente o erro tipado de plano vazio com evidências completas de
  reconciliation e gap analysis da mesma run;
- cria no máximo uma nova run `planning`, no mesmo `journey_id`, sem repetir
  as etapas já persistidas e sem usar `factory_retry_failed_run`;
- mantém a tarefa, o binding, a requisição e o SHA e grava recibo durável;
- bloqueia pause, stop, mudança de geração, drift, concorrência e uma segunda
  tentativa do mesmo source-run.

O worker relê o checkpoint, a jornada e o commit pelo SHA exato antes de
qualquer chamada de modelo. Avanço posterior de `main` não substitui o SHA
autorizado; indisponibilidade do objeto exato falha fechada.

## Operação e gates

O modo `recovery` faz uma varredura limitada de jornadas sem candidato e pede
a retomada somente para runs com o erro tipado de planejamento vazio. O RPC
decide elegibilidade; não há SQL ad hoc,
reabertura de Change Set, auto-merge, Preview artificial ou mudança no CRM.
Enfileirar é gratuito; planejamento só acontece se o worker já autorizado
passar pelos gates de autenticação, ledger e orçamento existentes.

Antes de usar em produção: revisão humana da PR, CI no SHA da PR, merge humano
e aplicação explícita da migration pelo gate de Control Plane. A prova real da
jornada CRM requer ainda uma credencial oficial válida para o projeto Factory e
evidência durável da run resultante; testes offline não a substituem.

`scripts/verify_journey_v2_native_recovery_postgres.py` aplica as migrations
V2 e de recovery em PostgreSQL descartável e comprova a RPC, repetição,
propagação de `journey_id`, checkpoint, ACL e bloqueio por pausa. Ele nunca
usa o projeto Supabase Factory.
