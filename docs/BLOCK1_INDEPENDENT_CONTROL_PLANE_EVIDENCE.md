# Block 1 — Independent Control Plane access evidence

This is a **read-only inventory**, not a substitute for authenticated adversarial tests. Execute `scripts/audit_block1_control_plane.sql` in a privileged **read-only** PostgreSQL session against the intended Supabase project, record the timestamp, project ID, current commit SHA, and complete query result in the certification receipt. Never use a production service key in browser/CI output.

## Live observation — 2026-11-05 UTC

Supabase project `fjplmxfcshhbmzgvyqlm` was inspected through independent read-only catalog queries. Observed: 58/58 `factory_*` ordinary tables with RLS enabled; no public write grants; one authenticated self-SELECT operator policy; four functions executable by `anon`/`authenticated`, all `SECURITY INVOKER`; one `SECURITY DEFINER` function without public execution. These observations were collected independently of CI at the time, and **do not attest a new candidate SHA or prove runtime tenant isolation**.

The executable SQL audits ordinary and partitioned tables, public write grants, public or write policies, and publicly executable SECURITY DEFINER functions. It emits explicit blocker counts and never grants `product_ready`. Catalog results must be correlated with the exact deployed schema and current release. Any blocker requires remediation; zero blockers still requires negative authenticated RLS/RPC and cross-tenant tests before certifying `security/data_access_boundaries`.

## Remaining independent proofs

- Negative `anon`, authenticated non-operator, operator, and cross-tenant access attempts against isolated test fixtures.
- Signed operator browser login, negative route/role/CSRF cases, and immutable SHA/browser evidence.
- Independent secret scanner and dependency advisory results for the exact candidate.
- Effective GitHub ruleset with strict checks, applicable PostgreSQL QA, and **observed owner-only merge** for the single-maintainer repository. Mandatory approval count remains zero to avoid self-review deadlock; a ruleset by itself cannot prove the owner clicked Merge. See `docs/BLOCK1_RUNTIME_SECURITY_EVIDENCE_20261106.md`.
- Clean setup, scheduler/recovery, rollback, requirements-to-journey and simulation-reachability receipts.

**No migrations, writes, paid model calls, merge, or release are authorized by this audit.**
