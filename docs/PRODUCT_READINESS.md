# Product Readiness Contract

Last updated: 2026-10-07.

## Why this exists

The Factory previously had an ambiguity: a green task/release path could be described conversationally as if the entire product were complete. That is unsafe for an app factory because local delivery evidence does not prove global product readiness.

This contract makes the scope explicit and fail-closed.

## Readiness scopes

| Scope | Meaning | What it does NOT mean |
| --- | --- | --- |
| `work_item_complete` | The current task/change set satisfied its acceptance criteria and evidence. | The app is complete. |
| `release_candidate_ready` | The exact candidate SHA passed the applicable release gates and can wait for human production release. | The product was globally audited. |
| `release_completed` | A human production release was observed and reconciled. | The whole product is secure, operable and finished. |
| `product_ready` | A current full-product audit passed all required product readiness domains with no critical blockers. | Permanent perfection; future changes can invalidate readiness. |

The Factory must never infer `product_ready` from CI, Preview, a merged PR, a completed task, zero pending gates, zero open issues, or a successful release alone.

## Required evidence for product_ready

A product can be called ready only when a full-product assessment has current evidence for all applicable domains:

1. **security** — authn/authz, tenant isolation, secrets, public surfaces, dependency/supply-chain and data access boundaries;
2. **observability_operations** — health/readiness, error aggregation, logs/traceability, alerting, recovery/runbook and critical integrations;
3. **test_strategy** — representative unit/integration coverage plus E2E of critical journeys and regression gates;
4. **product_experience** — information architecture, UI consistency, loading/error/empty states, responsiveness and accessibility for products with a user interface;
5. **documentation** — setup, configuration, operational ownership, known limitations and release/rollback guidance;
6. **functional_completeness** — no known mock/no-op/demo path presented as a finished production feature and no unresolved critical requirement blocker.

Each domain must also declare a `verification_state` describing how the evidence was validated. Merely configuring a gate or tool is not execution evidence.

Allowed verification states are domain-specific:
- `security`: `executed` or `reviewed`;
- `observability_operations`: `executed` or `observed`;
- `test_strategy`: `executed` only;
- `product_experience`: `observed` or `reviewed`;
- `documentation`: `reviewed`;
- `functional_completeness`: `executed`, `observed`, or `reviewed`.

For `test_strategy`, a workflow that exists but did not run for the assessed SHA is not valid evidence.

If a domain is genuinely not applicable, that non-applicability must be explicit, reviewed, and evidenced; silence is not a pass.

## Existing-project rule

Imported/existing projects require a baseline audit before the Factory may make a global completion claim. The audit must look beyond the current change scope because inherited debt can exist outside changed files.

## Release report semantics

Release reports describe the **candidate/release**, not the entire product. They must carry `readiness_scope=release_candidate` and must not set `product_complete=true` unless a separate full-product readiness assessment is present and passing.

## Human-facing language

Allowed without a product audit:

- "this task is complete";
- "this candidate is ready for human release";
- "the release completed";
- "the core architecture is implemented, with these remaining blockers".

Disallowed without a passing product audit:

- "the app is ready";
- "the product is complete";
- "100% finished";
- "only external credential X remains" when other readiness domains have not been globally assessed.
