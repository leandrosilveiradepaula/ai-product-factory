# Auditora de gates por PR exata: qualquer projeto Factory

Escopo: observacao consultiva, somente leitura, de candidatos. O codigo recusa credenciais cross-repo implicitas, associacoes de projeto inconsistentes, PR de fork, SHA incorreto, inventario truncado e politica Preview ausente.

Cinco evidencias: (1) identidade exata Control Plane/GitHub e controle running/generation, (2) CI nativa da PR no repositorio correto com check runs de SHA e **todos** os workflows `pull_request` mais recentes por arquivo de workflow, (3) Preview applicability por manifest e arquivos alterados — inclusive o caminho anterior de um rename — sem confundir build e browser verificado, (4) quantidade de Change Sets bloqueados existentes sem novo claim, (5) gate humano de merge sempre preservado.

Um retry antigo falho do mesmo workflow pode ser superado por seu retry mais
novo bem-sucedido. Um segundo workflow nativo no mesmo SHA que esteja falho,
cancelado, skipped ou ainda em andamento mantém `native_ci_not_verified`; um
workflow bem-sucedido de `push`, QA externa ou o maior `run_id` global não
substitui essa verificação. A PR em draft também recebe
`candidate_pr_draft`: o artefato continua consultivo e `authorized=false`.

Cada item de `/pulls/{n}/files` é validado com status e path. Para
`status=renamed`, os paths novo e anterior são entregues à política Preview;
assim, mover/remover código de `required_paths` não permite afirmar Preview
N/A. Inventário sem status, rename sem origem ou paths ambíguos falha fechado.

Owner command na issue Factory #713:

    /factory-candidate-gates infodive-service-desk pr=5 sha=c7b061c6f18961bd1fdfea51f59e2985bbe8247a

O workflow principal usa seu OIDC previamente autorizado e restringe token cross-repo ao host. Job no GitHub Actions devolve um artefato JSON sanitized por sete dias. Se encontra blockers verdadeiros e gera inventario completo, o job pode passar, mas o status do **candidato continua blocked**. Sem prova o job falha com unverifiable_live_evidence. Nunca interpreta a QA alternativa como equivalente a CI nativa, ou browser com Auth simulada como validacao de producao.

Testes: PYTHONPATH=src python -m unittest tests.test_candidate_gate_audit

Caso Service Desk: PR #5 em draft no SHA informado teve validacao em PostgreSQL/Chromium descartavel, porem CI nativa do repositorio privado sem runner, Preview nao configurado e Change Set anterior bloqueado por merge prematuro. Nenhuma migration, deploy, compra, modelo pago ou merge esta autorizado por esta auditoria.

