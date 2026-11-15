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
- Não encontrado: a tela de execução inexistente mostra a recuperação real;
  a API autenticada de existência desse **mesmo UUID** responde HTTP 404.
  O documento HTML pode ter HTTP 200 se o Next.js já iniciou streaming;
  o endpoint retorna 503, e nunca 404, se o Control Plane falhar.
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

## 15/11/2026 — Diagnóstico após #1455

O run protegido #43734306960 concluiu SUCCESS, WCAG/surface e limpeza do
operador, mas **não** emitiu o artefato de sete estados: a falha isolada foi
`b3_real_states_route_status_mismatch_missing_run`. O Next.js pode retornar
HTTP 200 para uma página de `notFound()` emitida após streaming da shell;
isso não transforma o recurso inexistente em válido. A prova atual exige
dois sinais reais do **mesmo UUID**: UI com página inacessível e API de
existência com HTTP 404. A API é protegida por operador autenticado, lê
somente a existência do run e retorna 503 quando o Control Plane falha,
sem fabricar 404 nem expor conteúdo de projeto.
Também foi alinhado o contrato emitido pelo produtor JS com o verificador
independente Python, incluindo `pendingHumanGateCount=0`. Até novo recibo
completo e certificação persistida, o critério continua não aprovado.

## Certificação pós-merge: preservação de PASS anterior

O run #43734829661 (trigger visual após #1455) não persistiu o certificado,
por proteção correta do `readiness_prewrite_guard`: o coletor B1/B4 perdeu
`observability_operations/recovery_alerting` após alteração em
`supabase_operational_health.py`, mas o recibo anterior já tinha PASS. A
referência imutável do verificador foi reconciliada com o run **agendado**
#43707075595 (main `2bdbcb5c…`), que concluiu SUCCESS, com
`schedule-probe` e `alerts` SUCCESS e os sete blobs operacionais iguais
aos do SHA `06d02f72…`. Testes negativos de SHA, run/evento e drift
continuam exigidos. **Não** foi desligado o gate de monotonicidade.
Novo PASS para states depende do novo browser real e do certificado persistido.

## 15/11/2026 — Execução pós-merge #1456, loading real

A captura #43747033345 foi concluída SUCCESS (superfície, WCAG, prova
B2 assinada, limpeza de operador), mas o artefato de sete estados não foi
emitido. Código de falha sanitizado: `b3_real_states_loading_not_rendered`.
A prova utilizava `page.goto('/')`, uma navegação de documento inteiro;
esta ação não provoca necessariamente o fallback `app/loading.tsx` do
App Router durante transições clientes. A correção usa **clique em Link
real visível para /runs** com Chromium limitado a transporte HTTP real,
cache desabilitado e prefetch de páginas autenticadas desativado.
Exige ainda GET primeiro-partido de /runs, fallback acessível visível,
conteúdo final renderizado e transição sem mutação. A prova de erro offline
é feita a partir de um novo documento, menu avançado realmente aberto e
novo clique não-prefetched; conexão restaurada e botão de retry são
verificados sem interceptação/HTTP artificial. A suíte de integração executa
o **Next/React de produção com servidor local inert** para reproduzir
loading/offline/retry; essa fixture não é por si um PASS de certificação.
Nenhum critério é promovido antes de nova captura autenticada em produção.
