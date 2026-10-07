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

1. **security** — authn/authz, tenant/data access boundaries, secrets and dependency/supply-chain boundaries;
2. **observability_operations** — health/readiness, traceability, recovery and alerting;
3. **test_strategy** — representative unit/integration coverage, critical E2E and regression gates;
4. **product_experience** — full surface inventory, responsive coverage, accessibility and loading/error/empty states for products with a user interface;
5. **documentation** — setup/configuration, operations and release/rollback guidance;
6. **functional_completeness** — requirements inventory, mock/no-op/demo inventory and critical journeys.

A domain marked `passed` must provide all of:
- at least one non-empty evidence reference;
- explicit `coverage` entries for every required dimension of that domain; and
- an explicit `verification_state` proving how that evidence was validated.

Allowed verification states are domain-specific:
- `security`: `executed` or `reviewed`;
- `observability_operations`: `executed` or `observed`;
- `test_strategy`: `executed` only;
- `product_experience`: `observed` or `reviewed`;
- `documentation`: `reviewed`;
- `functional_completeness`: `executed`, `observed`, or `reviewed`.

For `test_strategy`, a configured workflow that did not execute for the assessed SHA is not evidence. A `not_applicable` domain also requires an allowed verification state and non-empty evidence.

This is deliberate. Evidence such as "reviewed", one screenshot, one green PR or one manually inspected screen is not sufficient to prove a whole-product domain. The coverage contract forces the assessment to say what was actually checked.

If a domain is genuinely not applicable, that non-applicability must be explicit and evidenced with a reason; silence is not a pass.

## Coverage keys

| Domain | Required coverage |
| --- | --- |
| security | `authn_authz`, `data_access_boundaries`, `secrets_dependencies` |
| observability_operations | `health`, `traceability`, `recovery_alerting` |
| test_strategy | `unit_integration`, `critical_e2e`, `regression_gates` |
| product_experience | `surface_inventory`, `responsive`, `accessibility`, `states` |
| documentation | `setup_configuration`, `operations`, `release_rollback` |
| functional_completeness | `requirements_inventory`, `mock_noop_demo_inventory`, `critical_journeys` |

Project-specific automated audits are encouraged as evidence but are not universally hardcoded. A headless service may mark product experience not applicable with explicit rationale; a UI product cannot skip responsive/accessibility/state coverage just because CI is green.

## Existing-project rule

Imported/existing projects require a baseline audit before the Factory may make a global completion claim. The audit must look beyond the current change scope because inherited debt can exist outside changed files.

The CRM dogfood demonstrated why: multiple manual UI passes still left hundreds of mechanically detectable surface issues until the repository was scanned globally. Readiness evidence therefore needs coverage, not merely a positive assertion.

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
