# Admissão de continuations terminais e Change Sets

## Problema factual

O root run humano da continuação CRM `8b607ffb-008c-4ae4-aa29-2f624f27988b` está `completed`, porém seu Change Set `552fd082-7c8e-4ed7-a712-2a550bb50a52` está `superseded`. A Work Unit vinculada produziu um commit, mas não há `release_run_id` para esse Change Set. O auditor E2E daquela continuação confirmou só cinco etapas. O diagnóstico de admissão respondia `no_new_action`, sem explicar a falta de handoff de entrega.

## Comportamento correto

Quando o usuário escolhe **run exata**, o leitor resolve o root task id do run e apenas Change Sets que pertencem ao mesmo projeto e à raiz, no máximo 30 registros e 30 Work Units. A validação prévia rejeita referências cruzadas, IDs inválidos, duplicatas e output SHA malformado. Não observa Change Set de outro root mesmo que seja mais recente.

O classificador `admission_terminal_lineage` devolve exclusivamente metadados fixos e não sensíveis: estado do Change Set, contagem de Work Units, outputs formalmente corretos, existência de release_run_id e epoch revogado. `superseded` exige revisão do motivo do encerramento; `blocked` remete à causa durável; Change Set ainda ativo requer inspeção de elegibilidade sem claim. Um Change Set `completed` ainda não prova release, e um output SHA não prova CI, Preview ou merge. Pausa/Stop e outro estado do controle têm precedência sobre a razão do Change Set.

A ação segura é **analisar evidências do Change Set**, não reexecutar run/código/CI/modelo automaticamente. Retomar desenvolvimento exige novo caminho de trabalho autenticado, apenas se houver uma demanda atual não satisfeita. Produtos globais continuam `not_assessed` ou `not_ready` até auditoria independente.

## Testar

- `PYTHONPATH=src python -m unittest tests.test_admission_terminal_lineage tests.test_admission_diagnostics`
- `validate` + `factory-acceptance` no GitHub Actions (branch e SHA exatos).
- Depois de merge humano da Factory, emitir comando owner-only `/factory-admission-diagnose crm-infodive 8b607ffb-008c-4ae4-aa29-2f624f27988b` na issue #713. Conferir `root_change_set_superseded`, output count 1, generation 4 vs 6, sem alteração de estado.
- Não criar Preview para codepaths Python/docs; nenhum SQL migration nesta mudança.

