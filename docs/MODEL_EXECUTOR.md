# Model Executor

The factory separates execution routing from provider implementation.

- `PRIMARY`: the default reasoning/coding model used for most tasks.
- `CODEX`: a specialized coding executor used only when the Codex policy routes a task there.

Default budgets are deliberately conservative:

- up to 6 primary-model calls per task;
- up to 1 Codex call per task.

Provider credentials are never stored in the repository. If a provider is unavailable, the factory must continue deterministic work where possible and fail closed only for the model-dependent step.

## Optional private SQL specialist

SQL-InfoDive (IBM Cloud) has an opt-in Chat Completions adapter, not registered in the runtime. It needs private-network/credential and cost-ledger approval before any live selection. See [SQL-InfoDive integration](SQL_INFODIVE_FACTORY_PROVIDER.md).
