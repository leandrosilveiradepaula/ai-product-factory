# Product Stage readiness evidence — 2026-10-15

A scheduled GitHub Actions job can pass while product work remains queued because paid-model execution is intentionally disabled. The new product-readiness-evidence CLI mode executes before the paid worker and is an explicit prerequisite for it. This mode never calls an LLM or changes runtime state.

Preflight reasons: model_disabled, primary_auth_missing, budget_not_configured, cost_ledger_unavailable, paid_cost_unknown, budget_exhausted. No exception contents, credentials or token values appear in audit or output. A pending created/queued run with a queued task and active project receives append-only product.worker_blocked evidence linked to its existing project/task/run IDs and trusted Actions run ID. Identical reasons are deduplicated for 30 minutes; transitions are not. Queries and number of records are bounded; audit failures fail closed.

GitHub Actions emits an explicit warning and a summary saying the Product Stage was blocked rather than executed. The Console reads this run-specific audit and renders the reason in pt-BR, without claiming that a global scheduler wake proves worker execution. Historical evidence is timestamped and is not a live billing probe.

No change to model enablement, quota, budgets, reservation amount, GitHub App access, merges or Preview policy. The existing fixed Factory budget remains US$4.00, reserve US$0.50 per call. The preflight only reads the existing cost ledger; it is not an atomic cost reservation. Concurrent paid workers may still race between budget check and reservation. This requires a separate transactional RPC and reviewed production migration, and is **not** claimed resolved here.

The initial Service Desk work item stays unchanged until an authorized worker actually claims it. GitHub App installation in the Factory repo and the current Vercel dispatch credential remain unverified. Native cron is best-effort, not an immediate delivery guarantee.
