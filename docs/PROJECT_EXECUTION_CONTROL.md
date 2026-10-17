# Project execution control — implementation boundary (issue #894)

This document describes a **candidate implementation, not deployed runtime authorization**.

**User decision:** Registration creates a non-executable draft. Only an explicit
operator command can start it. Pausing, stopping and restarting are deliberate
actions. Existing projects are not silently stopped during migration.

The deterministic Python contract in `project_execution_control.py` defines
states and safe transitions independently of product lifecycle stages. It
requires a version CAS and a generation increment for a new execution epoch.
The candidate Supabase runtime worker now performs epoch checks, but this is not yet deployed. It must not be wired only to UI
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

## Isolated CI remediation

The initial candidate failed the unit suite because older test fixtures lacked execution generations and failed isolated PostgreSQL QA because its disposable schema omitted the existing production `factory_runs.started_at` column. The candidate fixtures now provide explicit generations for permitted actions, preserve a missing-generation rejection test, and mirror the required column. The unit and isolated PostgreSQL workflows passed on candidate SHA `c7d2967f1c40f3f0a73e2fcad91d23e36b6cde0c`; Console validation and exact-SHA Preview remain separate requirements.
\n## Known release blockers\n\n- The production migration is not authorized by a successful CI run; it requires a separate human decision.\n- The claim RPC candidate now acquires the project control row before task/run writes, matching the operator transition lock order. This requires disposable PostgreSQL CI and a dedicated concurrent pause/claim race test before production rollout.\n- A standalone epoch-check RPC cannot make later model, network or database side effects atomic with the check. Audit all executor routes and enforce generation in mutating database RPCs; do not claim full cancellation safety based only on preflight.\n- Never treat queued Vercel checks as Preview evidence. Require the exact SHA, successful deployment and browser verification when Console files change.\n\n## Disposable concurrency evidence\n\nThe isolated PostgreSQL QA now opens a second connection while an operator transaction holds the project-control row lock. The competing claim must return no work through `SKIP LOCKED`; after release, the original claim can proceed. The same QA checks idempotent restart replay and generation stamping. These are candidate tests, not evidence of production deployment.\n\n## Operator console behavior\n\nThe Console validates the control RPC state, version and generation before reporting success. A missing or malformed version in a submitted form is rejected rather than coerced to zero. A new project requires a deliberate Start confirmation, and an unavailable control record shows a fail-closed explanation rather than action buttons. A Resume transition does not manufacture a new bootstrap run; only Start/Restart with an actual returned run ID may wake the intake worker.\n\n## Runtime admission hardening\n\nThe candidate claim function now locks and rechecks both the task and run statuses before updating them, so a stale candidate selected before a concurrent worker claimed it is rejected. The runtime worker rejects a claimed run with zero stages instead of falsely completing it; it attempts a terminal failure only through the epoch-protected queue. Product-stage persistence rejects evidence other than `completed` before any RPC. The SQL claim race still requires the disposable PostgreSQL QA and exact-SHA CI checks; external effects remain subject to separate epoch and gate controls.\n\n## Claimed payload contract\n\nThe candidate queue now rejects a malformed claim payload before constructing a work item: run/task/project identifiers must be nonblank strings, stages must be a list of nonblank strings, context must be a mapping, and execution generation must be a positive non-boolean integer. A legacy claim response without an execution generation is not dispatched. A stage handler must return a mapping before evidence can be persisted. These checks are defense in depth, not a substitute for transactional database epoch enforcement.\n
## Additional worker admission invariants

A claim must provide a nonempty, unique, whitespace-normalized stage sequence and a nonblank worker identity. Stage lifecycle events require a nonblank stage; completed evidence must contain a mapping. The worker rejects malformed or repeated stages before invoking handlers and must not report a successful run in those cases. The PostgreSQL claim/epoch gates remain authoritative and these adapter checks provide defense in depth.
