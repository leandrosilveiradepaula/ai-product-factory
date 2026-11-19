# Private SQL-InfoDive model — Factory integration

Source: Agente Financeiro (agente-sql-langgraph), specifically
app/integrations/openai_compatible/configuration.py and client.py, plus
docs/deployment/local-llm-smoke.md.

The Finance agent already uses a PRIVATE OpenAI-compatible Chat Completions
service in IBM Cloud over WireGuard. This is not the OpenAI Responses API.

Observed/historical settings, NOT verification from the Factory runner:
- provider_key = infodive_ibm_cloud
- POST /api/chat/completions
- Host HTTP header = chat.internal
- previously observed VPN base URL = http://10.66.66.1
- Authorization = Bearer token from the official secrets environment
- request = {model,messages,temperature:0,max_tokens:4096,stream:false}
- response = choices[0].message.content and usage token counters

**Important**: the exact runtime model ID must be reconciled with the
Finance environment's OPENAI_COMPATIBLE_SQL_MODEL. "SQL-InfoDive" is a
display label, not proof of the effective API model ID.

Implementation: private_chat_provider.py supplies a disabled-by-default
ModelProvider-compatible adapter with bounded requests/responses, private
IP validation, no redirect, no proxy, sanitized errors and offline tests.
It is not wired into Product Stage, Direct or Codex. Those workers remain
unchanged. No n8n workflow or finance data is accessed by the Factory.

Do not enable until ALL these external gates are satisfied:
1. A dedicated, least-privilege Factory bearer secret exists in a protected
   server-side environment; do not copy any token into code or browser.
2. That exact Factory execution host has an operator-approved private
   network path to IBM Cloud. GitHub-hosted Actions does not inherit the
   Finance VPS WireGuard tunnel; never make a public proxy or disable TLS.
3. Exact model ID, health and access policy are verified without model calls.
4. A SQL-specialist workflow is explicitly selected and independently
   evaluated; do not assume a SQL-focused model can plan or code products.
5. A human-approved input/output price (or explicitly certified zero
   marginal charge), current Control Plane cost ceiling, per-run reservation
   and durable tool_family=model ledger are mandatory. The optional
   private_model_metering.py wrapper implements this gate and records actual
   usage, but it is NOT registered with the scheduled worker. Unknown cost
   blocks paid use. A SQL-specific authorized worker and network route must
   be implemented and evaluated separately before any live use.
6. Only then perform an explicitly authorized bounded live invocation;
   record usage and review the evidence before production activation.

Environment variables (all intentionally UNSET in this change):
- FACTORY_SQL_INFODIVE_ENABLED (must be "true")
- FACTORY_SQL_INFODIVE_PRIVATE_ROUTE_ATTESTED (must be "true")
- FACTORY_SQL_INFODIVE_BASE_URL
- FACTORY_SQL_INFODIVE_MODEL
- FACTORY_SQL_INFODIVE_HTTP_HOST (optional)
- FACTORY_SQL_INFODIVE_ALLOW_PRIVATE_HTTP (must be "true" for VPN HTTP)
- FACTORY_SQL_INFODIVE_API_KEY (protected secret; never NEXT_PUBLIC_)
- FACTORY_SQL_INFODIVE_TIMEOUT_SECONDS (defaults to 180)
- FACTORY_SQL_INFODIVE_MAX_TOKENS (defaults to 4096)

No live API call, budget change, migration, worker deployment, production
merge, SQL execution or new recurring paid service is authorized here.

## Manual WireGuard network-only preflight

The workflow .github/workflows/sql-infodive-private-network.yml runs only
via workflow_dispatch on the exact main repository and protected GitHub
Environment ibm-private-llm. It does not receive the IBM model API bearer.
It prepares a minimally scoped ephemeral WireGuard peer, routes only the
private model IP /32 over factory-ibm, verifies interface and TCP reachability
without sending HTTP, removes the temporary peer key and records a sanitized
7-day SHA-bound artifact. A passing result proves network only, not a model,
pricing, SQL, credential, or production readiness assessment.

This workflow intentionally cannot run successfully until a private-network
administrator provisions a new dedicated Factory peer (do not reuse financial
Agent VPN keys) with least privilege and configures protected environment:

- Secret FACTORY_INFODIVE_WG_CLIENT_PRIVATE_KEY
- Variable FACTORY_INFODIVE_WG_PEER_PUBLIC_KEY
- Variable FACTORY_INFODIVE_WG_ENDPOINT (hostname:UDP-port)
- Variable FACTORY_INFODIVE_WG_CLIENT_ADDRESS (dedicated RFC1918 /32)
- Variable FACTORY_SQL_INFODIVE_BASE_URL (private API IPv4 base URL)
- Variable FACTORY_SQL_INFODIVE_MODEL (verified deployed model identifier)
- Variable FACTORY_SQL_INFODIVE_HTTP_HOST (actual Host header, optional)

Never put private keys or model credentials in PRs, workflows, artifacts,
project manifests, UI settings, or GitHub logs. Do not click Run workflow
before the dedicated VPN/access approval. A future SQL-specialist worker
still needs an independent API credential and pricing/ledger approval; the
general Product Stage/Direct/Codex routes remain untouched.
