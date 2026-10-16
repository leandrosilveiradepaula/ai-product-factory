# OpenAI API credit-denial reconciliation — runbook

**Status:** candidate only; migration not applied; Service Desk run still blocked.

## What happened

On 2026-10-16 at 02:50:04 UTC, the Service Desk's original Direct run
`fffee538-9781-4905-a69d-f3427d6f66b3` failed with an actual API HTTP 429,
`type=insufficient_quota`, `code=credit_balance_exhausted`,
`request_id=req_c83153187db74f209bf372a1f42d4f5b`. The provider returned
an error rather than a Responses model result or token-usage object. The
original metered implementation conservatively persisted the reserved
`factory_tool_usage.id=117` as `model_call_cost_unknown` with null cost.

The operator reports that API credit was replenished. That fact **does not**
resolve an unknown-cost ledger entry. Product Stage and Direct workers must
continue to fail closed as long as it remains unresolved. Internal budget
USD 10 and per-call reserve USD 0.50 are independent of the provider balance.

## Candidate fix

The provider adapter now emits a typed denial **only when all of these
facts hold simultaneously**: HTTP 429, exact credit-balance error type/code,
provider request ID, and **no** Responses ID, generated output or usage
object. In that exact case, the metered provider records an explicit rejected
pre-response operation and releases its reservation. Network failures,
timeouts, generic 429 rate-limits, malformed denials and partial/missing
usage after a generated response still record cost unknown.

The versioned migration
`20261016040600_reconcile_openai_credit_denial.sql` is a separate,
one-off accounting action. It checks the immutable recorded request identity,
original run/work-unit/Change Set, exact error details, zero observed token
usage, blocked status, leases, source SHA, and absence of any unrelated paid
cost-unknown event. Only then can it reclassify the original row as a rejected
pre-response operation with USD 0 usage. The complete prior row is copied to
append-only audit metadata. The migration does **not** requeue or trigger a
model call.

**Human financial/prod decision required:** A repository merge does not
approve a production accounting reclassification. Before approving the
Console migration gate, the operator should inspect the OpenAI Usage
Dashboard for the correct organization, project and UTC interval and confirm
that this refused request had no charge. The HTTP rejection is strong
pre-response evidence, but not a standalone invoice or independent
billing-report verification. If usage cannot be reconciled, do not apply
the migration or invent a cost; keep the paid gate blocked.

## Resume only after evidence

1. Merge the PR through an authorized human release gate after green CI.
2. Request a durable Console `apply_control_plane_migration` gate for its
   exact PR, SHA and filename, with the financial review evidence.
3. Human operator applies it explicitly; verify the schema migration record,
   ledger row #117 and `model.usage.credit_rejection_reconciled` audit event.
4. Independently verify no other paid unknown events and the real configured
   budget USD 10 / reserve USD 0.50. Do not make a paid test call.
5. Revalidate the original blocked run, assignment, task, work unit and
   Change Set, and recover **the same run** atomically and with audit. Preserve
   its attempt count and two already-completed wave-7 units.
6. Make one OWNER `/factory-wake` call only after recovery; verify worker,
   output commit and wave integration before dispatching wave 8.

The Service Desk must still complete its RLS/RBAC, TSX and isolated real-CI
release gates. Vercel Preview guard remains independent.
