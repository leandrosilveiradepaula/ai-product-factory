# Rotação após merge humano — candidato source-only de projeto existente

## Defeito operacional observado

No dia 29/10/2026, a PR CRM #202 foi mergeada por humano:
HEAD do candidato 0381e414f9580aa90a15bf1b3c9c8815d7f906b3,
merge em main f9b953e9c22ca112cb508c9ca89ddba4e5849cf7.
O Control Plane da Factory ainda apontava para a PR #202 fechada, em
geração 15 / versão 14. O guard PinnedNonproductionTarget.verify exige
PR aberta para uma nova reconciliação: novos Starts seriam barrados.
Não é legítimo reabrir a PR antiga ou reaproveitar o Start falho
958bb0e3-859f-4e78-8979-4c52cd87c10a.

## Contrato do novo caminho, sem migration

A função já implantada factory_replace_nonproduction_candidate_v1
é service_role-only, SECURITY INVOKER e possui CAS de geração/versão,
controle running, quiescência e auditoria atômica. O novo operador
released_existing_candidate adiciona o preflight que faltava quando
o candidato antigo já foi integrado humanamente.

1. Lê o registro da Factory e sua continuação OWNER vinculada à issue
   autorizada. Verifica por GET que a PR antiga é exatamente a pinned,
   closed + merged, e que seu merge_commit_sha é ancestral da main atual.
   Não exige que a branch antiga ainda exista.
2. Exige nova PR aberta em DRAFT (fonte apenas), mesma repository, base main atual,
   head preview/** verificado, comparação ahead (1–8 commits) sem behind,
   única mudança docs/codex/CURRENT_TASK.md.
3. A nova seção de autorização deve referir-se à mesma issue do OWNER.
   Lê 2–4 caminhos de código/testes existentes no SHA do novo candidato;
   exige CI nativa CRM validation SUCCESS no HEAD exato.
4. Revalida ambas as PRs e os refs imediatamente antes da transação.
   Chama somente a RPC versionada original; quiescência e CAS são
   novamente conferidas no Control Plane, e a auditoria
   project.delivery_target.replaced é emitida na mesma transação.
5. Registra no artifact do GitHub Actions old merge SHA / novo source SHA
   e recibo saneado, sem atribuir Work Units. O próximo Start legítimo
   ainda precisará construir seu próprio Backlog, PR, QA e Preview.

A PR de bootstrap é deliberadamente **apenas fonte de autorização**. Não
contém implementação de produto nem conta como uma nova prova da Factory.
A PR CRM #202 mergeada não se transforma retroativamente em run da Factory.

## Operação

Após CI verde e **merge humano da PR da Factory**, publicar na issue #713
como OWNER, somente quando a PR source-only nova estiver aberta/verde:

/factory-rotate-released-candidate crm-infodive pr=<PR_NUMBER> issue=22

O workflow autonomous-runner.yml@main verifica a identidade do OWNER
antes de OIDC, usa a permissão server-side existente e escreve um único
recibo de rotação com CAS. Não é necessário migration, novo broker,
token no chat, alteração de RLS, saldo de modelo, auto-merge ou release.

Somente depois de conferir o recibo/snapshot e validar novo escopo
poderá haver um NOVO Start legítimo. Se a questão de escopo real já
estiver implementada ou exigir alteração material de política, o
planejamento deve responder sem inventar Work Units.

**Limite de certificação:** CI/Preview do novo source-only PR não
provam E2E; product_ready=false até seis domínios avaliados e
linhagem inteira da jornada verificada.
