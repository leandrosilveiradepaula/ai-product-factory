# Block 1 — independent runtime security observations (2026-11-06 UTC)

**Status:** candidate PR evidence, not a Product Readiness certification. Source of truth remains Control Plane post-human-merge, not this document.

## PostgreSQL effective roles — executed against Factory project

Project `fjplmxfcshhbmzgvyqlm`. Read-only role simulations were run directly through the connected Supabase SQL executor, using `BEGIN TRANSACTION READ ONLY`, `SET LOCAL ROLE`, transaction-scoped `request.jwt.claim.sub` and `ROLLBACK`. No users, grants, policies, or data were changed.

| Negative / positive scenario | Independently observed outcome |
| --- | --- |
| Anonymous read of `factory_console_operators` | PostgreSQL SQLSTATE `42501`, permission denied |
| Authenticated role without subject | Zero operators visible |
| Authenticated role with unknown UUID | Zero operators visible |
| Authenticated role with selected active operator subject | Exactly one active operator visible; row belongs to subject |

Reproducible SQL: `scripts/audit_block1_rls_role_probes.sql`. It emits only boolean probes, not identifiers. The connected SQL runner returns only the final result set when given the whole SQL file; execute each transaction individually to retain four independent output rows. The active-operator transaction was executed independently and returned `passed=true`. The anonymous deny, missing subject, and unknown subject were observed independently in separate queries.

**Limitations:** Postgres role/claim simulation is not a signed Supabase JWT, browser session, or cross-repository tenant E2E test. Do not label `security/authn_authz` or `security/data_access_boundaries` certified based on these probes. The direct anonymous deny occurs intentionally and may be reported as an error by SQL clients.

## Independent Gitleaks scanner

`.github/workflows/block1-independent-secrets.yml` uses pinned `gitleaks/gitleaks-action` (GitHub `contents: read`, no persisted checkout credential, no commenting and no secret-bearing artifact). The action runs on each PR and manual dispatch. Logs from PR #1251 run [42150970003](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/42150970003) show Gitleaks 8.24.3, PR commit-range scan, **no leaks found**, completed successfully. This is evidence for that commit range, **not an assertion that the entire historical repository was scanned**. Failures of future scans must fail the CI job.

Separate production-dependency advisory evidence: [run 42114837015](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/42114837015), candidate SHA `1d376e0a77bffda77d0c2d5ce5887b488b83e768`: npm audit found 0 high / 0 critical. Scanner remains active for new PRs. Neither replaces signed auth/authorization tests.

## Single-maintainer release policy

The owner is the only authorized human reviewer. Ruleset #24457514 was verified active on 2026-11-06: required PR, strict status checks `test` and `factory-acceptance`, no force push or deletion, empty bypass list, **zero compulsory reviewer approvals**. Requiring one review by the PR's own author would deadlock development, so approval count 0 is intentional, **not evidence by itself of manual release**.

Use `python scripts/audit_block1_owner_merge_evidence.py --sha <exact_main_merge_sha> --pr <number>` immediately after owner merge. It read-only checks that GitHub records the expected owner account as `merged_by`, exact main SHA, strict rules, and no bypass. GitHub API evidence **cannot prove physical human button-click or rule out a stolen owner credential**. The Factory must still have no runtime merge capability and must remain in `awaiting_release` for production. The audit returns `block1_certified=false` and `release_authorized=false` unconditionally.


Independent GitHub API observation on 2026-11-06: [PR #1248](https://github.com/leandrosilveiradepaula/ai-product-factory/pull/1248) was merged by account `leandrosilveiradepaula` (actor type `User`) into `main` at SHA `09888f175c9ad00ec1f99ba1c42b6e814eec0134`. The live branch tip matched that SHA; the effective ruleset required both checks and strict freshness, with no bypass. This documents **owner-account merge attribution** for the prior release; it does not prove the physical interaction or absence of automation.

The quality gate still needs applicable PostgreSQL QA evidence and Preview/browser checks when Console changes. No change in this PR requires Vercel Preview, because `apps/console/**` is untouched.

## Remaining evidence before Block 1 acceptance

Real JWT operator and negative RBAC/browser sessions; tenant/cross-repo backend adversarial probes; secret scan for broader historical/other repositories when required; independent clean setup/recovery/rollback with durable receipts; complete requirement-to-journey and mock/noop runtime-reachability proof. No implied authorization for new Start, credential use, migration, model spend, merge, or production release.
