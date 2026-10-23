# J7 — Imutabilidade das evidências GitHub da jornada

## Objetivo

Não certificar um Start da Factory com uma mistura de snapshots de PR, branch,
inventário de arquivos, código de Work Unit e CI obtidos em momentos diferentes.
Esta correção adiciona **somente leitura** ao auditor; não inicia trabalho,
não altera o Control Plane, não chama modelos e não habilita auto-merge.

## Cinco contratos verificáveis

1. **PR de candidato admissível:** número, repositório, head SHA e
   `factory_change_sets.integration_branch` devem coincidir. PR aberta
   precisa estar não-draft, não mergeada e apontar para o SHA exato;
   PR já mergeada deve estar `closed`, `merged=true` e possuir
   `merge_commit_sha` de 40 caracteres hexadecimais. Base branch e
   base SHA devem ser verificáveis. Fork, head apagado ou campos ausentes
   não podem preencher evidências J3/J7.
2. **Head de branch ainda viva:** antes e depois do inventário, Work Units e
   checagem de CI, a branch de uma PR aberta precisa continuar apontando para
   o commit candidato. Se o ref mudou, a auditoria recusa. Para PR
   **já mergeada**, GitHub pode ter eliminado a branch: não consultar ref
   inexistente, usando a identidade e recibos reais do release observer.
3. **Inventário e proveniência:** o leitor mantém a verificação de cópia
   byte a byte de Work Units, ancestralidade validada, recibos de
   reconciliação, escopo de project/run e paths completos de Preview.
   Inventário vazio não atesta Preview N/A. Nenhum commit de outra run é
   promovido porque exista no repositório.
4. **Não misturar CI com outra revisão da PR:** `get_ci_state` consulta
   novamente o head internamente. Após esta chamada o auditor lê mais uma
   vez a PR inteira e o ref da branch ainda aberta. Mudança de SHA, base,
   origem, draft, merge ou ref entre snapshots resulta em falha explícita
   `unverifiable_live_evidence` do CLI — jamais `observed_complete`,
   `eligible` ou sucesso de Product Readiness. Não há GET atômico
   multi-recurso do GitHub; uma mudança e reversão entre consultas continua
   fora do que uma leitura pode provar.
5. **Regressões gratuitas:** testes sem rede e sem banco exercitam
   PR aberta/mergeada, branch deletada após merge, alteração de head
   durante consulta CI, alteração de base durante leitura de arquivos,
   branch movida, fork, draft, dados incompletos e parâmetros inválidos.
   `validate` e a matriz PostgreSQL descartável da Factory devem passar
   no SHA desta PR.

## Limite da prova

A evidência J3/J7 só é externa quando um Start genuíno em projeto
greenfield **explicitamente autorizado** produzir Work Units, branch,
commit, PR e CI por conta da Factory, e sua jornada atingir Preview
aplicável (ou N/A durável), `awaiting_release`, merge humano observado
e operações. A suite offline não substitui isso.

O projeto `infodive-service-desk` é produto real, não sandbox.
O canário histórico sem repo não é autorização para criar um novo.
Não reutilizar CRM/SQL/Service Desk como alvo de escrita para fabricar
PASS. Sem alvo autorizado ou ledger/capacidade verificados, reportar
`blocked_sandbox_not_authorized`.

Este patch não altera migrations, RLS, permissões, modelos, saldo,
Vercel ou pilotos. Merge na main/produção continua exclusivamente humano.
