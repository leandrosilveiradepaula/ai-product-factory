# Bloco 1 — política de proteção efetiva da main (05/11/2026)

## Diagnóstico reproduzível

A política GitHub efetiva não pode ser inferida da presença de arquivos de workflow nem de CI verde. O auditor `scripts/audit_block1_effective_gates.py` lê via API GitHub **somente GET** a lista de rulesets e o conteúdo completo de cada ruleset, calcula as restrições vigentes e informa bloqueios sem modificar configurações.

No ruleset atual #24457514, verificado antes desta PR, os checks obrigatórios são `test` e `factory-acceptance`. Há PR obrigatório, proibição de exclusão e force-push, mas `product-readiness-postgres` não é obrigatório, `strict_required_status_checks_policy=false` e `required_approving_review_count=0`. São lacunas explícitas de proteção, não provas de que a Factory pode realizar merge de produção: o gate humano da Factory continua obrigatório independentemente da configuração GitHub.

## Sem falso PASS

O auditor sempre emite `regression_gates_certified=false`, mesmo se todos os checks estiverem presentes: faltam as verificações de CI real por SHA, QA PostgreSQL para migration e Preview aplicável. Os testes negativos cobrem ruleset desativado, ausente, sem checks, sem revisão e não estrito. Se a API não permitir leitura, a execução informa `unverified` e falha fechada, nunca assume proteção.

A correção das regras GitHub requer acesso administrativo e decisão humana separada. Esta PR **não altera rulesets, RLS, dados, produção, custo ou merge**. `test_strategy/regression_gates` permanece parcial até evidência independente integral.

## Linha de base

A PR #1241 foi mergeada humanamente em `512f0bb7652e271ce4e9f4e42de1398571c64031`, com `validate` push #42079696529 SUCCESS. Os nove critérios do Bloco 1 continuam sem certificação integral; não confundir inventário com prova de acesso/autorização/rollback.
