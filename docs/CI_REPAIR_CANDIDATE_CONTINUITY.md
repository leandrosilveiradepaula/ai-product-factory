# Prova 2 — CI repair no SHA integrado do CRM (25/10/2026)

## Incidente comprovado

A AI Product Factory produziu a primeira entrada autenticada do Service Desk como módulo do CRM, via root run `7a4a88ac-2ad2-42bc-bc6b-5135035b0d84`, Direct `bd5a2e8d-413e-442b-8f23-6ef3016ea39e`, Change Set `673a2fc7-5f8c-40da-8bec-18ff6bb7eeed` e [CRM PR #197](https://github.com/leandrosilveiradepaula/crm-infodive/pull/197), HEAD `28e58ad942029335b3ffb92050c5e1062aa496cf`, base Preview `preview/hardening-release-candidate`. O Direct criou commit de código `af86d5ca9500f7d3feeef612528085b7355ff719` alterando apenas quatro arquivos autorizados. Nenhum merge em produção.

A CI nativa CRM [#40150697885](https://github.com/leandrosilveiradepaula/crm-infodive/actions/runs/40150697885) falhou TypeScript `TS2307`: `src/app/(dashboard)/service-desk/page.tsx:2:28` importa `@/lib/auth` inexistente. A fonte real é `src/lib/session.ts`, mas esta correção **não edita CRM manualmente**. A Factory persistiu repair request `d1ba00fc-827d-4930-a04d-bcae57ef42f0`, tentativa 1/3 e Work Unit `19cc5394-8721-4ebf-8429-fb777f656d1d`, run `19767c5c-8a0d-4ada-8e9f-ad5df55181b1`. A primeira execução bloqueou antes de modelo ou commit: `PermissionError: repin evidence does not match exact pinned source`.

**Causa:** o verificador introduzido pela PR #1089 preserva corretamente o repin do projeto CRM para a branch Preview e seu SHA `0429872652e8cb2bc0e9cde618bf5e848190e186`. Porém a tentativa de CI repair opera legitimamente no commit *posterior* gerado pela própria Factory (`28e58ad...`). Seu `base_commit` não deve ser equiparado ao SHA de origem do projeto.

## Correção versionada

- `ci_repair_candidate_evidence.py` faz uma verificação **adicional e independente** de branch e PR de reparo reais no GitHub: repositório, branch `factory/change-set-...`, base Preview, HEAD SHA candidato, número de PR, estado open, ausência de merge/draft, request UUID, contagem de tentativas e arquivos exatos.
- `change_set_worker.py` exige a evidência após o binding original e antes de gerar contexto/modelo. Uma segunda leitura verifica que a identidade do reparo não mudou.
- `work_unit_context.py` vincula `repository.ci_repair_candidate_evidence` ao HEAD da PR de reparo. Não reutiliza `delivery_repin_evidence` do projeto como autorização do SHA novo; não amplia `write_scopes`; outros tipos de run preservam exigências anteriores.
- `ci_native_lint_diagnostics.py` e `github_rest.py` extraem **somente** caminho, linha, coluna, código TypeScript e alias local permitido de logs nativos já comprovados por run ID, tentativa e SHA. Nunca enviam log bruto, mensagens arbitrárias, URLs assinadas ou tokens ao modelo.
- Migration **apenas versionada e ainda não aplicada** `20261025013500_resume_blocked_ci_repair_candidate.sql`: RPC `SECURITY INVOKER` com EXECUTE apenas `service_role`; CAS de epoch, SHA, Work Unit/Change Set/repair request, CI code/typecheck, ausência de leases, commit, releases e repetição de auditoria. Reabre apenas a mesma tentativa falhada, mantendo o limite 1/3, Product Stage histórico e sem executar modelo dentro da RPC.
- Script de recuperação sem modelo é chamado no `candidate-repin`, inerte quando migration ausente. Nenhum auto-merge; release de `main` continua gate humano.

## Aceitação técnica e gates

1. Regressões Python: identidade da PR e escopos, recusa de head/base alterados, projeto errado, tentativa excedida, texto injetado e credenciais; parser TypeScript com `TS2307` real sem payload livre.
2. PostgreSQL **descartável** 16: permissão por role, cardinalidade 1, drift SHA/epoch, lease ativo, candidato já escrito, concorrência, replay 0, auditoria e root Product Stage não reexecutado. Nada apontando para Supabase real.
3. `validate` e matriz QA nativa completos no HEAD exato.
4. **Gate humano 1:** merge da PR de correção na `main` da Factory (runtime em produção).
5. **Gate humano 2 separado:** autorização explícita e aplicação da migration apenas ao Control Plane, depois verificação de roles e status.
6. Recuperar via OWNER `/factory-candidate-repin`, confirmar mesma run `19767c5c...`, única auditoria e status `queued`; emitir `/factory-wake` para o Direct corrigir o import da PR CRM #197. Exigir novo commit SHA, CI CRM nativa verde, Security/QA/Ops, Preview Vercel e browser real, gate de merge humano para CRM produção.

**Não declarar Prova 2 PASS até completar os recibos exigidos.** Não criar outro CRM/Vercel/Supabase para o Service Desk. Não executar benchmark de 63 perguntas nem chamar modelo pago para preflight.
