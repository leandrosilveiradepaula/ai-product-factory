# Console action audit

Reconciled: 2026-09-30.

This audit checks that visible interactive controls have a real route, server action, or client handler. It does not mutate production data merely to prove that a button exists. Mutating paths are verified by source binding, tests, CI and, when safe, Preview/browser evidence.

| Surface | Control | Binding | Audit state |
| --- | --- | --- | --- |
| Global | Brand | `/` | route exists |
| Global | Sidebar navigation | App Router pages | route inventory test |
| Global | + Novo trabalho | `/projects/new` | route exists |
| Global | Sair | `signOutAction` | server action |
| Login | Entrar | `signInAction` | server action; safe `next` preserved |
| Novo projeto | Novo produto / Projeto em andamento | React state handler | client action |
| Novo projeto | Revisar | `submitIntake` | server action |
| Novo projeto | Anexos | private Storage + attachment metadata | server-side upload |
| Revisão | Editar | returns with encoded draft context | briefing/draft preserved |
| Revisão | Referências | HTTPS anchor | actionable external link |
| Revisão | Iniciar / Importar | `start` server action | persists intake, finalizes attachments, queues bootstrap |
| Projeto | Fila de trabalho | `/queue` | route exists |
| Projeto | Conectar Supabase | OAuth connect route | admin-only, fail-closed |
| Projeto | Resultado OAuth | callback query result | visible success/failure notice |
| Execuções | Abrir fila | `/queue` | route exists |
| Execuções | Linha da execução | `/runs/[id]` | route exists |
| Gates | Aprovar / Rejeitar | `resolveGate` | server action |
| Operadores | Salvar e ativar / Desativar | `updateOperator` | admin server action |
| Configuração | Governança / Modelos / Execução / Preview / Segurança | page anchors | real targets |
| Configuração | Operadores | `/admin/operators` | only rendered to admin |
| Orquestração | Abrir execução / projeto | dynamic App Router links | routes exist |
| Deployments | Projeto / execução | dynamic App Router links | routes exist |
| Evals | Projeto / execução | dynamic App Router links | routes exist |
| Auditoria | Projeto / execução | dynamic App Router links | routes exist |
| Home | Diagnósticos / runs / gates / audit | App Router links | routes exist |

## Fail-closed corrections

- The dashboard no longer shows demo data when the Control Plane is missing.
- Login destinations reject external/protocol-relative redirects.
- Supabase connect is not offered to a non-admin operator.
- OAuth callback outcomes are visible to the operator instead of being represented only in the URL.
- Configuration labels that visually behaved like tabs are now real navigation anchors.
- Editing an intake reuses the current draft and counts existing attachments toward the 10-file limit.

## Verification

`tests/test_console_action_audit.py` covers route inventory and the critical bindings above.

Because this change touches `apps/console/**`, the final candidate must also pass:

1. Console dependency audit policy.
2. TypeScript typecheck.
3. Next.js production build.
4. Repository tests and Factory acceptance.
5. Exact Vercel Preview for the candidate SHA.
6. Browser evidence on that exact Preview.
7. Human production merge.
