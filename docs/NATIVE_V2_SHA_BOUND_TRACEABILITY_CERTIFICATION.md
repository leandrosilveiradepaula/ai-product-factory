# Atestação de rastreabilidade V2 com fonte independente e SHA atual

Este bloco fecha **somente** `observability_operations/traceability` usando a execução independente real da Jornada V2 existente CRM #209. Não executa Start, ciclo de desenvolvimento, browser novo, modelo pago, release de produção ou migrations.

## Proveniência e escopo

- Auditor original do OWNER: GitHub Actions `42026802447`, job `native-v2-journey-readonly`, Factory SHA `2fc03b19d72b76be55366f8d8fae940300640874`, `completed/success`, outros workers `skipped`.
- Artefato: `native-v2-readonly-42026802447` (`13414057651`), digest oficial `sha256:223765b014c9ffd4f11201f63c38844feaef420ba1ee8db8b2390b0f9b894070`, com expiração prevista para 12/11/2026. Atestação positiva só enquanto os bytes podem ser conferidos.
- CRM: jornada `bb14e150-2c7e-423b-8e5d-e211dab6225c`, 5 Work Units verificadas, candidato `d0738ee3f3fbb6fb5100e09804e0e2a92c9da0c7`, merge humano **Preview** `d84f41938a5e36b4b5f86133434c900c433bffc1`. Sem produção.
- Critério global: **rastreabilidade de uma cadeia existente**. `functional_completeness/critical_journeys`, `test_strategy/critical_e2e`, Segurança, UX, documentação e `recovery_alerting` continuam pendentes até provas próprias. O greenfield legítimo autorizado segue ausente.

## Caminho de verificação

No `product-readiness-certification-post-ci`, apenas após `validate push main` bem-sucedido no SHA exato, o broker OIDC já autorizado permite ler o Control Plane. Em fase de coleta e, **outra vez imediatamente antes das RPCs de persistência**, o certificador:

1. Revalida a identidade do workflow atual, a execução original OWNER, seus jobs de sucesso/skip e artefato vinculado ao SHA original.
2. Compara blob hashes dos sete arquivos do auditor entre o SHA auditado e o HEAD vigente, além do bloco exato do job V2 no runner. Qualquer mudança invalida o reaproveitamento.
3. Faz download do artefato com token apenas no GitHub API; o redirect HTTPS assinado aceita apenas hosts previstos e **nunca recebe token**.
4. Compara SHA-256 da ZIP, extrai JSON único com limite de bytes e confere todos os campos tipados, inclusive `production_released=false`, `paid_calls=0`, `writes=0`.
5. Lê `factory_journeys`, `factory_change_sets`, `factory_tasks`, `factory_runs` e `factory_project_execution_controls` via GET, confere vínculos, estado terminal e epoch; não usa RPC de escrita nem ID de projeto inexistente em `factory_runs`.
6. Autoriza apenas `VerifiedCriterionEvidence(domain=observability_operations,criterion=traceability)` derivado do runtime confiável no mesmo SHA. O `conservative_verified_manifest` permanece o padrão sem essa opção.

Na primeira verificação, ausência de fonte mantém a célula `missing` e persiste baseline conservadora; se a prova desaparece **entre coleta e gravação**, o certificador falha **antes** de chamar `begin`/`persist`, sem aceitar digest contraditório. Todos os seis domínios e `product_ready` permanecem `false` na ausência de 19 atestações válidas.

## QA e limites

Regressões offline validam OWNER/execução, jobs, SHA, alteração de código, arquivo/digest, linha de banco, produção indevida, origem do workflow e perda da prova entre fases. Preview Console não aplicável porque nenhuma alteração `apps/console/**` é feita.

Depois de merge humano, verificar `validate push main` e o job posterior `product-readiness-certification-post-ci` no SHA correto, baixar recibos, conferir estado persistido no Supabase. **Não presumir que a célula passou apenas porque CI ou job concluiu `success`.** Se o artefato expirar ou houver drift, registrar pendência e obter uma nova execução OWNER read-only, nunca preencher `passed` por declaração.

Referências: [auditoria V2 original](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/42026802447), [recibo na issue #713](https://github.com/leandrosilveiradepaula/ai-product-factory/issues/713#issuecomment-6657927100), `docs/FINALIZATION_EXECUTION_CONTRACT.md` e `docs/FINAL_CERTIFICATION_MATRIX_20261026.md`.
