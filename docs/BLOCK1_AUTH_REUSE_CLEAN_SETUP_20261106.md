# Block 1 — independent evidence reuse and clean setup (2026-11-06 UTC)

This is an evidence ledger for **two scoped observations**, not a product or security certification. The Factory must stay `product_ready=false` until independent durable evaluation of all required criteria.

## Reused authenticated Console evidence

Trusted source: [Authenticated Console visual evidence #42100072898](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/42100072898), successful `push main` attempt 1 at `16ae1f28d1807399990727b7e524520347f5f62d`. Independent GitHub inspection found:

- Successful `capture` job and an unexpired nonempty encrypted `authenticated-console-42100072898` artifact; matching `factory_visual_evidence_runs` status `captured` in Supabase (no sensitive columns read).
- The protected browser log, inspected using the connected GitHub audit client, reported 14 screens, 12 navigation paths with HTTP 200, mobile/accessibility evidence and negative operator RBAC transition `/admin/operators` → `/unauthorized`. The Console deployment SHA was verified before and after capture.
- GitHub comparison from the authenticated source SHA to Factory `main=aade774390334250d31775e4b71032421663a33e` confirmed five later commits and **no changes to `apps/console/**`**.
- The new independent workflow `.github/workflows/block1-authenticated-console-reuse.yml` checks *all tracked Console file blob hashes*, exact source-run provenance, ancestry, successful capture job and artifact retention for each PR head SHA. The receipt is uploaded even on failure.

**Important limitation:** the GitHub Actions token cannot fetch the earlier job's detailed log: authenticated request returned HTTP 401, anonymous fallback HTTP 403. The verified workflow therefore **does not claim** to have reopened the browser interactions, decrypted the artifact, independently verified JWT issuer/claims or certified RBAC/tenant access. It explicitly emits false for these claims. The historical log was examined independently through the connected GitHub tool; it is separately linked above. Do not expand token privileges simply to force a PASS.

## Non-root, credentialless README exercise

`scripts/exercise_block1_clean_setup.py` verifies the documented Python commands using an allowlisted environment and `uid != 0`. The independent Actions job copies the checked-out code (without `.git`) into an isolated temporary directory accessible to `nobody`, clears inherited environment variables with `env -i`, and runs:
- `python -m ai_product_factory.cli validate config/factory.example.json`
- `python -m ai_product_factory.cli codex-decision --complexity high --files 20 --deep-debug`
- `python scripts/check_test_collection.py`

At [run #42152594208](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/42152594208), SHA `e47c304f2730d3da259ebe798121a98a921cec0f`, all three commands returned exit code 0; non-root identity, environment allowlist and README contract checks returned true. The summary includes `block1_certified=false`, `documentation_setup_configuration_certified=false` and `paid_model_calls=0`. The run is a genuine isolated setup reproduction, **not an installation/deployment/complete operations simulation**.

## Remaining blockers

- Auth: signed JWT issuer/claims and real negative operator/nonoperator sessions are not fully certified by a historical browser artifact.
- Access boundaries: additional cross-tenant, cross-repository and server/backend adversarial checks remain.
- Documentation: independent operations/incident and rollback rehearsal still require durable evidence.
- Functional completeness: requirement-to-real-journey receipts and runtime mock/noop reachability need complete review.
- Current SHA certification in the Control Plane remains `not_ready`; CI and this documentation cannot change that.

No external model usage, Supabase write, privileged operator provisioning, release, deployment, auto-merge or migration is part of this candidate.
