# CRM #171: V2 context preflight recovery

The previously blocked work unit requires a narrowly scoped, audited, one-time recovery after PR #1178. Preserve the same run, task, work unit, journey binding and generation. Do not replay planning or automatically merge production. Verify the immutable source SHA, execution generation, absence of GitHub writes, and exact `PermissionError: journey context cross-project` before requeue. The runtime worker must revalidate its guards before writing.
