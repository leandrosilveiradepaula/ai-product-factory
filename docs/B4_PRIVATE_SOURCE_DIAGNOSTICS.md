# B4 — Diagnóstico sanitizado da prova privada no certificador 19/19

## Estado real em 17/11/2026
Factory `main` após a PR #1502, SHA `ee46408a513b2d5e0918abe9241d095f4803794d`, `validate push` #44170190246 **SUCCESS**, certifier first-attempt #44170315862 **17/19**; `readiness_guard_regression_blocked` corretamente impediu substituir o certificado persistido 18/19 por 17/19. Ausentes apenas `test_strategy/critical_e2e` e `functional_completeness/critical_journeys`.

O mesmo Studio run `3e747d9d-2440-4e78-8db0-55461753954e` está `merged`, Change Set `0bccb423-cacb-49fa-b238-c8baba27e372` `completed`, release report `released/observed_manual_merge`, operação e snapshot confirmados. O SHA Studio `a7ff9a4099d50c24af9858e03d0b785ed8faa452` descende do snapshot visual assinado `9290634e647a381712b4b1b5bbd1ba0159969ff1`; o GitHub comparou exatamente 2 commits e apenas 3 arquivos de tests/docs/workflow. As ACL do Control Plane não foram alteradas. Esta documentação não autoriza o produto Studio como funcional/autenticado.

## O defeito de observabilidade B4

O B4 aninhado visitava projetos e Change Sets, mas suprimia razões `b4_...` específicas em favor de `b4_greenfield_verified_candidate_missing_or_ambiguous`; o gerador de baseline capturava a exceção genericamente, persistindo apenas `missing`. Por isso três tentativas independentes não distinguiam falha de fonte GitHub privada de falha real de CI/Preview/merge. Nenhum novo PASS ou pontuação pode ser criado com diagnósticos.

A correção classifica somente **códigos internos fixos**, sem dados do projeto, URL, token, payload HTTP, stack trace nem segredos. O campo `reason` permanece estado `missing`, contendo apenas o código sanitizado. A guarda monotônica e a revalidação no certifier permanecem inalteradas.

## Como interpretar o próximo recibo

- `b4_cross_repo_explicit_credential_missing`: credencial explícita ausente no evento protegido; revisar o mapeamento de `FACTORY_GITHUB_TOKEN` sem exibir valor.
- `b4_cross_repo_access_denied`: a leitura cross-repo foi negada antes da requisição ou pela boundary; nunca usar `GITHUB_TOKEN` nativo como fallback.
- `b4_cross_repo_read_unavailable`: erro tipado de transporte/limite/retorno ao ler a API privada; investigar permissões, disponibilidade ou rate limit externamente, sem registrar resposta da API.
- `b4_browser_ancestor_compare_incomplete`: GitHub não comprovou ancestry/behind_by/total/changed_files inteiros e limitados; `b4_browser_witness_runtime_changed`: houve diferença não allowlisted ou no runtime, precisa de testemunha nova.
- `b4_current_wave_...`, `b4_independent_recovery_audit_missing` etc.: falha real do Control Plane contra a mesma jornada e SHA; não forçar estados SQL.

O operador deve ler o artefato `factory-readiness-certification-<run>` do `workflow_run` fresh/first attempt e a `criteria[test_strategy/critical_e2e].reason`. Decidir a correção baseado **no código exato**, antes de alterar autenticação ou requisitos. O erro de transporte nunca vira aprovação e não se acrescenta acesso público.

**Gate:** a Factory `main` em produção só pode mudar com merge humano. Não rodar o certifier manualmente ou `rerun` para contornar atestação da primeira tentativa.
