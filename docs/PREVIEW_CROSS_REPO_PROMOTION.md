# Preview cross-repo — promoção opt-in com CAS (Prova 2)

Objetivo: a Factory deve publicar e verificar Preview apenas quando há um candidato CI/Security/QA/Operations aprovado, sem deployment de branches intermediárias. A promoção não é merge, não toca main, não autoriza release e não consome modelo pago.

## Política server-side por projeto

A configuração confiável do projeto deve incluir a seguinte seção em manifest.preview (o exemplo é do projeto atual, NÃO é hardcode no runtime):

~~~json
{
  "provider": "vercel",
  "mode": "github",
  "required": true,
  "promotion": {
    "mode": "github_ref_cas",
    "enabled": true,
    "source": "change_set",
    "branch_prefix": "preview/factory-cs",
    "base_ref": "preview/hardening-release-candidate",
    "max_ahead_commits": 8
  }
}
~~~

Outros projetos podem escolher source=pull_request, outra base e outro prefixo dentro de preview/**. O projeto precisa autorizar explicitamente o uso de sua namespace Preview e a credencial GitHub App/FACTORY_GITHUB_TOKEN deve possuir a permissão mínima já aprovada para o repositório. Não adicionar políticas RLS públicas nem enviar tokens ao browser.

Sem política, o caminho legado apenas consulta deployments existentes: nenhuma referência Git é escrita. Política inválida/desabilitada bloqueia promoção e release. Preview explicitamente N/A continua gerando recibo N/A, nunca deployment fictício.

## Contrato de segurança da execução

1. Conferir run preview_ready, qualidade, projeto ativo/geração, PR aberto e não draft, base e head SHA exatos, mesmo repositório e CI nativa verde. Compare GitHub deve provar ancestrais, ahead bounded e zero behind.
2. Antes de escrever: recibo de intenção no Control Plane, revalidação de epoch/PR/CI e bloqueio por status Vercel de rate limit. Nenhuma chamada de modelo.
3. Se a branch Preview reservada não existe, criá-la na base verificada; só depois avançar. Se já aponta ao candidato, não gerar push novamente. Drift concorrente bloqueia.
4. O avanço usa GraphQL updateRef com expectedOid e force:false, com retorno SHA-exato. Não substituir por REST PATCH sem CAS. A Factory nunca executa merge.
5. Reutilizar GitHubVercelPreviewAdapter, DurablePreviewAdapter e VerifiedPreviewCoordinator. Sem Vercel READY para o SHA, manter preview_ready e registrar preview.deployment_pending (sem falso PASS). Só navegador Playwright real e política de release podem liberar awaiting_release.
6. Merge de produção é humano, sempre; PR com base preview/** exige observação independente de merge não-prod e evidência de navegador pós-merge.

## Evidência operacional (25/10/2026)

Factory #1095 foi mergeada; CRM #197 head ae7fbb3143f677b555fc862926f17b033b7df6fb teve CI verde e especialistas aprovados na Factory. Preview falhou em #40199162918: Vercel GitHub Preview was not discoverable for the candidate commit. O último deployment READY da Vercel corresponde à base 0429872652e8cb2bc0e9cde618bf5e848190e186, não ao candidato.

O CRM usa vercel.json deploymentEnabled com main=true e preview/**=true, demais branches=false. A referência histórica curta preview/factory-cs-673a2fc7 continua na base; a nova política usa o UUID completo para evitar colisões de nome. Houve bloqueio de segurança ao tentar atualizá-la por ferramenta: NÃO contornar com outra API/client. O código desta PR permanece inerte até merge humano e autorização de política/credenciais. A PR do CRM não foi mergeada, nenhuma produção alterada. Não declarar Prova 2 PASS sem deployment e browser do SHA real.

## Testes

tests/test_preview_candidate_promotion.py testa política, projeto genérico, SHA/PR drift, CI, quota, geração, concorrência, GraphQL expectedOid e replay. Exigir CI e acceptance da Factory verdes no HEAD desta PR. Nenhuma migration, deploy, recarga de créditos, benchmark do Agente SQL ou chamada paga de sondagem neste patch.
