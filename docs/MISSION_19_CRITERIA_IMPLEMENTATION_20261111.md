# Missão integrada — matriz técnica dos 19 critérios

Esta matriz é um registro técnico da missão no ramo `codex/fix-audit-hydration-19`.
Ela não é certificação, não altera o Control Plane e não autoriza merge ou release.
O baseline observado foi `main=9aa968cedb2aa441b18f421c3fcc07b1918434aa`;
o certificado durável desse SHA registrou 13 critérios `passed`, um `partial` e
cinco `missing`, com `product_ready=false`.

## Matriz de critérios

| Domínio | Critério | Implementação e testes verificados | Evidência disponível | Estado técnico |
| --- | --- | --- | --- | --- |
| Security | `authn_authz` | Guardas de rota, Server Actions, sessão adulterada e RBAC já têm regressões; esta missão acrescenta negativa de RPCs privilegiadas para `anon`/`authenticated`. | Captura autenticada B2 e QA PostgreSQL isolado; não cobre toda a identidade assinada em produção. | `implemented_pending_external_evidence` |
| Security | `data_access_boundaries` | RLS e grants de operadores exercitados em PostgreSQL isolado, incluindo leitura cruzada negada. | Catálogo live: todas as tabelas `factory_*` com RLS; prova dinâmica de todos os recursos ainda falta. | `implemented_pending_external_evidence` |
| Security | `secrets_dependencies` | Scanner de árvore, auditoria npm e contratos de não-exposição executados no SHA. | Atestado independente persistido. | `implemented_and_verified` |
| Operations | `health` | Health Console/Control Plane e verificador independente mantidos. | Atestado independente persistido. | `implemented_and_verified` |
| Operations | `traceability` | Vinculação nativa V2 de SHA, CI e proveniência mantida. | Atestado independente persistido. | `implemented_and_verified` |
| Operations | `recovery_alerting` | Recovery, alertas e scheduler têm contratos e QA isolado. | Atestado independente persistido. | `implemented_and_verified` |
| Test strategy | `unit_integration` | Suites Python, Node e PostgreSQL são exigidas por CI. | `validate` exato no SHA de baseline. | `implemented_and_verified` |
| Test strategy | `critical_e2e` | Harnesses negativos cobrem falhas e fences; não substituem jornada real. | CRM está somente em Preview não produtivo. | `blocked_external_dependency` |
| Test strategy | `regression_gates` | Ruleset, checks requeridos e bloqueio de auto-merge verificados. | Atestado independente persistido. | `implemented_and_verified` |
| Product experience | `surface_inventory` | 14 rotas autenticadas, navegação e detalhe de projeto mobile capturados. | Recibo de browser no SHA de baseline. | `implemented_and_verified` |
| Product experience | `responsive` | Desktop/mobile, overflow, toque e menu integral são validados. | Recibo de browser no SHA de baseline. | `implemented_and_verified` |
| Product experience | `accessibility` | Landmark, nomes, IDs, ordem de tabulação, referências ARIA e foco em conteúdo oculto são validados no contrato. | Captura autenticada limitada; ainda falta revisão integral WCAG e fluxos dinâmicos. | `implemented_pending_external_evidence` |
| Product experience | `states` | Estados de atenção e erros conhecidos têm teste; esta missão inclui `loading.tsx` e `error.tsx` globais, com retry e sem vazamento de diagnóstico. | Estados reais completos por módulo requerem jornadas Control Plane seguras. | `implemented_pending_external_evidence` |
| Documentation | `setup_configuration` | Setup sem credencial e comandos documentados foram reexecutados pelo verificador. | Atestado independente persistido. | `implemented_and_verified` |
| Documentation | `operations` | Runbooks e jobs operacionais foram ligados ao SHA. | Atestado independente persistido. | `implemented_and_verified` |
| Documentation | `release_rollback` | Revert isolado e gate humano de produção foram exercitados. | Atestado independente persistido. | `implemented_and_verified` |
| Functional completeness | `requirements_inventory` | Os 19 critérios apontam para contratos executáveis, testes e lacunas atuais. | Atestado independente persistido. | `implemented_and_verified` |
| Functional completeness | `mock_noop_demo_inventory` | Inventário e negação de entrypoints de runtime executados no CI. | Atestado independente persistido. | `implemented_and_verified` |
| Functional completeness | `critical_journeys` | Leitor read-only distingue CRM Preview de release e exclui o Service Desk aposentado. | Falta Start/jornada greenfield legítima e release humano observado. | `blocked_external_dependency` |

## Integrações e testes desta missão

- Console ↔ Control Plane: loading e erro globais não afirmam sucesso nem
  renderizam erro interno; a ação de retry não dispara escrita.
- Console ↔ Auth/RLS: usuários não confiáveis continuam bloqueados antes de
  dependências privilegiadas; o QA PostgreSQL usa somente banco efêmero.
- GitHub ↔ CI: a PR exige SHA e checks exatos; não há auto-merge.
- GitHub ↔ Vercel: qualquer mudança em `apps/console/**` exige Preview e
  browser no SHA candidato antes de merge humano; esta missão não publica.

Comandos executados localmente nesta missão:

```powershell
npm --prefix apps/console run typecheck
npm --prefix apps/console run build
node --test apps/console/tests/*.test.mjs
$env:PYTHONPATH='src'; py -3.14 -m unittest tests.test_console_global_feedback tests.test_block1_b2_execution_and_access tests.test_block1_console_routes tests.test_block1_requirements_trace tests.test_independent_requirements_inventory_evidence
```

## Causa-raiz observada no Preview candidato

As capturas autenticadas oficiais dos runs
[`42957904555`](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/42957904555)
e [`42958798005`](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/42958798005)
alcançaram o Preview oficial e completaram o ciclo de criação e remoção do
operador efêmero. Ambas falharam no gate B2 da rota administrativa antes de
qualquer escrita de produto. O recibo do Control Plane para o segundo run foi
consultado em modo leitura e está `expired`, portanto não restou conta de teste.

O workflow autenticado deliberadamente executa o verificador que está em
`main`, não um script mutável da PR. A melhoria deste ramo separa, no próximo
workflow confiável, três causas que antes tinham a mesma mensagem: exposição de
`/admin/operators`, perda de sessão do operador e redirecionamento inesperado.
Ela só pode ser observada depois de merge humano e do Preview/produção exato
correspondente. Não se deve despachar uma cópia da workflow em branch, trocar a
origem confiável, ou promover este diagnóstico a evidência positiva.

Após o merge `864e4c29`, o workflow confiável confirmou que a condição é
`b2_operator_admin_page_exposed`, não perda de sessão. O ramo de reparo
seguinte adiciona `GET /api/session`, uma leitura autenticada que devolve apenas
o papel efetivo da própria sessão. A captura exige explicitamente
`role=operator` antes de consultar a rota de administração; assim, uma elevação
de papel é separada de um eventual defeito de proteção de rota, sem registrar
token, e-mail, identificador de usuário ou conteúdo do Control Plane.

Após o merge humano `6b2970fe39402f650dec0600722c75f18d19a677`, a captura
oficial [`#43021529721`](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/43021529721)
confirmou `role=operator` e ainda assim observou a permanência em
`/admin/operators`. O ciclo de provisionamento e remoção do operador efêmero
foi concluído; isso descarta a hipótese de sessão perdida e impede tratar a
falha como aprovação de segurança. A correção candidata acrescenta uma barreira
de middleware antes da renderização dessa única rota administrativa, mantendo
as guardas existentes da página e da Server Action. Ela falha fechada para
papel ausente, ambíguo, não-admin ou erro de consulta, e só poderá ser aceita
como evidência após CI, Preview oficial e nova captura autenticada no SHA
integrado.

## Bloqueios externos reais e verificação posterior

1. `critical_e2e` e `critical_journeys`: um operador deve autorizar um Start
   legítimo para o CRM quando houver trabalho real, e o proprietário deve
   definir um produto greenfield novo, real e diferente do Service Desk.
   Depois, o leitor de jornada deve observar Start, PR, CI, Preview, merge
   humano, release e operação na mesma linhagem.
2. `authn_authz`, `data_access_boundaries`, `accessibility` e `states`:
   requerem evidência autenticada/operacional completa no SHA integrado. A
   certificação posterior deve executar apenas os verificadores independentes
   previstos, sem promover este documento ou mocks a prova.
3. Antes da certificação posterior: confirmar o SHA de `main`, CI e Preview
   quando `apps/console/**` mudar, então consultar o recibo persistido no
   Control Plane. `product_ready` deve permanecer calculado pelo certificador.

## Atualização técnica — witness B2/B3 de fronteira dinâmica

O pipeline de certificação agora reconhece um artefato adicional **somente**
quando ele vem de uma captura autenticada nova, no mesmo SHA avaliado. O
verificador independente baixa cada artefato pelo ID declarado no GitHub,
rejeita redirecionamento autenticado, arquivo extra, expiração, identidade de
run/branch/commit divergente, campos desconhecidos e qualquer fato que tente
promover artificialmente segurança, isolamento de tenant ou estado de backend.

- O witness B2 retém negativas reais de rotas privadas e API sem sessão, sessão
  inválida e operador em rota administrativa. Ele só permite estado `partial`
  para `authn_authz` e `data_access_boundaries`; JWT assinado independente,
  isolamento cross-tenant e cobertura integral continuam explicitamente
  `false`.
- O witness B3 agora exige duas evidências distintas para alcançar no máximo
  `partial` em `states`: as transições da interface por fixture e uma leitura
  autenticada real de `/api/human-attention`. A leitura registra apenas a
  classe disponível/indisponível e zero/positivo — jamais corpo, projeto,
  contagem, cookie ou conteúdo do Control Plane. Ela continua sem certificar
  todos os estados de backend, acessibilidade completa ou E2E independente.
- O produtor e o certificador revalidam o mesmo recibo antes de qualquer RPC
  persistente. Reuso histórico não habilita esse caminho; uma captura velha não
  pode elevar o SHA atual. Nenhum passo cria Start, altera RLS, grava dados de
  produto, consome modelo pago, faz merge ou publica produção.

As regressões adversariais cobrem conteúdo secreto, escrita/uso pago, flags de
certificação indevida, artefato duplicado/expirado e proveniência incompatível.
Este é avanço técnico de evidência limitada, não a certificação final nem uma
mudança dos bloqueios humanos de B4.
