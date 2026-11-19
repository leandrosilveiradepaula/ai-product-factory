# SQL-InfoDive na AI Product Factory — acesso DIRETO pela VPS

## Decisão arquitetural do operador (19/11/2026)

A Factory NÃO utilizará n8n nem LangGraph para acessar a LLM.
Os repositórios e conversas do Agente Financeiro são usados SOMENTE
para recuperar o contrato de conexão. Não importar workflows n8n,
não utilizar webhooks n8n, LangGraph, seus containers, ou tokens S2S.

O fluxo pretendido é:

  Factory Control Plane (fila, orçamento, auditoria, autorização)
         ↓ worker Python nativo da Factory, executando NA VPS
  VPS existente srv1319424 (interface wg-ibm já instalada)
         ↓ conexão direta pela rede privada WireGuard existente
  API SQL-InfoDive hospedada na IBM Cloud

Nenhum novo WireGuard peer, túnel no GitHub Actions ou proxy público
é necessário por esta arquitetura. O túnel EXISTENTE pode transportar
ambas as aplicações na mesma VPS, desde que o isolamento das credenciais
e os controles de acesso do host sejam mantidos. Não alterar o WireGuard
que atende o Agente Financeiro, não copiar arquivos/chaves e não ampliar
ACL/rede por conta própria. Os workers GitHub Actions permanecem no
caminho atual e NÃO chamarão diretamente o IP privado da IBM.

## Fonte do contrato, com datas e proveniência

Fontes consultadas:
- Histórico do projeto Agente Financeiro, 13/10, 06/11 e 09/11/2026.
- agente-sql-langgraph/app/integrations/openai_compatible/configuration.py,
  client.py (leitura documental, sem invocar LangGraph).
- docs/deployment/local-llm-smoke.md e
  docs/operations/N8N-OFFICIAL-SQL-INFODIVE-PROVIDER.md (leitura apenas;
  os IPs ilustrativos desta última NÃO são configuração real).

Valores históricos que foram efetivamente registrados nas conversas:
- Interface da VPS: wg-ibm, VPN split-tunnel.
- Peer WireGuard IBM: 52.118.255.226:51820/UDP.
- IP de túnel VPS: 10.66.66.6/32; rede privada 10.66.66.0/24.
- Serviço privado: 10.66.66.1; o roteamento era via wg-ibm.
- Endpoint: http://10.66.66.1/api/chat/completions
- Cabeçalho HTTP: Host: chat.internal
- Provedor: infodive_ibm_cloud; versão SQL:
  sql-infodive-ibm-cloud-v1; modelo reportado SQL-InfoDive.
- Segredo de API referenciado pelo nome OPENAI_COMPATIBLE_SQL_API_KEY
  (NUNCA copiar valor ou usar token n8n/LangGraph S2S).
- Em 06/11 e 09/11 houve evidência de handshake recente, TCP OK
  e HTTP 200 no fluxo privado. ISSO É HISTÓRICO, não revalida o
  serviço nem o token a partir deste novo worker.

O adaptador Factory usa contrato OpenAI-compatible Chat Completions
(model, messages, max_tokens, stream:false) e extrai
choices[0].message.content e usage. Não utilizar Responses API por
engano. Nome exato do modelo deve ser reconciliado em runtime sem
imprimir nenhum segredo.

## Código preparado nesta PR

- src/ai_product_factory/private_chat_provider.py:
  cliente HTTP direto com Bearer próprio e respostas sanitizadas.
  Apenas o transporte de produção exige a rota efetiva da VPS,
  antes de ler o token.
- src/ai_product_factory/private_model_vps_route.py:
  verifica localmente a rota do sistema com ip -json route get e
  exige dev=wg-ibm; recusa eth0/default e outros destinos públicos.
- scripts/sql_infodive_private_network.py --check-only:
  teste local NA VPS: rota + conexão TCP, sem chamada HTTP nem token.
  Nunca cria peer, executa SQL ou chama modelo.
- src/ai_product_factory/private_model_metering.py:
  preço aprovado e registro no ledger; verifica rede ANTES de
  reservar custo. Nenhuma credencial pública.
- Testes offline sem acesso ao provedor ou a VPS real.
- Não há provider selecionado implicitamente pelo Product Stage,
  Direct ou Codex.

## Configuração prevista para worker Factory na própria VPS

Variáveis de ambiente/secret do processo isolado Factory, não
necessariamente as mesmas do Agente Financeiro:

FACTORY_SQL_INFODIVE_BASE_URL=http://10.66.66.1
FACTORY_SQL_INFODIVE_HTTP_HOST=chat.internal
FACTORY_SQL_INFODIVE_MODEL=SQL-InfoDive (confirmar valor efetivo)
FACTORY_SQL_INFODIVE_WG_INTERFACE=wg-ibm
FACTORY_SQL_INFODIVE_ALLOW_PRIVATE_HTTP=true
FACTORY_SQL_INFODIVE_API_KEY=<segredo próprio da Factory, protegido>
FACTORY_SQL_INFODIVE_ENABLED=true (somente após gates)
FACTORY_SQL_INFODIVE_PRIVATE_ROUTE_ATTESTED=true (após prova no host)

O modelo não é grátis por presunção: definir taxas aprovadas
FACTORY_SQL_INFODIVE_PRICING_APPROVED, *_INPUT_USD_PER_MILLION e
*_OUTPUT_USD_PER_MILLION, com ledger/reserva real da Factory.
A política financeira e o teto do Control Plane não são alterados.

## Estado e dependências reais

A configuração histórica e o código não demonstram disponibilidade
atual do serviço privado na VPS. As tentativas de inspeção direta
com ferramentas administrativas retornaram exit code 1, sem prova
nova; não apresentar health do MCP como health da LLM.

Faltam:
1. Instalar/autenticar o worker Python DA FACTORY na VPS sob
   usuário/serviço isolado e configuração própria protegida.
   Publicação e credenciais/alteração de acesso exigem gate humano.
2. Executar o preflight --check-only NA VPS e registrar recibo
   datado de rota/TCP, sem chamada de modelo.
3. Integrar esse worker ao Control Plane através de fila durável
   e seleção explícita de tarefas elegíveis à SQL-InfoDive.
   Não executar SQL financeiro automaticamente.
4. Aprovar custo marginal/preços e verificar capacidade real.
5. Autorizar teste privado limitado, verificar uso e auditoria.
6. Merge/release de produção é exclusivamente humano.

Nenhuma chamada à IBM, n8n, LangGraph, compra de crédito, migration,
deploy ou merge ocorre nesta PR. Preview não se aplica fora
de apps/console/**.
