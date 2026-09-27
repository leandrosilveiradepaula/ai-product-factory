# Factory Acceptance

Last updated: 2026-09-27.

This document defines the executable completion gate for the AI Product Factory itself.

The purpose of this gate is to distinguish **internal product completeness** from **external activation readiness**. A green Factory acceptance check means the deterministic platform, safety boundaries, workers, evidence flow and release model are implemented and regression-tested. It does **not** claim that externally blocked paid providers are enabled.

## Acceptance matrix

| Factory stage / capability | Executable evidence |
| --- | --- |
| Idea / intake | Factory Console intake, Control Plane project bootstrap and project/spec persistence are present in the repository and migrations. |
| Discovery | Lifecycle begins at Discovery and product-stage runtime can claim durable work. |
| Product Spec | Specification is a first-class lifecycle stage and is persisted through the product-stage pipeline. |
| Planning | Planning is a first-class stage and feeds durable executable backlog. |
| Backlog / routing | Dispatch worker and Direct-vs-Codex policy are wired independently from human-risk gates. |
| Implementation | Direct and selective Codex workers both produce through the existing GitHub delivery loop. |
| Review | Review is an explicit lifecycle stage; failed CI can return work to implementation. |
| Tests / evals | CI follow-up persists quality-gate evidence; deterministic unit/compile validation runs on every PR/push. |
| Preview | Preview is fail-closed by default, supports explicit non-applicability, and verifies exact candidate evidence when required. |
| Human merge gate | Runtime GitHub adapters intentionally contain no merge capability. Production merge is human-authorized. |
| Release | Release worker observes an already-merged PR and records evidence; it does not perform the merge. |
| Operations | Recovery, health and deduplicated operational alerts are wired into the scheduled runner. |
| Cost safety | Paid primary execution requires explicit enablement, known budget and per-run reservation. |
| Codex safety | Codex requires explicit enablement + official WIF values + identity token file + cross-repo GitHub credential. |
| Cross-repo safety | Native Actions token is repository-scoped; external repositories require `FACTORY_GITHUB_TOKEN`. |
| Benchmark safety | The Agent SQL 63-question benchmark is never an implicit Factory action. |

## What “internally complete” means

The Factory is internally complete when all of the following are true:

1. the normal `validate` job is green;
2. the dedicated `factory-acceptance` job is green;
3. Control Plane schema/migrations are reconciled with the repository;
4. Console production health is green;
5. there are no unresolved Factory code issues required for lifecycle correctness;
6. the runtime continues to fail closed for paid/external providers that are not administratively ready.

## External activation dependencies

These are **not missing implementation work**:

- OpenAI primary-model API quota/billing must be administratively approved before `FACTORY_PRIMARY_MODEL_ENABLED=true`;
- Codex managed-workspace Workload Identity Federation must provide real `OPENAI_FEDERATION_RULE_ID` and `OPENAI_WIF_AUDIENCE` values before `FACTORY_CODEX_ENABLED=true`;
- cross-repository execution requires a real `FACTORY_GITHUB_TOKEN` with the minimum required repository permissions;
- Supabase leaked-password protection remains an administrative hardening item.

The platform must remain useful and observable while those providers are blocked. Health/readiness should report the dependency; the runtime must not invent credentials, switch to unofficial tokens, or spend money merely to probe readiness.

## Release semantics

Production remains a human-authorized action. The user may provide standing authorization for merges, but the runtime itself still has no automatic merge capability. This preserves the architectural separation between implementation automation and production authority.

The release observer records a merge that has already occurred and advances durable state to operations.
