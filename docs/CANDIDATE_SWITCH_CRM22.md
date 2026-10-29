# Troca controlada de candidato existente — CRM #22

## Causa real

O manifesto \`crm-infodive\` guarda um candidato não produtivo da PR #56,
\`preview/hardening-release-candidate\`, SHA
\`08257c0d545bf98c7f34ae40d8b2e221468764ab\`. A função antiga
\`factory_repin_nonproduction_target_v1\` permite atualizar **somente** o
SHA dessa mesma PR/branch; não permite adotar uma PR independente e alinhada
à continuação OWNER da issue CRM #22.

A PR CRM #202 corrige uma falha reproduzida no código: acesso
\`service_role\` aos remetentes existentes de organizações alheias sem filtro
de tenant. Isso não autoriza reaproveitar ou reabrir a linhagem histórica da
PR #56 ou seus Change Sets concluídos.

## Solução

- \`verify_candidate_switch\` atesta via GitHub **ambas** as identidades
  imutáveis, issue #22 realmente autorizada em \`continuation_request\`,
  escopo de código, estado da PR, base \`main\` atual, compare \`ahead\`
  sem \`behind\` e run mais recente do workflow nativo \`CRM validation\`
  no SHA exato.
- A migration instala um **novo** RPC \`SECURITY INVOKER\`, concedido apenas
  a \`service_role\`, com CAS de \`generation/version\`, controle \`running\`,
  ausência de trabalho vivo e evento de auditoria
  \`project.delivery_target.replaced\`. Mantém o \`repin_policy\` e
  preserva integralmente runs/Change Sets/avaliações históricas.
- A migration não é aplicada automaticamente; exige revisão, CI e **aprovação
  humana específica para aplicar SQL em produção**, mesmo após merge humano.
- Esta troca **não** significa que a Jornada 1 terminou e não cria um
  \`awaiting_release\` artificial. É apenas a identidade de candidato
  necessária para a próxima execução verificada.

## Execução quando gates forem atendidos

1. Exigir CI \`CRM validation\` verde, Vercel Preview no commit
   exato do CRM e PR aberta não-draft, em \`preview/**\`.
2. Exigir CI \`validate\` e \`candidate-switch-postgres\` verdes na PR
   da Factory; depois merge **humano** em \`main\`.
3. Obter aprovação específica e aplicar a migration versionada via
   fluxo oficial de Supabase. Verificar ACL
   \`service_role=true\`, \`anon/authenticated=false\`.
4. Reconciliar somente o projeto CRM, com credenciais server-side:
   \`\`\`bash
   PYTHONPATH=src python scripts/switch_existing_nonproduction_candidate.py \
     --project-key crm-infodive --candidate-pr 202 --issue-number 22
   \`\`\`
5. Comparar recibo \`status=replaced\`, nova \`generation/version\` e
   evento de auditoria; depois retomar apenas a jornada legitimamente
   autorizada pela Factory, sem chamadas pagas de sondagem.
6. Se surgir drift de PR/CI/ref/controle, falhar fechado e reinspecionar.
   Nunca atualizar \`manifest\` manualmente, forjar CI, abrir gate por
   conveniência ou realizar merge de produção via runtime.
