# SQL-InfoDive (IBM Cloud) — LLM de propósito geral na Factory

## Decisão atual de produto — 19/11/2026

SQL-InfoDive é o NOME do modelo, não uma restrição ao domínio SQL.
O modelo é uma LLM de propósito geral. A Factory poderá escolher esse
provedor para Discovery, Product Spec, planejamento e implementação
direta, usando o mesmo contrato de tarefas, testes e gates dos demais
provedores. A adequação e qualidade das respostas por tipo de tarefa
ainda exigem evals reais; não presumir uma aprovação apenas pelo nome.

O caminho de inferência oficial é:

Factory Python / Supabase Control Plane
   -> worker Python NATIVO da Factory na VPS Infodive
   -> interface WireGuard wg-ibm JÁ EXISTENTE na VPS
   -> API Chat Completions SQL-InfoDive na IBM Cloud

Não utilizar n8n nem LangGraph em nenhuma etapa do acesso da Factory.
Os dois projetos serviram apenas como referência documental de configuração.
Não migrar dados financeiros, não executar SQL financeiro e não copiar
credenciais desses serviços.

## Fonte e protocolo

Observação histórica do Agente Financeiro (não prova de conectividade atual):
- Modelo apresentado como SQL-InfoDive, provedor infodive_ibm_cloud.
- Configuração de origem: app/integrations/openai_compatible/configuration.py
  e client.py do repo agente-sql-langgraph; referências datadas 06 e 09/11.
- VPN da VPS: wg-ibm, endereço do host documentado 10.66.66.6/32,
  peer IBM histórico 52.118.255.226:51820/UDP.
- Serviço privado histórico 10.66.66.1.
- POST http://10.66.66.1/api/chat/completions
- Host: chat.internal
- Authorization: Bearer <credencial dedicada da Factory, server-side>
- Resposta: choices[0].message.content, usage.prompt_tokens e
  usage.completion_tokens. A Factory exige usage para contabilizar custo.

A prova de rota deve ser executada no processo real na VPS: o executor
administrativo remoto retornou erro de netlink e um HEAD sem credencial
atingiu timeout de TCP. Esses resultados NÃO provam que a VPN do host
ou a API estejam indisponíveis. O gateway MCP da VPS está saudável,
mas isso também não comprova o endpoint IBM.

## Estado do código na PR #1527

- Cliente privado Python, sem proxy HTTP, redirects ou endpoint público,
  com Bearer próprio, erro sanitizado e limites de timeout/saída.
- Provider opt-in por FACTORY_PRIMARY_MODEL_PROVIDER=infodive_ibm_cloud.
  Valor default openai permanece. Não há fallback silencioso entre modelos.
- Suporte a ModelRequest.output_schema como instrução JSON no protocolo
  Chat Completions, sem pressupor suporte a response_format da OpenAI.
- Product Stage: usa a fila existente factory_claim_next_run com CAS e
  checkpoints de execução; não cria fila sintética ou outro Start.
- Direct: usa o roteamento, claim, lease, PR e quality gates existentes.
  O perfil do agente atribuído deve trazer model_policy.provider igual
  a infodive_ibm_cloud e model_policy.enabled booleano true, configurado
  pelo operador no Control Plane. Perfil de outro provedor não autoriza
  uso da IBM mesmo que o worker esteja disponível.
- Validação da rota wg-ibm e TCP ANTES de qualquer claim, token ou gasto.
  O cliente revalida rota antes de ler a credencial para cada chamada.
- Reuso de ledger/custo Primary atual: taxa de entrada e saída aprovada,
  reserva por execução, custo observado e bloqueio de custo desconhecido.
  O teto financeiro é cumulativo entre provedores; IBM não contorna saldo.
- CLI de preflight sem LLM e template systemd inerte. Nenhum serviço real
  da Factory foi instalado na VPS.
- Testes offline usam transportes injetados. Não houve requisição paga,
  instalação de peer WireGuard, modificação na produção nem migration.

## Configuração futura exclusiva do processo VPS

Todas as variáveis abaixo são server-side em arquivo legível somente por
usuário/serviço dedicado à Factory (nunca NEXT_PUBLIC_, browser ou GitHub
Actions; não reutilizar chaves n8n/LangGraph/Agente Financeiro):

FACTORY_PRIMARY_MODEL_PROVIDER=infodive_ibm_cloud
FACTORY_INFODIVE_VPS_WORKER_ENABLED=true
FACTORY_PRIMARY_MODEL_ENABLED=true
FACTORY_SQL_INFODIVE_ENABLED=true
FACTORY_SQL_INFODIVE_PRIVATE_ROUTE_ATTESTED=true
FACTORY_SQL_INFODIVE_WORKER_SHA=<SHA exato do checkout Factory na VPS>
FACTORY_SQL_INFODIVE_BASE_URL=http://10.66.66.1
FACTORY_SQL_INFODIVE_HTTP_HOST=chat.internal
FACTORY_SQL_INFODIVE_MODEL=<ID real do modelo, confirmar>
FACTORY_SQL_INFODIVE_WG_INTERFACE=wg-ibm
FACTORY_SQL_INFODIVE_ALLOW_PRIVATE_HTTP=true
FACTORY_SQL_INFODIVE_API_KEY=<nova credencial protegida dedicada Factory>
FACTORY_SQL_INFODIVE_PRICING_APPROVED=true
FACTORY_SQL_INFODIVE_INPUT_USD_PER_MILLION=<preço aprovado>
FACTORY_SQL_INFODIVE_OUTPUT_USD_PER_MILLION=<preço aprovado>

Além disso: SUPABASE_URL, SUPABASE_SECRET_KEY (ou service_role legado),
credencial GitHub cross-repo adequada e agente atribuído autorizado.
O prefixo SQL nas variáveis existentes é uma herança de identificação
do modelo; NÃO delimita tarefas que ele pode desempenhar.

Preflight no checkout instalado e aprovado:

python scripts/factory_sql_infodive_vps_worker.py --preflight-only --tcp

O resultado preflight_ready apenas comprova pré-requisitos de configuração,
reconciliação de SHA, rota/TCP e orçamento. Não garante capacidade da API
nem autorização de execução de um run. A CLI não faz chamadas de modelo
nem claims. A rotina de produção deve usar o runtime_cli já existente,
por exemplo --mode direct (perfil autorizado) e --mode product, conforme
a política e o Control Plane. O template systemd incluído permanece
DESABILITADO e requer adaptação ao host.

## Gates para ativação e primeira prova real

1. Merge de produção é EXCLUSIVAMENTE humano. A PR está em draft.
2. Confirmar rota wg-ibm e TCP a partir do próprio worker, sem model call.
3. Instalar o worker isolado da Factory na VPS, com serviço, conta, env e
   escopo mínimos revisados (alteração de produção/acesso sensível).
4. Provisionar token próprio e confirmar o ID atual da LLM; não reciclar
   token do Agente Financeiro.
5. Aprovar preços efetivos (inclusive 0 apenas se marginalmente gratuito
   e explicitamente comprovado); o teto interno histórico US$15 está
   esgotado para a reserva US$0,50. Nenhuma ampliação implícita é aceita.
6. Vincular o perfil de agente autorizado ao provider no Control Plane
   e verificar um run elegível; não disparar trabalho de outro projeto.
7. Autorizar uma chamada real delimitada, conferir resposta, usage e
   recibo de custo, executar evals por tipo de tarefa e qualificar a
   adequação do modelo antes de tratar a integração como operacional.

A seleção por env da VPS não altera a configuração do GitHub-hosted runner.
Não adicionar saldo automaticamente, não auto-merge, não executar benchmark
de 63 perguntas e não declarar product_ready por causa desse preflight.

## Atualização operacional — 20/11/2026 (Direct nativo na VPS)

A PR #1545 foi mergeada humanamente (main `5cbc68277b37a1f45cf8fd2950d2dc171576f433`),
e o Product Stage da VPS foi verificado em execução agendada real.
O Direct permanece **desabilitado**. O GitHub App do CRM/Dark Channel é
emitido via broker OIDC do GitHub Actions, que não fornece identidade OIDC
à VPS. A VPN IBM, a credencial do modelo e o Supabase não concedem acesso
de escrita GitHub cross-repository. Não tentar reaproveitar GITHUB_TOKEN.

Antes de qualquer claim Direct, inclusive na VPS, o runtime exige:
1. binding exato run → task → projeto → repositório ativo na fila do Control Plane;
2. autorização GitHub do projeto em estado `ready` e capacidades verificadas
   `contents_write`, `issues_write`, `pull_requests_write` para cross-repo;
3. no native IBM VPS, token `FACTORY_GITHUB_TOKEN` explícito, mantido
   somente server-side e nunca enviado à LLM, ao browser ou ao código gerado;
4. leitura autenticada do repositório GitHub retornando `full_name` e `id`
   correspondentes ao alvo, e permissão de push quando publicada pela API;
5. agente Direct com `github_write`/`model_primary`, `model_policy.provider=infodive_ibm_cloud`
   e `model_policy.enabled=true`, além do orçamento e da rota privada.

Um bloqueio de credencial retorna `blocked_github_credential` antes do
claim, sem gastar tokens, escrever branches ou consumir tentativas.
Os timers Direct **não devem** ser ativados sem validação real do token
escopado e da política do agente. O GitHub App existente não autoriza
emitir tokens em nome da VPS fora do broker já restrito ao GitHub Actions;
qualquer novo mecanismo de identidade para VPS é alteração sensível
sujeita a gate humano.
