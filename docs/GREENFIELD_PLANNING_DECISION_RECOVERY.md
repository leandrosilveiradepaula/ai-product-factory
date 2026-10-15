# Greenfield planning-decision continuation (15 Oct 2026)

## Confirmed failure before it happens

The real greenfield project `infodive-service-desk` completed Discovery, Specification and initial Planning and recorded a planning decision gate. Its human-approved decision at 2026-10-15 20:33:27 UTC queued run `d5f1ea54-c388-4266-83b1-b8b06f2fd302` with stages `reconciliation,gap_analysis,planning` and zero attempts. No `factory_project_state_snapshots` row exists for this greenfield project, while the Python `ProductStageExecutor.reconciliation` requires a durable snapshot and source evidence. Therefore increasing the paid model budget **alone** would lead to a deterministic failure after the run is claimed.

Current financial guard is correct: the product worker recorded `budget_exhausted` on GitHub Actions run `38802952061`, without claiming the run or spending. The Factory's US$4.00 total cap and US$0.50 per-call reservation remain unchanged.

## Candidate correction

Migration `20261015210000_greenfield_planning_decision_resume.sql` redefines only the private `factory_resolve_human_gate` RPC. After a human-approved **greenfield** planning decision, its continuation contains `planning` only and `reconcile_first=false`. All other project kinds retain `reconciliation,gap_analysis,planning` and their original gate permissions. The Product Stage planning prompt explicitly treats previously approved `manifest.human_decisions` as binding and uses the stored `manifest.engineering_plan` rather than re-opening the same human gate.

An idempotent, bounded migration backfill fixes only existing greenfield planning-decision runs that are `created`, have zero attempts, still have a queued task, match the exact old stage sequence, and refer to an **approved** decision gate. It retains the run/task IDs, writes a durable correction audit, and does not modify claimed or completed work.

## Production rollout gate and verification

This migration changes an existing privileged Control Plane function and run metadata in production. **Do not apply without an explicit human production-migration decision**. Code merge alone does not apply SQL to Supabase, and a green CI result does not prove the DB is upgraded.

After that authorization:
1. Recheck `pg_get_functiondef('public.factory_resolve_human_gate(uuid,text,text,text)'::regprocedure)` and ensure it matches the predecessor contract; ensure the pending greenfield run has not been claimed or changed.
2. Apply the versioned migration once with migration history, not ad-hoc DML. Verify `factory_runs.metadata.stages=['planning']`, `reconcile_first=false`, audit `planning_decision.greenfield_stages_corrected`, and unchanged run/task identity and attempt counts.
3. Keep `FACTORY_MODEL_BUDGET_USD=4` and `FACTORY_MODEL_RESERVATION_USD=0.5`. The run should remain blocked by `budget_exhausted` until a **separate** explicit cost decision. No paid probes to test the migration.
4. Before allowing implementation, require an actual project GitHub repository and verified project-specific App capabilities. The Service Desk project still has `repository=NULL`. Do not claim that a plan containing 13 tasks is an executable backlog.

No auto-merge, Preview bypass, paid credit purchase, RLS widening, or additional GitHub App access is part of this patch.
