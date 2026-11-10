# B1–B4: enforced focus contract

**Single objective:** certify the Factory's 19 real criteria, with durable evidence, not more PRs. This document complements [the binding certification plan](PLANO_CERTIFICACAO_19_CRITERIOS.md) and [the execution contract](FINALIZATION_EXECUTION_CONTRACT.md).

## In scope

Only `leandrosilveiradepaula/ai-product-factory`: B1 requirements, B2 security/runtime, B3 Console UX, B4 Factory autonomy and real journeys. Other projects (including CRM) can be evidence sources **read-only**; cross-repo changes require separate, explicit human authorization. Never re-open old CRM Change Sets, create synthetic Starts, run paid models to probe, weaken RLS, or auto-merge to production.

Before selecting work, reconcile AGENTS.md, PROJECT_PLAN.md, STATUS.md, OPERATIONS.md, AUTH_ACTIVATION_READINESS.md, MEMORY.md, main SHA, exact CI and the 19 persisted criteria in Supabase. Select acceptance based on a criterion's missing *independent* proof, not convenience. Deliver meaningful batches to PR, tests, CI; then request a single human merge when production would change.

## Required PR body contract

Each Factory PR must have lines (the text is metadata, **never an authorization**):

```text
Factory-Block: B2, B3
Factory-Criteria: functional_completeness/mock_noop_demo_inventory, product_experience/states
Factory-Intent: advance
Factory-Acceptance: Independent Supabase certification persisted at the exact main SHA with newly passed target criteria and no loss of previous PASS.
Factory-Scope: leandrosilveiradepaula/ai-product-factory
Factory-Cross-Repo: read-only
Factory-Human-Gates: human-review; production merge is never automated
```

If a previously approved criterion regressed and the task is limited to repairing it, set `Factory-Intent: repair-regression` and include `Factory-Incident: https://github.com/leandrosilveiradepaula/ai-product-factory/issues/NNN`.

The deterministic `scripts/check_block1_focus.py` rejects PRs whose exact commit, repository, main base, paths, declared block/criterion or human-gate declaration fail. Its approval **does not** prove the code actually implements the declared criterion, that an operational test has passed, that production access is safe, or that merging is authorized. Claims about new PASS require a *separate*, independently persisted certificate on the exact post-merge SHA.

## Rollout and protection

The `validate / test` job runs the focus check for all PRs, including edits to PR descriptions; it is skipped on pushes to `main`, where the existing independent certifier applies. The source of the checker is pinned to the PR BASE commit: candidate code cannot replace the checker at verification time. This initial bootstrap PR is the only exception (review the guard implementation carefully before human merge). No privileged token is supplied to candidate code.

Verify in GitHub **Settings → Rules → Rulesets** that the active `main` ruleset requires the GitHub Actions checks `test` and `factory-acceptance`, prevents bypass, and keeps human-only merge. A successful check cannot force human review or merge by itself. If GitHub check configuration or permissions are unavailable to the connected integration, do not claim those settings were changed.

This is **preventive CI scope validation**, not write permission restriction at the connector level. Enforce real cross-repo read-only permissions in the GitHub App installation or connector grant; the CI script cannot revoke a connector's API scopes. Bootstrap and future PR approvals remain human.

## Result reporting

Report `main_sha`, `certified_sha`, `passed/partial/missing`, exact regressed/gained criterion identities, and human gates. Green CI ≠ readiness; merely preserving 10/19 is zero certification progress. No CRM implementation, deployments or other projects unless a specific already-authorized real Factory journey explicitly requires them.
