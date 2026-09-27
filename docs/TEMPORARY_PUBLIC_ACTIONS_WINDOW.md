# Temporary public Actions window

Purpose: allow a short human-authorized public-repository window so standard GitHub-hosted Actions can execute without consuming the private-repository included-minute quota.

This is an access-expansion procedure, not a normal runtime action. Repository visibility must be changed only by the human repository owner.

## Known exposure

Making this repository public makes its code, Git history, branches, issues, pull requests, and Actions history publicly discoverable and copyable. Returning the repository to private later does not revoke clones or copies made while public. Public forks created during the window may remain public after the source repository becomes private again.

The repository intentionally contains architecture and non-secret operational metadata, including OpenAI workload-identity provider/service-account identifiers, GitHub OIDC claim shapes, Control Plane architecture, deployment references, and security/runbook documentation. These are not credentials, but they become public operational intelligence during the window.

The repository history also contains commit author metadata. Treat that as public once visibility changes.

## Pre-open checklist

- [ ] Confirm there are no open pull requests from untrusted contributors.
- [ ] Confirm no current branch/file contains a literal credential.
- [ ] Keep `FACTORY_PRIMARY_MODEL_ENABLED=false`.
- [ ] Keep Codex execution disabled unless its independent auth gate has already passed.
- [ ] Confirm the only workflows triggered by `pull_request` are read-only and do not reference secrets or OIDC.
- [ ] Confirm no workflow uses `pull_request_target`.
- [ ] In GitHub Settings > Actions > General, require approval for workflows from external fork contributors.
- [ ] In the Vercel project settings, confirm Git Fork Protection is enabled before the repository becomes public.
- [ ] Do not authorize Vercel deployments originating from unknown forks.
- [ ] Record the public-window start time.

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
