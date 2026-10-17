# Authenticated lifecycle read-only audit and pending control settlement

This candidate is **not** production deployment. PR #907 is the human-merge
dependency for the current manual-control UI and its exact-SHA Vercel evidence.

## Operator-visible, read-only browser proof

The authenticated Playwright audit opens an already existing project's details
without pressing Start, Pause, Stop, Resume or Restart. A scoped request route
aborts non-GET traffic to that project's path. It validates the Portuguese
state label against the exact authorized command set, every form's project key,
version and unique UUID, and the submit button label. A generic "some valid
button set" is **not** sufficient. In particular, **Pausando** requires only
**Parar**, and **Parando** provides no command.

The same controls are validated again in a 390px mobile viewport. Mobile
project-detail horizontal overflow fails the audit; a screenshot and bounded
state evidence are produced. If there is no accessible existing project, the
audit fails rather than claiming a lifecycle pass without coverage. The audit
never changes a live project's execution state.

The pure read-only control validator is tested with Node's built-in test runner
in the standard CI job. That does not substitute for a protected authenticated
Playwright run with real operator access. It also does **not** prove the
mutating Start/Pause/Stop/Restart flow; that requires an isolated test fixture
and approved cleanup, never the four existing production projects.

## Graceful settlement when more than 100 projects are pending

The prior settlement worker read only the first 100 PAUSING/STOPPING rows.
Rows removed from that filter by successful settlement make OFFSET pagination
unsafe. The new code walks UUID keyset pages and validates strictly ascending,
unique canonical IDs and every RPC acknowledgement. The function itself
remains service-role-only and the SQL/queue/generation policy is unchanged.

Regression tests cover 102 simultaneous pending controls, cursor overlap,
malformed identities, invalid acknowledgements and a STOPPING project still
waiting for its lease. All tests are mocked: they never invoke the production
RPC, alter production projects, spend model tokens or create Vercel Previews.

## Release policy

This PR changes Python, workflow, tests, script and documentation, not
`apps/console/**`: Vercel Preview is not applicable to this PR. A
successful CI alone is not permission to merge production. Merge is a
separate human decision after verifying compatibility with #907.
