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
