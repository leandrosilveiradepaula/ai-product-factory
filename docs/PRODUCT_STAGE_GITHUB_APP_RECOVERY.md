# Recuperação Product Stage e token GitHub efêmero (21/11/2026)

O Direct na VPS já emitia credenciais temporárias GitHub App por
repositório, mas o Product Stage, no contexto de uma recuperação humana
do Dark Channel, instanciava `GitHubRestAdapter` sem token.
O segundo run da recuperação (`4d9a090c-b699-44bf-bafa-7e0fe321a7e7`)
falhou no preflight com `reconciliation_context_preflight_failed` antes
de executar qualquer etapa paga. O journal evidenciou `GitHub credential
is required`. O worker mantém os timers ativos e a versão aprovada
`5bc4844c` até o merge humano desta alteração.

O Product Stage passa a reutilizar `mint_vps_github_app_token`, com
escopo no projeto/repositório ativo verificado no Control Plane, sem
gravar token em arquivo, ambiente, argv, modelo ou logs. GitHub Actions
e outros provedores seguem pelo adapter/autoridade anteriores. A
falha de emissão bloqueia a reconciliação antes de invocar a LLM.

A autorização de recuperação existente é inalterada. Um run de retry
que falhou exclusivamente no preflight sem modelo pode ter **no máximo
uma** nova continuação, após validação de linhagem e erro original,
usando `factory_retry_failed_run` pelo service_role. A rotina recusa
uma cadeia de três ou mais retries, mismatch de project/actor/epoch,
Change Set terminal reaberto ou write scope alterado.

A geração de nova continuação não ocorre nesta PR; é uma ação
operacional controlada após merge humano, CI e rollout por SHA.
A migração SQL Dark Channel não é aplicada, Preview do Console é
N/A e auto-merge permanece inexistente.
