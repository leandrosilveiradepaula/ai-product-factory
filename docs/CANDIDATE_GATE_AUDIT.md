# Auditora de gates por PR exata: qualquer projeto Factory

Escopo: observacao consultiva, somente leitura, de candidatos. O codigo recusa credenciais cross-repo implicitas, associacoes de projeto inconsistentes, PR de fork, SHA incorreto, inventario truncado e politica Preview ausente.

Cinco evidencias: (1) identidade exata Control Plane/GitHub e controle running/generation, (2) CI nativa da PR no repositorio correto com check runs de SHA e workflow pull_request real, (3) Preview applicability por manifest e arquivos alterados, sem confundir build e browser verificado, (4) quantidade de Change Sets bloqueados existentes sem novo claim, (5) gate humano de merge sempre preservado.

Owner command na issue Factory #713:

    /factory-candidate-gates infodive-service-desk pr=5 sha=c7b061c6f18961bd1fdfea51f59e2985bbe8247a

O workflow principal usa seu OIDC previamente autorizado e restringe token cross-repo ao host. Job no GitHub Actions devolve um artefato JSON sanitized por sete dias. Se encontra blockers verdadeiros e gera inventario completo, o job pode passar, mas o status do **candidato continua blocked**. Sem prova o job falha com unverifiable_live_evidence. Nunca interpreta a QA alternativa como equivalente a CI nativa, ou browser com Auth simulada como validacao de producao.

Testes: PYTHONPATH=src python -m unittest tests.test_candidate_gate_audit

Caso Service Desk: PR #5 em draft no SHA informado teve validacao em PostgreSQL/Chromium descartavel, porem CI nativa do repositorio privado sem runner, Preview nao configurado e Change Set anterior bloqueado por merge prematuro. Nenhuma migration, deploy, compra, modelo pago ou merge esta autorizado por esta auditoria.

