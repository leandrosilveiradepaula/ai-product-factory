# B3 — Matriz real de estados autenticados do Console (17º critério)

**Critério:** product_experience/states. O verificador anterior da Factory
atestava somente quatro transições React alimentadas por GETs interceptados e
uma única observação da API real. Ambos eram corretamente PARTIAL.

## Nova prova obrigatória

O workflow oficial Authenticated Console visual evidence, com operador efêmero
Supabase Auth, captura um artefato sanitizado separado e exige todas as
observações abaixo no **mesmo** run autenticado, no Console realmente servido:

- Sucesso: GET real da Visão geral, com conteúdo autenticado renderizado.
- Vazio: GET de /api/human-attention com 200 e contagem real zero, com ausência
  do contador visual de decisões.
- Loading: fallback acessível do Next.js durante navegação com **latência
  Chromium real**; o script não intercepta nem substitui respostas de API.
- Acesso negado: operador de visualização alcança a tela real /unauthorized,
  sem ganhar privilégios administrativos.
- Não encontrado: GET real de UUID de run inexistente retorna 404 e mostra
  a tela amigável de recuperação.
- Erro de conexão: offline real do Chrome durante navegação, mostrando a
  superfície acessível de erro/retry do Console. Não é um HTTP 503 simulado.
- Recuperação: conexão restaurada e clique real em Tentar novamente alcança
  uma rota funcional.

Proibido usar request.route(), route.fulfill(), HTTP 503 artificial,
resposta mockada, alteração de banco ou Start fictício para gerar PASS.
Nenhum corpo de API, texto de projeto, cookie, JWT, credencial, screenshot,
histórico do operador ou dado pessoal entra no artefato. O modo desconectado
não prova um incidente de indisponibilidade do backend; o recibo declara
backendOutageClaimed=false explicitamente.

## Gate independente

O produtor cria block1-b3-real-states-witness.json **somente se todas as
etapas terminarem**. A ausência ou erro mantém o critério PARTIAL ou MISSING
e a captura das demais superfícies e WCAG continua executável.

O módulo independent_b3_real_states_evidence.py exige em conjunto:

1. captura de Console autenticada e bem-sucedida;
2. prova de todas as rotas/responsividade real, subárvore Console/serviço
   reconciliada com o SHA avaliado;
3. as provas B2/B3 de entrada real e resposta do backend da mesma captura;
4. artifact GitHub não expirado, namespace, workflow_run, SHA e arquivo exatos;
5. todas as sete observações reais, fonte declarada por estado e contadores
   de escrita, interceptação, erro inesperado e chamadas pagas iguais a zero.

O builder conservador e o certifier reexecutam o verificador independentes,
antes de aceitar testado e persistido. Um JSON adulterado não consegue gerar
PASS diretamente; o verificador retorna VerifiedCriterionEvidence vinculado
ao SHA atual e um recibo auditável. O certificado global ainda permanece
NOT_READY até 19/19.

## Execução após merge humano da Factory

1. Confirmar CI de validação e integridade no SHA da main.
2. Confirmar Console em produção com health, subárvore de código e commit
   servido verificados.
3. No Actions, iniciar um **novo** workflow_dispatch de
   Authenticated Console visual evidence, com target_url oficial. Esse fluxo
   já usa OIDC e cria/remover operador temporário sem expor credenciais.
4. Confirmar resultado da matriz e sua versão do artefato sanitizado.
   Se não houver matriz completa, investigar a etapa real que falhou; **não**
   reusar fixture, relaxar tolerâncias ou reclassificar como sucesso.
5. Executar o fluxo independente de certificação no SHA corrente com
   flags existentes --verify-complete-console-surface e
   --verify-live-console-boundaries. Antes da escrita, reler os recibos,
   jobs de captura e provenance GitHub + Control Plane.
6. O 17/19 só existe quando o Control Plane persistir a avaliação
   product_experience/states=passed. Merge/CI verde, print local ou Vercel
   READY não contam.

Este pacote **não toca** Supabase migration/RLS, release, merges,
habilitação de modelo, custos ou o produto piloto. Gate de merge da Factory
continua humano.

## Evidência de 15/11/2026 — pós-merge #1453

O run autenticado #43731168060 preservou B2 assinado e 57 denials, mas falhou
antes de concluir: o contrato de leitura exigia UUID de idempotência antes de
qualquer submissão, enquanto o controle de projeto corretamente inicia vazio.
Agora o formulário é uma fronteira cliente única para clique, teclado e
requestSubmit; o auditor read-only exige UUID ainda **não** alocado.
A matriz real também reportou `b3_real_states_route_status_mismatch`: a
próxima execução identifica qual rota falhou sem persistir URL/conta/dados.
Nenhuma ausência de prova será classificada como PASS.

O verificador do Preview greenfield envia os cabeçalhos suportados pela
Vercel somente para requisições do host exato, sem interceptar/mocar respostas,
sem suprimir erros reais de app e sem encaminhar OIDC a domínios terceiros.
A conclusão depende de nova captura real, CI verde e gate humano de merge.
