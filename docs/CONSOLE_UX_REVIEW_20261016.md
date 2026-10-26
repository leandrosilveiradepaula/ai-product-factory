# Console UX — revisão operacional e redução de complexidade (16/10/2026)

## Problema e evidências do código antes da alteração

Auditoria sobre a `main` em `5710b9d64797cc9199d120766245916ad002a982`.
A interface apresentava as 13 telas de operação, diagnóstico, qualidade e
administração simultaneamente no menu, repetia o atalho “Novo projeto” em
diversas telas e exibia um banner explicativo em praticamente todas as páginas.
A entrada do produto era dominada por três cartões educativos permanentes,
antes dos projetos reais. A criação de um novo produto possuía **dois inputs
`name="users"` diferentes no mesmo formulário**, podendo produzir
ambiguidade ao submeter o briefing. Nos cartões de projeto, o indicador
percentual representava apenas a posição da etapa, mas podia ser interpretado
como percentual de implementação ou prontidão.

Este trabalho é **reorganização da experiência e correção de apresentação**;
não altera autenticação, papéis, chamadas de modelo, gastos, Supabase RPCs,
gate humano nem capacidades do adapter GitHub.

## Experiência-alvo (sem ocultar funções)

1. **Área de trabalho:** Visão geral, Projetos, Aprovações. As demais dez
   páginas continuam com **links reais, intactos**, dentro de
   “Ferramentas avançadas”, que abre automaticamente ao navegar para uma
   dessas rotas. Cada destino tem `aria-current`.
2. **Home:** ação contextual baseada somente em evidência consultada,
   projetos reais, indicadores operacionais compactos e casos que exigem
   investigação. Auditoria, custos, execuções e atividade detalhada continuam
   disponíveis em detalhes colapsáveis. `getHumanGates(30,true)` e
   `g.actionable` impedem apresentar gates históricos como decisões.
3. **Celular:** cabeçalho curto, menu completo em disclosure e navegação
   inferior de três destinos fixos; contagem de decisões permanece visível.
   O menu fecha após mudança de rota; áreas avançadas nunca deixam de existir.
   Área útil recebe reserva de espaço para a barra inferior; sem esconder
   overflow horizontal do documento.
4. **Projeto:** uma ação de continuação por vez; “Solicitar alteração” é
   secundária quando há intervenção humana prioritária. Reconciliação e
   fila continuam acessíveis em “Mais opções”. A revisão de domínios de
   qualidade e as integrações prontas entram em disclosures, mas **avisos,
   motivos e blockers reais continuam expostos**.
5. **Prontidão, não percentuais:** os cartões e detalhes mostram etapa
   de fluxo (1 a 5), nunca um falso “80% pronto”. Gate de produção exige
   CI, auditoria, Preview/evidência ou não aplicabilidade explícita, e
   merge humano; nenhuma etapa de UI implica release verificado.
6. **Novo projeto:** entrada por prompt e nome acima da dobra,
   complementos/anexos em disclosure com preservação de valores do
   rascunho, etapa de revisão antes do envio, sem duplicar `users`.
   Campos existentes e payload continuam com os mesmos nomes e contratos.

## Critérios de validação

- Testes offline de arquitetura da interface: todas as rotas preservadas,
  gating/bloqueios intactos, decisão acionável, formulário sem campos
  duplicados, menu mobile e ausência de percentual enganoso.
- `validate`, `factory-acceptance`, `Console validation` com `npm ci`,
  `tsc --noEmit` e `next build`, todos no SHA da PR.
- GitHub check-run da Vercel indicando Preview **exato** do candidato,
  quando o provedor e quota permitirem. Verificar o SHA, URL e status READY.
- Evidência Playwright autenticada vinculada ao Preview e SHA:
  `overview`, `projects`, `new-project`, `human-gates`, detalhes,
  `overview-mobile`, `projects-mobile`, `configuration-mobile`,
  `overview-mobile-menu`, foco, rotas avançadas e ausência de overflow
  a 390px. Screenshot/render não substitui validação dos estados de
  acesso e ações de servidor.
- Revisão humana da UI, principalmente celular, antes de merge da Factory.
  Qualquer quota/credencial de Preview indisponível bloqueia publicação,
  **não** justifica marcar Preview validado nem burlar o gate.

## Não objetivo

Não redesenhar toda a identidade visual, apagar páginas, esconder estados de
segurança, reestruturar o banco ou liberar novas permissões. Futuras mudanças
nos formulários de gates ou comunicação de incidentes exigem evidência própria
e não devem desativar controles de aprovação existentes.

**Estado:** documento de mudança proposta; implementação, CI e Preview precisam
ser verificados na respectiva PR. Não publicado até merge humano.

## 26/10/2026 — Status operacionais sem falso verde

O componente compartilhado StatusPill passa a usar uma lista explícita de estados de sucesso: um status desconhecido ou contraditório não pode ficar verde por conter as palavras ready, healthy ou active. Casos de regressão incluem inactive, unhealthy, not_ready, not_verified, unverified, provider_status_success_unverified, erro de CI, ausência de avaliação e Preview N/A. Estados de Preview prontos para revisão são distinguidos da aprovação final. Um estilo forçado como tone=success não pode sobrepor falhas e incerteza, e uma legenda customizada preserva o nome semântico do estado para tecnologia assistiva. Testes executam o TSX verdadeiro, sem mock da lógica, em Console validation. **Isso melhora a apresentação; não comprova, por si só, auditoria UX/a11y completa ou produto pronto.** Preview e browser vinculados ao SHA continuam gates de publicação.

## 26/10/2026 — Authentic browser gate after #1109

The reviewed Console code was published in production from merge #1109,
with green Console CI and exact-sha Vercel READY. The automatic protected
browser audit run #40327176953 timed out while installing browser OS
packages on an updated Ubuntu 26.04 hosted runner. No screenshot or account
was produced, so authenticated mobile/a11y/gates remain unverified on this
SHA. Fix runner determinism on Ubuntu 24.04 (previous run #39467414056 passed)
and verify actual browser boot before allowing temporary operator provisioning.
Do not fabricate a passing browser E2E, trigger visual workflow through
workflow-only changes, or dismiss the unresolved #692 gated migration UI
transition without a safe test.

## 26/10/2026 — Migration gate-bound UX receipt (candidate)

Independent production browser run [#40330808460](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/40330808460) passed 14 authenticated pages, mobile, RBAC and encrypted evidence with ephemeral operator cleanup. It did not authorize or apply a migration. The existing UI displays a busy message and a success banner, but audit events lacked the exact gate_id and historical records lack SQL integrity metadata. A URL lookup hint, a matching migration name, or another approved gate must not produce a success message.

This change writes gate_id on new migration audit events and requires exact approved gate/run/candidate/migration name plus source_integrity=exact_sql_verified before displaying success. Transient REST failure returns no success without breaking the gates page. Console CI tests the actual transpiled TSX components and the actual TypeScript reader with offline delayed/failing/audited responses, including pending fieldset, idempotent result, URL cleanup and dismissal. Hook-controlled behavior is not a full authenticated browser Server Action test or real migration; human production gate, required Preview and product_ready=false remain unchanged.

## 26/10/2026 — Targeted keyboard/DOM accessibility audit (candidate)

The real authenticated Console run #40336494210 succeeded on the exact
published #1112 SHA e2a963be239cf0b072d3dc5b8df0bf1a6bf3d0fb with 14
screens, an encrypted artifact and verified ephemeral-operator cleanup. The
existing capture checks mobile layout, menu touch targets and programmatic
skip-link focus, but it does not establish that keyboard Tab reaches that
link or whether controls on all critical routes have accessible names.

This candidate adds a real, fail-closed DOM snapshot check to the same
already-authorized capture path on all 14 screens: pt-BR document language,
non-empty document title, a single main landmark, visible skip link,
heading presence, names on visible interactive controls, image alt
attributes, duplicate IDs and positive tab-order exceptions. It also
requires actual Tab and Enter to reach the main landmark on overview.
Only counts/booleans and safe route keys are recorded, never DOM text,
field values, URLs, identities or cookies. The screenshot archive remains
encrypted under the existing broker and OIDC rules.

No new account creation or project mutation is added. This is a targeted
accessibility audit, not comprehensive WCAG certification. Console-only
tests and workflows run unprivileged, and code-only changes have Preview
N/A. An independently authorized new protected browser capture after
human merge remains required to claim the newly added checks executed.
Global product_ready remains false.
