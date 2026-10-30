# Journey Delivery Binding v2

## Scope

V2 fixes the lifecycle class exposed by CRM #203 → #205 → #171. The old
project `manifest.delivery_target` is a mutable legacy selection cursor, and
`manifest.preview.promotion.base_ref` is a separate mutable legacy destination.
Neither identifies a new authorized request. A frozen source SHA, an output
SHA, a Preview merge SHA and a production release SHA are separate receipts.

The candidate migration `20261030150000_journey_delivery_binding_v2.sql` adds
`factory_journeys` and nullable `journey_id` foreign keys. It does not infer or
backfill a binding for old tasks, runs, Change Sets, or failed runs. The CRM
run `e2097705-5046-4825-a2c9-69088dbccdf5` remains historical and failed.

## State machine and activation

`intake_accepted`/`awaiting_source` records an authenticated OWNER or Console
intent, with request idempotency, but creates no task, run, wake, model call or
GitHub write. The privileged source resolver must inspect policy, repository,
access, current ref and scope, then call `factory_bind_journey_source_v2`.
That one database transaction records the immutable source and both delivery
destinations, then creates the task/run. The runtime reads the binding again
before any stage, and Preview promotion rejects a policy whose base ref differs
from the binding.

The flag is off by default. Activation requires, in order:

1. Human merge and green CI of this candidate.
2. Explicit human authorization to apply the versioned migration.
3. Verify service-role-only RPC ACL and RLS; no public grants.
4. Persist an explicit, versioned CRM V2 policy with digest, authorized source
   mode, unique journey integration branch and unique Preview destination.
5. Enable `FACTORY_JOURNEY_DELIVERY_BINDING_V2=true` only for the authenticated
   OWNER/Console paths and run the legitimate CRM #171 request.

Rollback disables new V2 intake at the flag. It does not delete journeys or
fall back to V1 for an already recorded V2 request; inspect/drain it under the
same controls. V2 never merges production and does not apply a migration.
