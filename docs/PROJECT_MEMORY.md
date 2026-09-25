# Project Memory

Each onboarded project can carry persistent, versioned product memory under `.factory/`:

- `product.json`: user goal, scope, acceptance criteria and product constraints;
- `architecture.json`: architecture and integration decisions;
- `current-state.json`: current lifecycle stage, status and observed repository head;
- `decisions/*.json`: immutable decision records.

This memory complements the central Supabase control plane. Repository memory travels with the code and is reviewable in PRs; Supabase tracks operational runs and cross-project state.

Secrets, credentials, tokens and raw sensitive payloads must never be stored in project memory.
