# Manual project execution — Console and scheduler contract (17 Oct 2026)

This operational note follows the already human-applied and independently
verified Supabase migrations
`20261017111500_factory_manual_project_execution_controls.sql` and
`20261017193000_factory_graceful_stop_preserve_queue.sql`.
Supabase production history was reconciled with official
`supabase migration repair 20261017193000 --status applied` and re-read.

## Authority and user intent

Registration persists a **draft** project; it does **not** create an executable
task, authorize a model call, or dispatch a worker. The Console's execution
state is read directly from the privileged Control Plane. If the row is absent,
malformed, or unavailable, controls fail closed.

An authenticated operator may use only the database-authorized lifecycle:
`draft -> start -> running`, `running -> pausing -> paused -> resume`,
`running/pausing/paused -> stopping -> stopped -> restart`.
Pausing/Stopping can settle immediately if leases are already quiescent.
The `stop` action remains available even **during** a pending pause; the
operator should not need to wait for a PAUSED acknowledgement to request STOP.

A pending pause/stop rejects new work claims immediately at the database
boundary. In-flight work already claimed by an authorized owner may finish
during draining. Queued tasks and runs must be preserved by STOP, and RESTART
may resume without fabricating duplicate runs. `version`, generation and
per-command UUID are the authoritative idempotency/fencing mechanisms.

## Wake after an operator command

The Console persists `factory_control_project_v1` **before** issuing any
best-effort wake. `start`, `resume`, `restart` in `running` request
a wake without depending on a newly created run ID (important for resuming
existing queued work). `pause` or `stop` in pending `pausing`/`stopping`
request a controller wake to allow prompt settlement.

A wake is **not** approval of paid models, new project registration, bypass
of a release gate, or evidence of a claimed run. The existing
`.github/workflows/autonomous-runner.yml` uses the privileged
`project-control-settle` RPC, database checks, and existing scheduler
readiness gates. If the wake is unavailable, the stored command remains valid
and the Console reports that only the scheduled fallback is available.

Do not dispatch a run automatically when the project is `draft`, `paused`,
`stopped`, `stopping` or `pausing`. STOP does not delete queued tasks,
rewrite history, merge PRs, or override the human production release gate.

## Evidence

- Pure Python state-machine tests include the `pausing -> stopping` operator
  transition and denial of further unapproved RESUME.
- `tests/test_console_manual_execution_flow.py` protects the Console
  state/wake/UX contract and repository_dispatch trust assumptions.
- PostgreSQL 16 isolated QA in
  `scripts/verify_manual_project_control_postgres.py` protects lease-backed
  STOP, idempotency, queue preservation, epoch and permission fences.
- `apps/console/**` changes **require exact-PR-SHA Vercel Preview and
  browser evidence** before human merge to production. Unit CI success
  alone is not sufficient.

Operationally, verify a real user journey in a separate isolated project
before claiming authenticated UI end-to-end completeness. Do not mutate the
four preexisting production projects for this test without a specific
operator action. This release does not create, start or stop any live project.
