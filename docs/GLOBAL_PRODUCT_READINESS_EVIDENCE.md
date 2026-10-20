# Global product-readiness evidence after validated main CI

## Purpose and scope

An end-to-end **delivery** proves work was shipped; it does not prove all
features, mobile/accessibility, tenant boundaries or operational recovery.
The Control Plane release may legitimately say
`product_readiness={ready:false,status:not_assessed}`.

`.github/workflows/global-product-readiness.yml` is a strictly read-only,
model-free observer automatically triggered by a successful `validate`
workflow on a **push to main**. It is not run on PRs, schedules, comments,
dispatches, or failed CI. It uses the short-lived Control Plane OIDC credential
and same-repository GitHub read token. No Vercel deployment or Preview is
requested.

The observer reads (bounded, read-only):

- The exact current GitHub default-branch HEAD, commit/tree provenance and
  complete non-symlink file path inventory.
- The exact completed, successful **push** `validate` run and all check-runs
  bound to the same SHA. GitHub CI is evidence of executed checks, **not** a
  full-product readiness evaluation.
- The matching Control Plane project by repository identity, with no
  cross-repository token substitution.
- A durable `factory_evaluations` row with
  `eval_type=product_readiness` and `baseline_ref=<current SHA>`, whose
  associated run/task belongs to the same project. Both the durable evaluation
  status and the complete six-domain result must satisfy
  `release_intelligence._verified_product_assessment`. Existing projects
  additionally require an **independent**, same-SHA
  `existing_project_baseline` evaluation (inherited debt, repository,
  critical journeys).

If the trusted evaluation does not exist, the scan returns
`not_assessed`, `product_ready=false`, the source/CI inventory and **six
verification work proposals**, one per required product domain. These are
not implementation tasks, billable authorizations, human gates, claims, or
scheduler work. Their `start_authorized=false` and
`paid_calls_authorized=false` never change. A real authorized project
continuation may use them as *evidence gaps* only, after confirming current
requirements; it must not manufacture code tasks from missing audits.

## Interpreting a report

The artifact `factory-global-readiness-<github-run-id>` contains
`factory-global-product-readiness.json` with the immutable assessed SHA,
Control Plane project key, check evidence, inventory counts and six-domain
audit state. It is retained seven days. A non-zero observer run means sources
were missing, ambiguous or stale: `unverifiable_global_readiness_evidence`.
No HTTP errors, private source, token values or prompts appear in the output.

A full `passed` state is possible only when the independent Control Plane
evaluation on the **current HEAD** is already present, passed, complete and
linked to this project. This observer **does not write evaluations** or
generate this certification. Work remains until verified auth/RLS, security,
critical authenticated E2E, UX/mobile/a11y, runbooks, incidents/recovery,
and all functionality/domain coverage are actually attested. File paths,
a successful PR, specialist reviews on an older candidate, or a healthy
console do not substitute.

On a rapid succession of merges, an earlier observer deliberately fails
closed if main has moved. A later successful main CI triggers a fresh
observer automatically. No extra workflow dispatch, cron or model call is
required.

## Verification

Offline: `python -m unittest tests.test_global_readiness_evidence -v`.
For exact code gates use `.github/workflows/validate.yml` and
`factory-acceptance` on PR head. No `apps/console/**` changes means
Preview **N/A**; after human production merge the real
`workflow_run` plus artifact must be checked. A GitHub CI pass alone
does not prove that the OIDC live collector executed successfully.

No migration, public RLS grant, new run, model billing, or auto-merge.
