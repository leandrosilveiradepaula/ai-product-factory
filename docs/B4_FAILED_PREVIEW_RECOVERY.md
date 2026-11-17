# B4 — Recover a failed real greenfield Preview on the original Start

## Incident and source of truth

The original Dark Channel Studio Change Set \`0bccb423-cacb-49fa-b238-c8baba27e372\`, root run \`3e747d9d-2440-4e78-8db0-55461753954e\`, and PR #2 must remain the same lineage. The run was terminal \`failed\` because the actual Preview returned HTTP 500; changing the code after that did not silently change the Control Plane SHA. Do not start another test-only product or silently mark the failed run as passed.

Verified isolated project \`nsmnmcjzprovxfxkhwxt\` (Supabase, Sao Paulo, Free, US$0/month) has the versioned Studio migration applied. Studio Preview uses branch-scoped environment values. The GitHub/Vercel SHA \`9290634e647a381712b4b1b5bbd1ba0159969ff1\` has native CI green and the independently verified Factory browser snapshot \`2ebdda68-9daa-46b4-a194-8c742c4e9886\`; browser run #44088733294 was successful. This is a real Preview proof, not a live authenticated business journey nor release approval.

## Protected recovery

The code in \`failed_preview_candidate.py\` and the versioned migration \`20261117133000_failed_preview_candidate_recovery.sql\` implement a single fail-closed conditional transition on this **same** root run. It is generic for any greenfield project/Change Set and does not hardcode this Studio's UUID or SHA.

1. Human reviews/merges the Factory PR; production migrations remain independently human-gated. Do NOT apply the migration automatically merely because CI passed.
2. Apply the **exact versioned migration** to Factory Control Plane only when authorized. Verify its name/version, security_invoker, service-role-only EXECUTE, PostgreSQL QA and RLS before continuing.
3. Issue the OWNER-only command below as a new comment on Factory issue #1414; the workflow independently queries the current PR/branch, ancestry/changed paths, full native GitHub CI and first-party exact-SHA browser run, then invokes the guarded RPC through the existing OIDC broker.

\`\`\`
/factory-reconcile-failed-preview run=3e747d9d-2440-4e78-8db0-55461753954e pr=2
\`\`\`

4. A successful receipt may only restore the original failed run to \`ci_pending\`, rebind its Change Set SHA and restore the already-integrated task to \`integrated\`. Historical browser FAIL, prior terminal timestamp (preserved in recovery metadata), release DoD blocker and prior specialist reviews remain preserved. The active run clears finished_at for CI requeue, and new SHA reviews/gates are required.
5. Let the existing deterministic \`runtime_cli --mode ci\`, specialist workers and Preview observer re-run. A new browser witness and verified DoD must precede \`awaiting_release\`; no human release gate is bypassed.
6. After Preview, QA, migration-validation and rollback-analysis pass on the latest SHA, request a **human** merge of Studio PR #2. The Factory release observer alone registers that merge and subsequent operation. Run the readiness certifier only after the full current-SHA chain is present.

## Security and negative evidence

The RPC is one-shot, \`SECURITY INVOKER\`, only executable by \`service_role\`; it requires an original failed browser evaluation, unleased failed task/run, live execution epoch, original PR chain, still-open human-gated PR, exact ancestor commit comparison, native CI and independently recorded first-party browser snapshot with matching signed verifier run identity. Failed reconciliation leaves original state untouched.

The isolated PostgreSQL QA applies the migration against a disposable 17.6 database, injects mismatched/forged witnesses, rejects replay and proves old evidence remains. Unit tests reject stale PR, branch, epoch, failed CI, wrong browser/verifier and missing nonhuman DoD. No credentials, production release, paid model call, fabricated status or auto-merge.
