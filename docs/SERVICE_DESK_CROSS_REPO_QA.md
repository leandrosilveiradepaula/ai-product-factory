# Service Desk — isolated cross-repository QA (incident fallback)

**Purpose:** Permit deterministic, credential-isolated validation on the
**Factory's public GitHub Actions runner**, because the private pilot's own
GitHub-hosted runner is failing before any checkout or script execution
([pilot issue #4](https://github.com/leandrosilveiradepaula/infodive-service-desk/issues/4)).
This is an incident fallback, **not** an authorization to merge/release.

## Trigger and trust

The trusted workflow `.github/workflows/service-desk-cross-repo-qa.yml`
is effective only **after human merge into Factory main**. It listens to an
OWNER issue comment on Factory issue #841 with the **exact** form:

```text
/service-desk-qa pr=3 sha=1001cb9e7508f0c484f4d0d5ae590ecf4d35f51c
```

The SHA is the exact PR #3 head at preparation time; inspect GitHub again
before triggering, because the branch may have advanced. The worker verifies
the private repository, PR state=open, target=main, the PR head repository,
and the full 40-character head SHA using an **explicit**
`FACTORY_GITHUB_TOKEN` (no cross-repo GITHUB_TOKEN fallback). Unknown PRs,
forks, changed heads, absent secret and invalid comments abort. Token never
enters npm steps, generated code, artifacts, browsers, or a persistent checkout
credential. This workflow does not request OIDC, paid models, database
privileges, Vercel deploys, or GitHub merge capabilities.

## Two bounded passes

1. If `package-lock.json` is missing, the workflow generates a proposed
   lockfile via `npm install --package-lock-only --ignore-scripts`, saves it
   with exact PR/SHA provenance to a 7-day artifact, **and deliberately fails**.
   It does **not** report the bootstrap as successful CI. The human/assistant
   must inspect and commit the lockfile in a new PR-branch commit before
   another exact-SHA run can pass. No purchase or new SaaS service.
2. With a committed lockfile, the workflow runs `npm ci --ignore-scripts`
   followed by the product's `npm run ci`, which must check TypeScript
   including TSX, unit tests and Vite bundle. An exact-SHA artifact records
   outcomes, and does not falsely mark `postgres_rls_isolation_passed`,
   `preview_verified`, `release_authorized` or product GitHub status green.

**Limits:** A green Factory QA is *supplemental* evidence only, not a native
check-run for the private pilot, PostgreSQL two-tenant isolation proof, a
browser/Preview proof, or an official production release. The Service Desk's
PR #5 security corrections also require real isolated Postgres/RLS tests.
Pilot release issue #8 and quality issue #2 stay open until all release gates
are met. The private repo's Actions allocation problem still needs an
administrative GitHub investigation; do not change repository visibility or
buy credits without explicit approval.

**Cost:** No paid model invocation, no dependency on the OpenAI budget, and
no database migration. QA consumes only existing free/available Factory
GitHub Actions resources, subject to normal GitHub plan limits.
