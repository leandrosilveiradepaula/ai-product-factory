# Prova 2 — contrato de testes fora do escopo do CI repair

## Evidência factual — 25/10/2026

A [PR CRM #197](https://github.com/leandrosilveiradepaula/crm-infodive/pull/197), criada pela Factory, está aberta no SHA `56e0c71ed786cca10074d3a87652c5b6739abc5f`. A segunda tentativa automática corrigiu o import `@/lib/session` e os quatro testes de `entry-guard` passaram. A CI nativa [#40156345062](https://github.com/leandrosilveiradepaula/crm-infodive/actions/runs/40156345062) passou TypeScript e três suites PostgreSQL, porém `Tests` falhou: 749 passaram, 1 falhou, 3 ignorados. A falha é `src/lib/sidebar-navigation-contract.test.ts:10:81`: um teste estático exige 16 `onNavigate={closeMobileMenu}`, mas a nova entrada do Service Desk eleva o total para 17. Remover callback da rota para obter 16 seria **quebrar o comportamento**, não corrigir o teste.

O Change Set real `673a2fc7-5f8c-40da-8bec-18ff6bb7eeed` possui quatro arquivos graváveis, entre eles `src/components/layout/Sidebar.tsx`, mas **não** o teste `src/lib/sidebar-navigation-contract.test.ts`. A terceira tentativa não pode usar esse arquivo sem autorização. Não há ampliação silenciosa de escopo e nenhuma correção é feita manualmente no CRM.

## Correção horizontal (qualquer repositório)

1. `ci_native_test_contract.py` recebe apenas o log nativo de job GitHub previamente validado pelo workflow ID/tentativa/SHA. Lê teste e arquivo fonte **no mesmo commit**, checa linha da asserção estática `match(...).length`, o `readFileSync` que aponta para o arquivo fonte, valor esperado e contagem real verificada. Exige uma única asserção coerente; redaction, tamanho excessivo e dados contraditórios falham fechados. Saída textual estritamente estruturada, nunca o log original.
2. `github_rest.py` anexa essa prova só ao `native-ci/tests` e somente se o job realmente falhou. `ci_repair_queue.py` **não** enfileira um terceiro reparo cego com sumário `Tests` genérico: só roteia à RPC específica se houver recibo completo e uma relação fonte→teste verificada. Reparo TypeScript/lint existente continua na RPC antiga.
3. Migration versionada `20261025031400_verified_native_ci_test_scope.sql` cria **nova RPC**, sem substituir nem ampliar a função anterior. Exige role privilegiada, projeto existing em running, Change Set/PR/SHA/generation atuais, origem de CI `code`, jobs nativos certificados, até quatro receipts idênticos, source já integrado, test `.test.ts[x]` ou `.spec.ts[x]` único, incremento exato de um na contagem. Cria nova Work Unit com a união do escopo histórico e **apenas aquele teste**, e auditoria `ci.repair.verified_test_scope`; não altera escopos de runs anteriores. Falha ou ausência de migration interrompem o fluxo antes de chamar modelo. Modelos não podem autorizar próprio escopo.
4. Testes Python offline cobrem derivação de prova, logs e conteúdo falsificados, projetos de arquivos diferentes, ausência de export, imutabilidade da origem e recusa antes da chamada paga. A matriz PostgreSQL16 descartável usa a nova função SQL real, exercita ACL, falsificações e replay.
5. O executor reparará o contrato sem remover handlers, modificar requisitos de autenticação ou afrouxar gates. Revisões de QA/Security, CI SHA-exata, Preview verificado e autorização humana de merge permanecem necessários.

## Operação segura

- **Gate 1:** merge humano da PR da Factory após CI integral.
- **Gate 2:** autorização humana independente para instalar apenas `verified_native_ci_test_scope` no Control Plane `fjplmxfcshhbmzgvyqlm`; conferir ACL `SECURITY INVOKER` (`service_role` somente), sem RLS pública.
- OWNER `/factory-wake` na issue #1055. A Factory revalida a PR #197 e os jobs no SHA exato, materializa apenas um terceiro reparo vinculado à falha e usa seus limites de orçamento. Sem acesso ao serviço ou se o recebimento de log falhar, **não gastar modelo**.
- Revalidar CI CRM e especialistas, Preview Vercel/browser e alcançar `awaiting_release`. O merge que publica produção continua humano. Não executar benchmark das 63 perguntas.

**Prova 2 permanece NÃO PASS** até a cadeia completa. O Service Desk é módulo do CRM, não produto independente.
