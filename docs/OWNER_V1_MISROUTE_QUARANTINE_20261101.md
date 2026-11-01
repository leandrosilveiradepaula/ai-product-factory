# Recovery of misrouted OWNER V1 Start

After Factory PR #1190 the OWNER job requests Journey V2. The earlier
issue-comment #6558318697 instead enqueued a legacy V1 run.

The legacy run f2006037-e43c-451c-89db-57fbdcd17cdf and task
820298e0-23e1-4cf1-b089-9f2bc9c661b7 have no journey_id. The CRM
project is paused at generation 17, control version 17. Do not resume
until both records are safely quarantined and independently verified.

The versioned migration installs the service-role-only function
factory_quarantine_owner_v1_misroute with active admin authentication,
strict run/task identity and request provenance, epoch CAS, absence of
lease/descendants/deployment/evaluation/release and exact admission
audit. It cancels only that run and task, preserves original audit events,
and inserts a durable idempotent receipt.

After PostgreSQL QA and human merge:
1. Apply the approved migration in Supabase Factory.
2. Recheck the CRM project remains paused at generation 17/version 17.
3. Verify run created, task queued, no lease, no other side effects.
4. Call the RPC with expected generation 17 and version 17, OWNER
   comment 6558318697, request id
   467a0b98-6dee-6423-4a73-8dcab1c052ba, an active admin operator
   and a unique stable command UUID.
5. Verify run/task cancelled, audit receipt, unchanged generation.
6. Verify CRM main equals preview/crm209-delivery-v3 at
   d63fa1ad8f1ffd252fe7df27f93a562e7184e8f6.
7. Resume through the versioned operator control RPC, then send a
   completely new OWNER /factory-start crm-infodive command in
   Factory issue #1055. Never replay the previous comment ID.
8. Verify V2 journey_id and SHA before permitting work. Manual CRM
   PR #207 is not Factory-generated proof. Production merge stays human.

No auto-merge, no model probes, no deployment, no accounting fabrication.
