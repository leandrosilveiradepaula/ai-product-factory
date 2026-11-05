# Fechamento Bloco 1 — nove critérios, evidência antes de PASS

Data de reconciliação: 2026-11-05. Este é um inventário **read-only**, não um atestado de certificação. Critérios originalmente anunciados como "8" são **9**: 3 segurança + 1 gates + 3 documentação + 2 completude funcional. Os outros 10 critérios pertencem aos blocos operacionais/UX/jornadas.

## Estado e defeito confirmado

- Baseline real após merge humano #1239: `main=7a7ec69f571b6043df749a070626c30ce4d160c4`, `validate` push #42052999290 SUCCESS, certificação Supabase `5202288e-d80c-4017-8537-b380398214ce` persistida no SHA. **3/19 passed**; `test_strategy/regression_gates=partial`; os outros oito itens deste bloco são `missing`.
- GitHub ruleset ativo [#24457514](https://github.com/leandrosilveiradepaula/ai-product-factory/rules/24457514) exige PR, impede delete/force-push, exige `test` e `factory-acceptance`; `required_approving_review_count=0` e `strict_required_status_checks_policy=false`. O workflow PostgreSQL QA não é check obrigatório do ruleset. Isso **não** autoriza automerge: merge de produção é gate humano, mas a cobertura automatizada de branch protection está incompleta.
- Não ampliar a ruleset sem gate humano de acesso administrativo. A QA PG deve continuar comprovada por execução real quando aplicável; documentar a lacuna, não promover `regression_gates`.
- A nova auditoria `scripts/audit_finalization_block1.py` inventaria documentos, fontes e marcadores de simulação, produz digests por arquivo e preserva `independent_pass=false` para todas as nove células. Ela não acessa valores de secrets, não lê banco, não cria Start, não toca produção nem chama modelos. Seus `partial` significam somente inventário de fontes.

## Condição de saída por critério (sem atalhos)

| Critério | Evidência independente ainda necessária |
| --- | --- |
| `security/authn_authz` | Browser autenticado em operador autorizado, matriz RBAC e negativas reais, token/issuer/claims corretos, recibo SHA-bound |
| `security/data_access_boundaries` | Revisão SQL de RLS/GRANT e RPCs + testes adversariais tenant/cross-repo/backend; não criar política pública |
| `security/secrets_dependencies` | Scanner real de segredos e dependências, revisão de exposição de tokens nos workflows/browser, artefato CI atual |
| `test_strategy/regression_gates` | Ler ruleset efetiva + latest PR run SHA, QA PG quando há migrations, Preview real quando aplicável e bloqueio do merge; gate de edição da ruleset permanece humano |
| `documentation/setup_configuration` | Reproduzir README/instalação em runner limpo sem credenciais e conferir versão/saídas |
| `documentation/operations` | Executar preflight/read-only de operações e incidentes com saída real, reconciliar comandos/estado atuais |
| `documentation/release_rollback` | Ensaio isolado de rollback/revert + testes negativos de auto-merge/produção; não realizar rollback produtivo |
| `functional_completeness/requirements_inventory` | Matriz requisito → implementação → teste → recibo, incluindo cada jornada do contrato, com cobertura completa ou bloqueio explícito |
| `functional_completeness/mock_noop_demo_inventory` | Classificar **cada** marcador de mock/dry_run/demo/noop e executar teste negativo de reachability até gates de produto; inventário de nomes não basta |

## Critérios de aceitação do bloco

1. Executar o inventário no CI do SHA candidato; seus nove registros nunca são `passed` por texto, SHA no link, presença de arquivo ou grep.
2. Para cada célula, implementar verificador independente e vinculá-lo ao produtor + certificador durável **somente** após provar as condições acima, inclusive casos negativos.
3. Confirmar `validate`, QA PostgreSQL quando aplicável, merge humano e certificação pós-merge no mesmo SHA; observar Control Plane, não declarar progresso com CI apenas.
4. Falta de permissão de operador, ajuste administrativo de ruleset ou ensaio produtivo deve ser reportada como gate externo, sem inventar aprovação.

O Bloco 1 não exige reexecutar o CRM #209, ativar Codex/WIF, pagar API, criar greenfield fictício, executar migration nem abrir acesso público. O objetivo é fechar lacunas reais, não multiplicar certificados artificiais.

## 05/11 — verificação estrutural negativa integrada ao CI

O job `test` também executa `scripts/audit_block1_source_boundaries.py` e os testes adversariais `tests/test_block1_source_boundaries.py`. A prova inspeciona a sintaxe AST de `resolve_github_token` e bloqueia remoção do `PermissionError` cross-repo, ausência da identidade `GITHUB_REPOSITORY`, ausência da exigência de baseline, desaparecimento de `test`/`factory-acceptance` e fontes ilegíveis. O relatório registra `security_certified=false` e `release_authorized=false` mesmo com todos os contratos presentes. Isso fortalece regressão, mas não substitui teste real de Auth/RLS/tenant.

## Ensaio offline de política de release/rollback

`tests/test_block1_release_rollback_exercise.py` executa a política real `evaluate_release` para PROD/DEV/PREVIEW, exige gate humano em PROD mesmo em risco default e verifica recusa de enum inválido. O procedimento de rollback continua exigindo PR de reversão e novo CI no SHA revertido; o teste não simula revert executado nem certifica rollback real. Nenhuma chamada de produção.
