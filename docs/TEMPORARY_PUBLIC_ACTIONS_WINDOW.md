# Temporary public Actions window

Purpose: allow a short human-authorized public-repository window so standard GitHub-hosted Actions can execute without consuming the private-repository included-minute quota.

This is an access-expansion procedure, not a normal runtime action. Repository visibility must be changed only by the human repository owner.

## Known exposure

Making this repository public makes its code, Git history, branches, issues, pull requests, and Actions history publicly discoverable and copyable. Returning the repository to private later does not revoke clones or copies made while public. Public forks created during the window may remain public after the source repository becomes private again.

The repository intentionally contains architecture and non-secret operational metadata, including OpenAI workload-identity provider/service-account identifiers, GitHub OIDC claim shapes, Control Plane architecture, deployment references, and security/runbook documentation. These are not credentials, but they become public operational intelligence during the window.

The repository history also contains commit author metadata. Treat that as public once visibility changes.

## Pre-open checklist

- [x] Confirm there are no open pull requests from untrusted contributors.
- [x] Confirm no current branch/file contains a literal credential.
- [x] Keep `FACTORY_PRIMARY_MODEL_ENABLED=false`.
- [x] Keep Codex execution disabled unless its independent auth gate has already passed.
- [x] Confirm the only workflows triggered by `pull_request` are read-only and do not reference secrets or OIDC.
- [x] Confirm no workflow uses `pull_request_target`.
- [x] GitHub fork pull-request workflows are disabled; external fork PRs cannot run repository workflows.
- [x] Vercel Git Fork Protection confirmed enabled.
- [x] Do not authorize Vercel deployments originating from unknown forks.
- [x] Public-window start: 2026-09-27T14:42Z (repository owner action).

## During the public window

Run only the non-paid validations needed to close the current verification debt:

1. `validate` / unit tests.
2. `factory-acceptance`.
3. `Console validation` when Console code changes.
4. Verified Preview / Playwright only for the exact trusted candidate that requires it.
5. OpenAI API WIF preflight is allowed because it performs no model call.
6. Codex auth preflight is allowed only as an authentication check and must not execute a Codex task.

Do not run `OpenAI runtime smoke`, `OpenAI runtime execute`, Direct paid-model execution, a Codex task, or the Agent SQL 63-question benchmark merely because Actions minutes are available.

Monitor new forks, external pull requests, workflow approvals, and unexpected deployments.

## Close checklist

- [ ] Record validation evidence and exact candidate SHAs.
- [ ] Check whether any public forks or external pull requests were created.
- [ ] Return repository visibility to private.
- [ ] Confirm production Vercel health remains HTTP 200.
- [ ] Re-check GitHub Actions workflows and environments after the visibility transition.
- [ ] Record the public-window end time and any irreversible exposure/forks observed.

If Vercel Git Fork Protection or GitHub external-workflow approval cannot be confirmed, do not open the repository.


## Current window evidence

- Repository visibility: public.
- Forks observed after opening: 0.
- Open external pull requests observed after opening: 0.
- Main validation after opening: `validate` run #1041 succeeded, including unit tests, compile and `factory-acceptance`.
- Console validation after opening: run #209 succeeded, including `npm install`, typecheck and production build.
- Historical redesign candidate `10f593d7d169d30fe5048eac9d98a94b8be1e151`: rerun of the previously quota-blocked `validate` and `Console validation` jobs succeeded.
- Vercel deployment quota remains exhausted for the current daily window; production health remains HTTP 200 on the last READY deployment.
- Browser/Playwright evidence for the historical candidate has not yet been re-executed.
