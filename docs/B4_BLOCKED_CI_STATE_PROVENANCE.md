# B4 — Source-compatible, fail-closed release-blocked candidate reconciliation

The original greenfield run `3e747d9d-2440-4e78-8db0-55461753954e` and original Studio PR #2 must be preserved. A legitimate earlier **failed-Preview** recovery (`factory_reconcile_failed_preview_candidate_v1`) wrote an immutable `reconcile_pr_candidate` receipt with `ci_state=success` and verified first-party GitHub Actions/Playwright provenance. The independently implemented **release-policy-blocked** reconciler required only the earlier `ci_conclusion=success` field, creating a real PT409 on a verified second-stage recovery despite all other run/PR/epoch/DoD guards passing.

## What changes

The versioned migration `20261117160500_verified_blocked_ci_state_alias.sql` replaces **only** the protected reconciler function to accept either (a) the already-valid `ci_conclusion=success` form, or (b) the exact **failed-Preview-specific** `ci_state=success` form with `github_actions_exact_sha`, `github_actions_checks`, `recovery_source=failed_preview`, positive bounded native CI and independent browser verifier identifiers, previously verified signed source, `release_authorized=false` and mandatory new specialist/DoD reviews.

It does **not** edit historical receipts, suppress CI, relax branch/SHA/epoch/lease/DoD/human approval, change RLS, rewrite product readiness, authorize a merge or create a new Start. The unmodified `factory_reconcile_policy_blocked_candidate_v1` CAS semantics remain. Source SHA, origin PR, full GitHub CI and preview remain independently reverified by the OWNER-only workflow before the RPC.

## Evidence and forward recovery

The isolated PostgreSQL 17 QA runs the old migration + new compatibility migration and exercises both valid original `ci_conclusion` and newer `ci_state` chains. It rejects missing browser metadata, wrong origin source, wrong CI provider, false billing/release fields, malformed run ID, and replay; it asserts the denied release report stays blocked. These tests use synthetic local data only. The real Studio PR's separate CI also tests the versioned Studio migration against PostgreSQL 17 and a controlled partial-failure/atomic rollback/forward recovery rehearsal, plus actual hosted Studio RLS/ACL.

### Operator gates
1. Human reviews and merges the Factory PR, which publishes the Factory Console only under its existing project policy.
2. Independently **authorize** application of exactly `20261117160500_verified_blocked_ci_state_alias.sql` in Factory Control Plane `fjplmxfcshhbmzgvyqlm`; CI green does not authorize production migrations.
3. Verify SECURITY INVOKER / EXECUTE only for service_role, then issue on OWNER issue #1414: `/factory-reconcile-blocked run=3e747d9d-2440-4e78-8db0-55461753954e pr=2`.
4. After the run is actually re-pinned to the Studio PR head, record the separately verified `migration_validation` and `rollback_analysis` evidence against **that same SHA** via the existing Control Plane evidence pathway, with GitHub run/job and hosted Studio schema/migration provenance. Re-run CI, QA/Security/Ops and Preview, then the release policy must independently evaluate DoD.
5. **Only** human merge of Studio PR #2 may publish production; release observer registers and certifier checks the same journey in operations. Never auto-merge or fake a certificate.
