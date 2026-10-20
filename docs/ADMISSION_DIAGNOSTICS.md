# Read-only admission diagnosis — issue #987

Run from a protected server-side Actions environment with privileged Supabase credentials:

```sh
python -m ai_product_factory.runtime_cli --mode admission-diagnose --project-key ai-product-factory
python -m ai_product_factory.runtime_cli --mode admission-diagnose --project-key ai-product-factory --run-id 945c0da5-f36f-46da-a454-072037a988a5
```

Output is a bounded JSON observation, **not permission to dispatch**. `status` is `waiting`, `eligible`, `blocked` or `in_progress`, with a normalized `reason_code` and `next_step`. Project control (including draft/paused/stopped) always overrides queue observations. Eligibility for an unclaimed Work Unit requires the **existing** planned-work peek and portfolio selection RPCs, not task counters. The product-stage run is recognized from the durable queued run/task. Run IDs cannot cross projects. History does not become new work.

The CLI reads project, control, command, task, run, portfolio and planned-work records, the current authoritative primary budget policy and the complete cost ledger. It does not query descriptions/prompts, log tokens, claim leases, emit audit events, create runs/PRs, invoke models or dispatch CI. When paid ledger or policy is unavailable, Product Stage and dispatch are blocked; no fallback defaults. The diagnostic uses the existing readonly `factory_peek_planned_work` and `factory_portfolio_candidates` RPCs (HTTP POST to SQL read-only functions; not scheduler writes).

**Boundaries:** maximum 100 recent tasks, runs, commands and work candidates (101 requested for truncation detection); if any source exceeds the bound, the diagnostic raises an error rather than proclaiming an empty queue. Large projects need cursor pagination in a future version. This mode does not prove worker heartbeat or provider availability and does not claim universal product readiness. Preview for this Python-only change is **N/A**, to be recorded on its PR; no Console files were changed.

Offline validation: `python -m unittest tests.test_admission_diagnostics`. Use GitHub CI for exact commit evidence. Production merge remains human, and production migrations are not needed.


## Execução operacional segura (20/10/2026)

Quando o conector GitHub não fornecer workflow_dispatch, um operador OWNER pode emitir em uma issue do repositório da Factory o comentário exato:

```text
/factory-admission-diagnose ai-product-factory
/factory-admission-diagnose ai-product-factory 945c0da5-f36f-46da-a454-072037a988a5
```

Use um comando **por comentário**. O workflow existente `Factory autonomous runner` usa o job isolado `admission-readonly`, valida o OWNER e a sintaxe **antes** de solicitar OIDC e preserva o artefato `factory-admission-diagnosis-<workflow_id>` por sete dias. Nesse evento, `schedule-probe` e todos os seus descendentes são SKIPPED. Não confundir um job da auditoria bem-sucedido com trabalho despachado.

O diagnóstico exclui a classe histórica `preview_ready` cuja fonte é `dogfood_manual_audit` das pendências de entrega. Uma run exata desta classe pode ser consultada, mas responde `historical_preview_audit_only`, sem reativá-la. Trabalho roteado para Direct/Codex e ainda não claimed indica `routed_execution_not_yet_claimed` e **não** autorização para execução de Product Stage. `in_progress` requer recibo de `started_at` da própria run, nunca heartbeat do cron.

Saída estruturada contém apenas IDs, estado e versão do controle, razão, próxima etapa, contadores limitados e código normalizado do ledger. `eligibility_scope=database_observation_not_claim_authorization` e `product_ready=false` são intencionais: o worker faz suas próprias checagens de credencial, budget e epoch. Falhas inesperadas geram JSON sanitizado `unverifiable_live_evidence` e exit code 2, não logs de HTTP/token/prompt. Esses relatórios não fazem chamadas pagas nem gravações no Control Plane.
