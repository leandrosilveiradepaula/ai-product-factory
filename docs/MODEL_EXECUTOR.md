# Model Executor

The factory separates execution routing from provider implementation.

- `PRIMARY`: the default reasoning/coding model used for most tasks.
- `CODEX`: a specialized coding executor used only when the Codex policy routes a task there.

Default budgets are deliberately conservative:

- up to 6 primary-model calls per task;
- up to 1 Codex call per task.

Provider credentials are never stored in the repository. If a provider is unavailable, the factory must continue deterministic work where possible and fail closed only for the model-dependent step.
