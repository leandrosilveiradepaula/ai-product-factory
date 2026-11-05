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

## 05/11 — consulta direta read-only de fronteiras RLS no Supabase Factory

Projeto `fjplmxfcshhbmzgvyqlm`, SQL somente SELECT sobre catálogos PostgreSQL:

- **58/58** tabelas `public.factory_*` possuem RLS habilitado; 0 sem RLS.
- `pg_policies` retornou **uma única política**: `factory_console_operators_select_self` para `authenticated`, apenas SELECT, com `auth.uid() = user_id AND is_active = true`. Nenhuma política de leitura/escrita pública para as demais 57 tabelas.
- `has_table_privilege` retornou **zero** tabelas `factory_*` com INSERT/UPDATE/DELETE concedido a `anon` ou `authenticated`.
- Quatro funções `factory_*` de trigger (`factory_propagate_journey_binding_v2`, `factory_stamp_ci_release_epoch`, `factory_sync_ci_repair_lease`, `factory_sync_ci_repair_request`) herdam EXECUTE de `PUBLIC` para `anon`/`authenticated`; todas são `SECURITY INVOKER`, `RETURNS trigger`, e não fornecem caminho RPC direto de mutação. Registrar como observação para revisar grants em eventual hardening, sem afirmar exploração ou revogar sem migration aprovada.

**Alcance:** metadados atuais de RLS/GRANT/trigger verificados; não prova sessão real de usuário, tenant cross-repo ou autorização do Console. `security/data_access_boundaries` continua sem PASS. Nenhuma alteração de política, privilégio, dados ou Auth foi feita.

## 05/11 — inventário de caminhos de simulação e rastreabilidade de requisitos

A trilha agora executa em `validate/test`:
1. `scripts/inventory_block1_simulation_paths.py` faz parse AST de todos os módulos Python de runtime em `src/ai_product_factory`, enumera **somente** arquivo, linha e categoria de marcadores `dry_run/mock/noop/fixture/demo`, registra SHA-256 determinístico, rejeita symlink e Python inválido. O inventário não lê testes, não revela conteúdo de linhas e **não** confunde marcador de comentário com caminho alcançável.
2. `scripts/trace_block1_requirements.py` valida que todos os 19 critérios do contrato estão mapeados a fontes/testes candidatos existentes e registra hashes por arquivo; em fonte ausente, marca `incomplete`, nunca `passed`.
3. `tests/test_block1_simulation_inventory.py` e `tests/test_block1_requirements_trace.py` cobrem determinismo, falta de fonte, sintaxe inválida, symlink, valores de segredos não publicados, 19 critérios e recusa de certificação por inventário.

**Próxima prova para PASS de completude funcional:** classificar o inventário de ocorrências reais por alcance do runtime e comprovar por teste adversarial que nenhum fallback mock/noop entra no produto/release; vincular requisito → jornada executada → recibo independente, não apenas código/documentação.

**Nota de controle:** O Bloco 1 tem nove células. A certificação oficial continua vinculada a `main` pós-merge e **não** se atualiza por PR/CI. O trabalho é seguro e read-only, mas ainda não conclui o Bloco 1.
