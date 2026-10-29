# Independent scheduler watchdog — candidate, OFF by default

## Why this exists

The Factory's native GitHub Actions `schedule` is best-effort. On 29 October
2026, the two Factory schedules last started at 10:04/10:26 UTC and then no
further `schedule` event was delivered through at least 15:22 UTC. GitHub
confirms that scheduled workflows can be delayed or dropped. The existing
six-hour OIDC-preflight fallback successfully woke the runner at 12:52 UTC;
**it is still scheduled by GitHub** and cannot make this a truly independent
timer. Issue #1143 remains valid until the native recovery conditions pass.

This watchdog is an opt-in, Python-stdlib-only trigger to be run from a
**separate already-managed host/timer**, not from the Factory's own GitHub
Actions. It is **not installed, enabled or holding credentials** by this PR.
It never reads Supabase, starts a model, selects a work item, merges, applies
migrations, deploys, or changes approval gates. It only inspects official
GitHub Actions evidence and can request an existing `workflow_dispatch` on the
immutable `leandrosilveiradepaula/ai-product-factory` / `main` target.
The Factory's existing workflow then performs its native queue admission,
lease recovery, cost controls and human production release gate.

## Fail-closed algorithm

1. Resolve the exact GitHub repository numerical ID and active workflow path
   using official REST API; reject drift, arbitrary repositories or branches.
2. Read the newest 20 `schedule` runs of that workflow, validate provenance,
   ordering and UTC timestamps. Two recent, consecutive, successful runs
   separated by less than two hours must each have the **actual
   `schedule-probe` job** completed successfully. This is the evidence needed
   to suppress a redundant external wake. A single returned native event
   after a gap does not count as recovery.
3. If the newest native run is still starting and is under 30 minutes old,
   do not request a concurrent duplicate yet.
4. If native liveness remains unproven, check the exact workflow's recent
   `workflow_dispatch` runs. Suppress an additional dispatch when one was
   created within 30 minutes. No caller-provided URL, repository or ref is
   accepted; `--execute` is a distinct operator-approved switch.
5. Only with both `--execute` and
   `FACTORY_EXTERNAL_SCHEDULER_ENABLED=true`, and a scoped credential,
   POST `{"ref":"main"}` to the **one exact Actions dispatch endpoint**.
   HTTP 204 is recorded only as `dispatch_accepted`, not executed/PASS.
6. API failures, ambiguity, missing job evidence, clock drift and missing
   credentials fail closed with redacted reason codes. A timer/log monitor
   should alert on repeated `blocked` results, rather than silently masking
   unavailability. This watchdog does not impersonate GitHub native
   `schedule_probe.native_observed`, and must never close #1143 itself.

This is at-least-once wakeup, not exactly-once dispatch. Concurrent watchdog
hosts are unsupported; use **one** timer instance. Even if external dispatch
is duplicated because of an API race or crash, the runner's existing
concurrency, Control Plane leases, epoch fences and budget checks must
remain the only work-effect authority. Do not loosen these controls.

## Offline validation (no provider credits)

From repository root:

```bash
PYTHONPATH=src python -m unittest tests/test_independent_scheduler_watchdog.py -v
```

For an approved trusted host with a read-capable scoped token already set as
`FACTORY_EXTERNAL_GITHUB_TOKEN`, run the following read-only preflight:

```bash
PYTHONPATH=src python scripts/independent_scheduler_watchdog.py
```

The preflight prints `would_dispatch` or `skipped` and **never** posts by
default. Without a token it correctly returns `blocked` (exit status 2).
Never paste tokens in chat, shell command arguments, PRs or logs.

## Activation gate — NOT granted by merge

A future operator-approved activation requires all of the following:

- A trusted timer host **outside GitHub Actions** (for example an already
  managed server). Do not create/purchase a new VPS automatically.
- A GitHub fine-grained credential scoped **only** to the Factory repository
  with the minimum **Actions read/write** capability needed to inspect runs
  and call workflow dispatch. Never use `GITHUB_TOKEN` from Actions on an
  external host, browser tokens, or a cross-repo credential.
- Secret `FACTORY_EXTERNAL_GITHUB_TOKEN` held in a root-owned service
  environment file (`0600`), never in Git, browser, container logs or the
  cron command line. A dedicated unprivileged service identity should run
  the script. Only on the trusted host, set
  `FACTORY_EXTERNAL_SCHEDULER_ENABLED=true`.
- An explicit cost/quota decision for added GitHub Actions runs; the
  watchdog itself calls no paid model and does not create a service, but
  real dispatches may execute already-authorized Factory work under its
  existing ledger/budget. Do not silently increase budget or call models
  to test the watchdog.
- Human review and merge of the PR that ships the script. Human activation
  of the timer and sensitive GitHub access is **separate**. Review one exact
  no-work dispatch in the real environment, then verify the resulting run,
  queue/lease behavior, nonnative telemetry and alert state. A POST 204 alone
  is not an end-to-end success.

A possible *operator-reviewed* systemd unit (illustration, **do not install
implicitly**) uses:

```ini
[Unit]
Description=AI Product Factory independent schedule watchdog

[Service]
Type=oneshot
User=factory-watchdog
Group=factory-watchdog
WorkingDirectory=/opt/ai-product-factory
Environment=PYTHONPATH=src
EnvironmentFile=/etc/infodive/factory-watchdog.env
ExecStart=/usr/bin/python3 scripts/independent_scheduler_watchdog.py --execute
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
```

A separate timer may run it at off-minute intervals, e.g. at minutes
7, 22, 37 and 52. Verify service user, Python version, checkout, log
redaction, permissions, clock accuracy, restart behavior and timer runs
before enabling. No Supabase `pg_cron`, `pg_net`, new Edge Function,
production migration or new recurring paid service is required by this
option. The GitHub `schedule` and six-hour fallback remain in place as
additional (not independent) opportunities.

## Preview and release policy

This candidate touches Python/tests/docs only, not `apps/console/**`:
Factory Console Preview is **not applicable** by its explicit path policy.
No migration, production deploy, human release, OAuth/WIF or Supabase RLS
change is implied. `product_ready=false` until the six-domain audit is
independently completed; this component only addresses missed wakeup risk.
