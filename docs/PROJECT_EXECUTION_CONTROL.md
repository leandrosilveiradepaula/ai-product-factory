# Project execution control — implementation boundary (issue #894)

This document is a **proposed contract, not deployed runtime authorization**.

**User decision:** Registration creates a non-executable draft. Only an explicit
operator command can start it. Pausing, stopping and restarting are deliberate
actions. Existing projects are not silently stopped during migration.

The deterministic Python contract in `project_execution_control.py` defines
states and safe transitions independently of product lifecycle stages. It
requires a version CAS and a generation increment for a new execution epoch.
This **does not yet fence any real worker**. It must not be wired only to UI
flags: claims, queue signals and side-effect checkpoints need a **transactional
Control Plane migration** enforcing the durable state.

## Sequence of safe implementation

1. Add versioned SQL migration with service-role-only invoker RPCs and audit.
   Preserve legacy behavior only through an explicit documented compatibility
   mapping; new projects default `draft`. Never migrate automatically.
2. Change atomic intake RPC so registration does not enqueue bootstrap or wake.
   Add separate idempotent `start` RPC. Ensure in-flight runs are not cancelled
   merely by adding the feature.
3. Restrict every product, Direct, Codex, manual Codex, integration and follow-up
   claim at the DB boundary. Add generation fencing before paid/model/network
   side effects and cooperative `pausing/stopping` acknowledgements.
4. Update all Console and scheduling entry points, including continuation and
   retry/recovery. Add explicit authenticated, origin-checked, auditable operator
   commands and mobile-friendly controls. No browser token.
5. Use disposable Postgres race-condition tests plus deterministic worker tests;
   verify registered drafts trigger **zero paid calls and zero runs**. For a
   Console change, exact-SHA Vercel Preview and browser evidence are mandatory.
6. Do not merge to production or apply the migration without a separate human
   production gate. Codex WIF and other external billing constraints remain
   independent and fail closed.

Note that actions already in flight cannot be assumed cancelled synchronously:
the system must first block *new* claims and collect quiescence evidence before
announcing `paused` or `stopped`.

## Worker side-effect checkpoint (candidate)

The migration defines `factory_assert_project_execution_epoch(project_id, generation)` as a service-role-only transactional checkpoint. Executors must capture the generation at claim time and invoke this RPC **immediately before** model/API calls, GitHub writes, workflow dispatch and deployments. A successful check does not reserve a lease or prevent a later pause: workers must also maintain a lease and record quiescence. The RPC is currently a contract, **not proof that all executor paths invoke it**. Production rollout remains blocked until those integrations and exact-SHA Preview are verified.

## Runtime worker candidate integration

The Supabase runtime adapter now requires an explicit positive execution generation and invokes the privileged epoch RPC at stage start, before stage persistence and before successful completion. The stage worker checks before and after handler execution. Missing claim generation fails closed. **The existing claim RPC must still be upgraded to return a trustworthy generation, and other executor routes need their own side-effect fences before this is deployable.** This candidate intentionally blocks old claims rather than silently treating them as authorized.
