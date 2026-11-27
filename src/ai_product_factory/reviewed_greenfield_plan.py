"""Versioned, source-reviewed recovery for one authorized greenfield journey.

This is an explicitly assisted plan, not a model response or general retry.
No request-supplied task list is accepted. Production remains human-gated.
"""
from __future__ import annotations

import copy
import hashlib
import json

_RECORD = json.loads("{\"plan_id\":\"dark-greenfield-reviewed-plan-20261126-v1\",\"run_id\":\"13fc575b-af98-4eb3-a5b8-01dce69ec8af\",\"task_id\":\"e30ee0cb-0be3-4ddc-a10e-d653d25fa266\",\"project_id\":\"19f0f200-3777-46c6-969a-acf0d3426ff1\",\"project_key\":\"dark-channel-studio\",\"journey_id\":\"c43e7781-7cb9-49fd-8459-cc358880df0a\",\"request_id\":\"0b6ab27d-11eb-acf6-1392-50857d8d854c\",\"source_run_id\":\"1ed3c5d1-fc2a-4bab-a4a9-12f53bc83c29\",\"source_commit\":\"55e8e8d8422ee044eb1112ab678cb0223e987742\",\"request_digest\":\"6325ff172bc0e73417bd365767deef78136ed016333e3d591adf921e8833888d\",\"repository\":\"leandrosilveiradepaula/dark-channel-studio\",\"generation\":1,\"source_blobs\":{\"app/server.js\":\"b3e0526b16d85cebd7ace53355e3a2422817772e\",\"app/editorial.js\":\"bce5fa1503e77f89de108d4b90e9baea68bdc4dd\",\"app/server.test.js\":\"018d5954cba3bb2a81a15d04d7ab5f7d600b22ad\",\"app/editorial.test.js\":\"8282e27835c7a3e744df2cb59725cef33e52362d\",\"app/editorial-server.test.js\":\"08041e8949f0833bb136777778d19cbf5795cb33\",\"src/domain/contracts.ts\":\"8a4dac6aa68c98a20be6d9e0f135ba4c749983f9\",\"src/domain/project-input.ts\":\"ec5b388721967c263701630600c8aaa22f04fd85\",\"src/domain/prompts.ts\":\"9dd9f9842e942d416cf346946311835bcc25920e\",\"src/components/projects/ProjectWorkspace.tsx\":\"0ad3366fce5242e3e4ae3ad38ff9d7a37a032bdf\",\"src/components/storyboards/StoryboardExportWorkspace.tsx\":\"95b504886b0f285fd7c64e967ca7a54981f9acb2\",\"supabase/migrations/20261116132000_tenant_persistence_rls.sql\":\"d940e4d8d94f6e03127fa43bb95d88996d882902\",\"supabase/tests/tenant_persistence_rls.sql\":\"2100b7192704c23ddcb9212b386fc6a460488ef9\",\"docs/PERSISTENCE_RLS_OPERATIONS.md\":\"bd9564cecf127a689399bd816b91458af464c72d\",\".github/workflows/validate.yml\":\"e85998aea1f9ac0634b4478f4380742f7cd3b72e\",\"scripts/verify_migration_forward_recovery.sh\":\"e344c5cfd39e18e6c4cfcee871c2d8323bb8bc46\",\"src/e2e/project-production-flow.test.ts\":\"9029e8840f6878790c8ba9e4b8a5e9c65ac38059\",\"app/README.md\":\"108bc77172fa071e9253fb19e071b0ae518bd7b8\"},\"plan\":{\"architecture\":\"Extend the existing authenticated Studio HTTP application, PostgreSQL tenant boundary and editorial domain; no replacement application, fake persistence, publication or paid service activation. Candidate changes only.\",\"workstreams\":[\"Tenant-safe catalogs and project lifecycle\",\"Structured editorial production and storyboard\",\"Review, versions and exports\",\"Authenticated workflow and access\"],\"tasks\":[{\"task_key\":\"studio-lifecycle-contract\",\"title\":\"Complete Studio durable lifecycle contract\",\"description\":\"Author one additive migration candidate against the actual existing schema. Close missing archive/restore and audit flows while preserving append-only documents, memberships, forced RLS, actor identity, composite tenant FKs and atomic reviewer decisions. No migration application to any remote database. Update isolated CI to exercise both versions in order.\",\"complexity\":\"medium\",\"preferred_agent_role\":\"development\",\"required_capabilities\":[\"implementation\",\"migration_authoring\"],\"scope_keys\":[\"supabase/migrations/20261126160500_studio_editorial_lifecycle.sql\",\"supabase/tests/tenant_persistence_rls.sql\",\".github/workflows/validate.yml\",\"scripts/verify_migration_forward_recovery.sh\",\"docs/PERSISTENCE_RLS_OPERATIONS.md\"],\"context_paths\":[\"supabase/migrations/20261116132000_tenant_persistence_rls.sql\",\"supabase/tests/tenant_persistence_rls.sql\",\".github/workflows/validate.yml\",\"scripts/verify_migration_forward_recovery.sh\"],\"depends_on\":[],\"acceptance_criteria\":[\"Operator-only catalogs and authorized project archive/restore are durable and tenant-isolated; no deletion or broader membership grants.\",\"Restoring content creates a new draft/version rather than rewriting reviewed history; project lifecycle changes and document/review/export events are attributable to the authenticated actor.\",\"Migration is additive, invoker-only, independently rollback-tested on isolated PostgreSQL and not applied to remote data; unauthorized and cross-tenant cases are rejected.\"],\"risk\":{\"production_change\":false,\"destructive_data_change\":false,\"expands_sensitive_access\":false,\"new_paid_service\":false,\"material_requirement_change\":false}},{\"task_key\":\"studio-catalog-workspace\",\"title\":\"Deliver channel, profile and project management\",\"description\":\"Complete real operator channel/profile creation and editing, profile settings and project creation/edit/archive/restore in the actual HTTP portal. Reuse existing domain contracts and the candidate lifecycle migration. Provide clear empty/error/loading states, escaped accessible forms, authenticated tenant-specific requests and real persisted results.\",\"complexity\":\"medium\",\"preferred_agent_role\":\"development\",\"required_capabilities\":[\"implementation\"],\"scope_keys\":[\"app/server.js\",\"app/server.test.js\"],\"context_paths\":[\"app/server.js\",\"app/server.test.js\",\"src/domain/contracts.ts\",\"src/domain/project-input.ts\",\"src/components/projects/ProjectWorkspace.tsx\"],\"depends_on\":[\"studio-lifecycle-contract\"],\"acceptance_criteria\":[\"A logged-in operator can create and edit channels and profiles, select them and create/manage a project with persisted settings.\",\"Author/reviewer/operator roles are enforced by JWT and RLS, including denied direct cross-tenant mutations and non-operator catalog changes.\",\"Archive/restore uses the authorized lifecycle contract, with meaningful feedback and preserved history; authenticated HTTP regression exercises the workflow.\"],\"risk\":{\"production_change\":false,\"destructive_data_change\":false,\"expands_sensitive_access\":false,\"new_paid_service\":false,\"material_requirement_change\":false}},{\"task_key\":\"studio-editorial-production\",\"title\":\"Deliver structured script, scene and prompt production\",\"description\":\"Integrate the existing editorial validation and domain prompt generators into an actionable production flow, not only pasted free text. Support briefing/research sources, chapters/segments, SEO/thumbnail, timecoded SRT, scene map, numbered persistent references, DNA and ordered image/video/hybrid/IV output. Keep optional external generation adapters disabled unless separately authorized. Do not claim unavailable normative attachments are verified.\",\"complexity\":\"medium\",\"preferred_agent_role\":\"development\",\"required_capabilities\":[\"implementation\"],\"scope_keys\":[\"app/editorial.js\",\"app/editorial.test.js\",\"src/domain/prompts.ts\",\"app/server.js\",\"app/editorial-server.test.js\"],\"context_paths\":[\"app/editorial.js\",\"app/editorial.test.js\",\"src/domain/contracts.ts\",\"src/domain/prompts.ts\",\"app/server.js\",\"app/editorial-server.test.js\"],\"depends_on\":[\"studio-catalog-workspace\"],\"acceptance_criteria\":[\"Structured authored material and sources persist as versions; SRT/scene map precede prompts and validate real timecodes and complete scene coverage.\",\"Each prompt references its scene, numbered reference assets/DNA and, for IV, the matching image; modes keep correct image and video outputs separated.\",\"Malformed, incomplete, conflicting and out-of-order production is blocked with actionable errors; no paid model or publishing action is enabled.\"],\"risk\":{\"production_change\":false,\"destructive_data_change\":false,\"expands_sensitive_access\":false,\"new_paid_service\":false,\"material_requirement_change\":false}},{\"task_key\":\"studio-reviewed-export\",\"title\":\"Complete version review and delivery exports\",\"description\":\"Finish authenticated document/scene/prompt editing, version history and restoration, reviewer return/approval, and approved-only separate TXT, JSON and CSV exports for scripts, captions, reference assets and prompt sets. Preserve clean prompt lines and project/reference/scene/version lineage; integrate the real portal rather than leaving unused workspace components as evidence.\",\"complexity\":\"medium\",\"preferred_agent_role\":\"development\",\"required_capabilities\":[\"implementation\"],\"scope_keys\":[\"app/server.js\",\"app/editorial.js\",\"app/editorial.test.js\",\"app/editorial-server.test.js\",\"src/e2e/project-production-flow.test.ts\",\"app/README.md\"],\"context_paths\":[\"app/server.js\",\"app/editorial.js\",\"app/editorial.test.js\",\"app/editorial-server.test.js\",\"src/components/storyboards/StoryboardExportWorkspace.tsx\",\"src/e2e/project-production-flow.test.ts\",\"app/README.md\"],\"depends_on\":[\"studio-editorial-production\"],\"acceptance_criteria\":[\"Authenticated user can inspect versions and review feedback, restore to a fresh draft where permitted, submit complete production, and receive a real reviewer decision; history is never overwritten.\",\"Only complete approved versions export; TXT is clean, JSON and CSV retain lineage and consistent references, with appropriate escaping; failed or stale approvals do not export.\",\"Actual authenticated HTTP flow covers create-to-review-to-export and denied roles/tenants, clear mobile and keyboard-friendly actions, and recoverable errors. Independent real Preview remains required.\"],\"risk\":{\"production_change\":false,\"destructive_data_change\":false,\"expands_sensitive_access\":false,\"new_paid_service\":false,\"material_requirement_change\":false}}],\"specialist_reviews\":[\"security\",\"qa\",\"operations\"],\"dependencies\":[\"Use original approved specification and completed discovery, current exact-SHA source, existing Studio Auth and dedicated database.\",\"Candidate migration and application configuration must receive their independent environment/human gates; never treat isolated DB or mock HTTP as real Preview.\"],\"test_strategy\":[\"Execute existing unit/domain, HTTP and isolated real PostgreSQL role regression on candidate; independent security, QA and operations validate actual authenticated Preview and complete editorial flow.\",\"Verify all original acceptance requirements, including applicable normative skill attachments. Missing attachments, any unverified requirement, or unavailable preview data remain explicit blockers; no fabricated PASS.\"],\"release_strategy\":\"Await real verified Preview, quality evidence and human production gate. Do not merge or publish automatically, apply migrations, change credentials or activate paid services.\",\"risks\":[\"Existing runtime/domain divergence and current schema lifecycle restrictions; candidate SQL must not expand sensitive access.\",\"Assisted planning provenance is not evidence that autonomous model planning works. Existing unresolved requirements remain visible until independently verified.\"],\"decisions_needed\":[]}}")
_ADMISSION = "_reviewed_plan_admission"
_VERIFIED = "_verified_reviewed_plan"


def _check_identity(context, record):
    binding = context.get("journey_binding_v2")
    snapshot = context.get("journey_request")
    origin = context.get("_verified_resume_origin")
    manifest = context.get("manifest")
    if (not isinstance(binding, dict) or not isinstance(snapshot, dict)
            or not isinstance(origin, dict) or not isinstance(manifest, dict)
            or manifest.get("onboarding_mode") != "greenfield"
            or manifest.get("source") != "factory-console"
            or any(binding.get(k) != record[k] for k in
                   ("project_id", "journey_id", "request_id", "repository", "source_commit"))
            or binding.get("execution_generation") != record["generation"]
            or binding.get("source_mode") != "main_snapshot"
            or snapshot.get("digest") != record["request_digest"]
            or not isinstance(snapshot.get("text"), str)
            or hashlib.sha256(snapshot["text"].encode()).hexdigest() != record["request_digest"]
            or snapshot.get("source") != "github-owner"
            or snapshot.get("authorization_event_id") != "7162981651"
            or snapshot.get("control_issue_number") != 1055
            or snapshot.get("control_issue_repository") != "leandrosilveiradepaula/ai-product-factory"
            or origin.get("source_run_id") != record["source_run_id"]
            or origin.get("snapshot_id") != record["source_commit"]
            or origin.get("request_id") != record["request_id"]
            or origin.get("generation") != record["generation"]
            or origin.get("prior_kind") != "greenfield"):
        raise PermissionError("reviewed_plan_identity_invalid")


def admit_reviewed_plan(run_id, task_id, project_id, epoch, context, metadata):
    # Internal receipts may only be minted from claimed durable metadata.
    out = {k: v for k, v in context.items() if k not in {_ADMISSION, _VERIFIED}}
    marker = metadata.get("reviewed_plan_recovery")
    if run_id != _RECORD["run_id"]:
        if marker is not None:
            raise PermissionError("reviewed_plan_unknown_run")
        return out
    if (marker != _RECORD["plan_id"] or task_id != _RECORD["task_id"]
            or project_id != _RECORD["project_id"] or epoch != _RECORD["generation"]):
        raise PermissionError("reviewed_plan_admission_invalid")
    _check_identity(out, _RECORD)
    out[_ADMISSION] = _RECORD["plan_id"]
    return out


def verify_reviewed_plan_source(context, github):
    out = {k: v for k, v in context.items() if k != _VERIFIED}
    if _ADMISSION not in out:
        return out
    if out[_ADMISSION] != _RECORD["plan_id"]:
        raise PermissionError("reviewed_plan_admission_invalid")
    _check_identity(out, _RECORD)
    candidate = out.get("current_state_facts", {}).get("live_candidate")
    if (not isinstance(candidate, dict)
            or candidate.get("observed_from") != "journey_delivery_binding_v2"
            or candidate.get("repository") != _RECORD["repository"]
            or candidate.get("journey_id") != _RECORD["journey_id"]
            or candidate.get("sha") != _RECORD["source_commit"]):
        raise PermissionError("reviewed_plan_live_source_invalid")
    total = 0
    for path, expected in _RECORD["source_blobs"].items():
        raw = github.get_file_text(path, ref=_RECORD["source_commit"]).encode("utf-8")
        total += len(raw)
        if len(raw) > 200_000 or total > 700_000:
            raise PermissionError("reviewed_plan_source_size_invalid")
        actual = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw,
                              usedforsecurity=False).hexdigest()
        if actual != expected:
            raise PermissionError("reviewed_plan_source_blob_mismatch")
    out[_VERIFIED] = _RECORD["plan_id"]
    return out


def reviewed_plan_output(item, stage):
    context = item.context
    if item.run_id != _RECORD["run_id"]:
        if _ADMISSION in context or _VERIFIED in context:
            raise PermissionError("reviewed_plan_unknown_run")
        return None
    if (stage != "planning" or tuple(item.stages) != ("planning",)
            or item.task_id != _RECORD["task_id"] or item.project_id != _RECORD["project_id"]
            or item.project_key != _RECORD["project_key"] or item.journey_id != _RECORD["journey_id"]
            or item.execution_generation != _RECORD["generation"]
            or context.get(_ADMISSION) != _RECORD["plan_id"]
            or context.get(_VERIFIED) != _RECORD["plan_id"]
            or context.get("current_state_facts", {}).get("operator_recovery") is not None):
        raise PermissionError("reviewed_plan_execution_invalid")
    _check_identity(context, _RECORD)
    out = copy.deepcopy(_RECORD["plan"])
    out["_evidence"] = {
        "kind": "reviewed_source_plan", "role": "assisted_planning",
        "source_ref": _RECORD["plan_id"], "source_commit": _RECORD["source_commit"],
        "source_blobs": dict(_RECORD["source_blobs"]), "model_invoked": False,
        "autonomous_model_planning": False, "usage": {},
    }
    return out
