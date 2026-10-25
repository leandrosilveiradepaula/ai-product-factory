# Certificação de integração não produtiva — auditor da jornada

Este contrato é **somente leitura** e não substitui `operations` ou release de
produção. Ele distingue um merge humano em `preview/**` de um merge humano
em `main`, usando o Start real, a linhagem exata do Change Set, o GitHub e
evidência independente de navegador do **SHA de merge**, não apenas do PR.

## Incidente externo real (25/10/2026)

A Prova 2 da Factory usou `crm-infodive` com Start OWNER, Change Set
`673a2fc7-5f8c-40da-8bec-18ff6bb7eeed` e PR CRM
[#197](https://github.com/leandrosilveiradepaula/crm-infodive/pull/197).
As quatro Work Units foram integradas ao longo de quatro commits de PR:

| Onda | SHA de integração do PR |
| --- | --- |
| 1 | `28e58ad942029335b3ffb92050c5e1062aa496cf` |
| 2 | `609be20a21d76427de14f0e7066599a7822de53a` |
| 3 | `56e0c71ed786cca10074d3a87652c5b6739abc5f` |
| 4 | `ae7fbb3143f677b555fc862926f17b033b7df6fb` |

Uma Work Unit anterior pode ter seus arquivos modificados por uma onda
posterior legítima. O auditor anterior comparava todos os arquivos de cada
Work Unit ao **último** candidato; isso reprovava incorretamente a proveniência
apesar de os blobs de cada Work Unit terem sido copiados no respectivo commit
de integração. O contrato novo exige:

1. Recibos `create_pr` do mesmo Change Set/PR, em ordem de ID e timestamp,
   sem duplicações, cada um com SHA imutável e cadeia GitHub fast-forward.
2. Cada Work Unit com run descendente do Start, timestamps presentes, paths
   verificados e bytes idênticos **no primeiro candidato subsequente**.
   Nenhum candidato intermediário é aceito como o SHA final da PR.
3. CI nativa exata, QA, Security, quality gate e Preview obrigatórios.
   Para Vercel, `evidence_ref` é o ID do deployment; os recibos de Preview
   e browser devem compartilhar o ID com o gate SHA/PR e o registro de
   deployment no mesmo run. O navegador deve validar a URL exata.
4. PR GitHub `closed/merged` com head SHA fixo e alvo `preview/**`;
   evento `change_set.nonproduction_merge.observed` service-only no mesmo
   release run, `status=integrated`, Change Set `completed`, identidade
   exata de repositório, PR, branches e SHA de merge.
5. Snapshot `factory_project_state_snapshots` vinculado por ID no evento,
   no mesmo projeto, com `candidate_commit=merge_sha`, `browser_verified`,
   verificador correlacionado, `gaps=[]` e nenhum direito de produção.
   Conferir branch Preview e ausência do SHA no caminho de produção, sem
   forçar ref, produzir novo deploy ou autenticar fora do caminho oficial.
6. Após as leituras, repetir o witness GitHub para recusar deriva concorrente.
   Escopos parciais, replay, branch base diferente e prova posterior
   contraditória falham fechados.

O merge humano foi `08257c0d545bf98c7f34ae40d8b2e221468764ab`
em `preview/hardening-release-candidate`. A CI pós-merge
[#40205496275](https://github.com/leandrosilveiradepaula/crm-infodive/actions/runs/40205496275)
passou; a verificação Playwright
[#40205752751](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/40205752751)
ficou em snapshot `011d1579-762b-4a1a-80c3-823e53d0aaa1`.
O observer [#40205844090](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/40205844090)
registrou `integrated_nonproduction` no run
`eafd1ac1-b57d-47d9-98eb-55a90003e6db`. Nenhum desses recibos
autoriza o merge da `main` do CRM.

## Comando OWNER após merge humano desta correção

Na [issue #713](https://github.com/leandrosilveiradepaula/ai-product-factory/issues/713),
um comentário da própria conta OWNER, uma única linha exata:

```text
/factory-journey-audit crm-infodive 7a4a88ac-2ad2-42bc-bc6b-5135035b0d84 2026-10-24T23:40:00Z scope=nonproduction
```

Este é o **novo modo opt-in**; sem o sufixo, o comando anterior continua
exigindo `operations` de produção. O job `journey-readonly` não tem
tokens cross-repo de escrita, não chama OpenAI/Codex e não cria release.

Só é PASS no modo não produtivo quando o artefato auditado retorna:
`status=integrated_nonproduction`,
`classification=integrated_nonproduction`,
`requirement_met=true`,
`highest_verified=awaiting_release`,
`nonproduction_integrated=true` e `nonproduction_merge_sha` correto.
`human_release_observed` e `operations` permanecem **not_reached**.
`product_ready=false`, `paid_calls=0` e `writes=0`.
Não apresentar esse status como conclusão do produto global.

A execução anterior
[#40206537474](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/40206537474)
falhou com `merged_candidate_without_verified_release`; esse era o
comando **de produção** sem escopo não produtivo. Não modificar auditoria
histórica ou fabricar release para alterá-lo.

## Gates que continuam separados

- Merge da PR da Factory em `main` exige humano. Nenhuma chamada desse
  auditor faz auto-merge, SQL, migration, deploy ou alteração de Control Plane.
- Certificação global de seis domínios (segurança, isolamento, operação,
  testes, experiência e documentação), greenfield externo realmente autorizado
  e credenciais Codex/WIF quando aplicáveis permanecem pendentes. PR #197 em
  Preview jamais substitui release real de produção.
- Testes: `PYTHONPATH=src python -m unittest discover -s tests -p 'test_journey_nonproduction.py'`,
  `test_journey_reconciled_release.py`, `test_audit_autonomy_journey_cli.py`
  e `test_journey_audit_trigger.py`; CI `validate` / `factory-acceptance`
  no SHA exato é obrigatória antes de pedir merge.
