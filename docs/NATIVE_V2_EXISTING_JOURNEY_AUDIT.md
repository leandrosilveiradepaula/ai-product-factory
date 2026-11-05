# Auditoria independente da Jornada V2 existente (read-only)

Este procedimento reutiliza a jornada **real** `crm-infodive` criada por OWNER e não executa um Start, um agente, SQL de escrita, Preview novo ou modelos pagos. Foi introduzido porque o auditor legado `SupabaseJourneyReader` procura `factory_project_execution_commands` e `project.continuation.requested`, enquanto a Jornada V2 registra `factory_journeys` + `journey.intake_accepted`.

## Execução após CI e merge humano da Factory

O broker do Control Plane possui allowlist de `workflow_ref`; o workflow V2 independente de #1234 foi corretamente negado pelo broker na execução [#42023882762](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/42023882762) (`unverifiable_live_evidence`), embora identidade OWNER e OIDC tenham passado. **Não** ampliar a allowlist do broker apenas para auditoria: executar o job `native-v2-journey-readonly` dentro do workflow **Factory autonomous runner** já autorizado, sem acordar outras lanes. O próprio OWNER comenta **na issue #713**, em linha única exata:

```text
/factory-v2-journey-audit crm-infodive bb14e150-2c7e-423b-8e5d-e211dab6225c
```

O job isolado verifica evento, identidade OWNER e GitHub repository **antes** do OIDC, usa somente `GET` PostgREST/GitHub, exige `FACTORY_GITHUB_TOKEN` de leitura cross-repo e guarda o artefato `native-v2-readonly-<run_id>`. Ausência de credencial/evidência gera bloqueio; nunca substituir com dados fabricados.

O auditor liga comentário GitHub original, SHA256 da solicitação, request UUID, recibos de intake/source binding, geração e política V2, root task + runs + Change Set, cinco Work Units, ondas sequenciais de PR e bytes de implementação, GitHub PR mergeado **somente** em `preview/**`, CI do candidato, QA, security, operations, gate de qualidade, deployment e browser do candidato. Revalida o merge SHA usando o snapshot pós-merge, a branch Preview e o run Actions do verificador. Qualquer ambiguidade, drift, mudança material de permissão ou ausência de prova bloqueia.

### Limites de interpretação

O resultado positivo exigido é `status=integrated_nonproduction`, `highest_verified=awaiting_release`, `production_released=false`, `product_ready=false`, `paid_calls=0`, `writes=0`. A prova diz respeito **apenas** à Jornada V2 CRM #209 em Preview. Não demonstra release de produção, F6 greenfield ou prontidão dos 19 critérios globais. O auditor legado e o certificador global continuam com suas próprias semânticas; não marcar domínio algum como PASS apenas por este recibo.

Testes locais: `PYTHONPATH=src python -m unittest discover -s tests -p 'test_native_v2_journey_audit.py' -v`, incorporados à CI geral. A versão candidata só pode ser usada depois de CI no SHA da PR e merge humano na Factory.
