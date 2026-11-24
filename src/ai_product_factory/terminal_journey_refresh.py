"""Only a legitimate next V2 intake can refresh a terminal source policy.
No production merge, no model, no force push. The DB independently fences
authorization, project, epoch, previous terminal delivery and request.
"""
from __future__ import annotations

import re
from uuid import UUID

from .journey_delivery_binding import JourneyBindingBlocked

_SHA = re.compile(r"[a-f0-9]{40}\Z")


def _ancestor(github, old: str, new: str) -> bool:
    if not isinstance(old, str) or not _SHA.fullmatch(old) or not _SHA.fullmatch(new):
        return False
    comparison = github.compare_commits(old, new)
    return (isinstance(comparison, dict)
            and comparison.get("status") in {"identical", "ahead"}
            and type(comparison.get("behind_by")) is int and comparison["behind_by"] == 0
            and type(comparison.get("ahead_by")) is int
            and comparison["ahead_by"] >= 0
            and ((old == new and comparison["status"] == "identical" and comparison["ahead_by"] == 0)
                 or (old != new and comparison["status"] == "ahead" and comparison["ahead_by"] > 0)))


def refresh_terminal_source(*, queue, github, project: dict, control: dict, journey: dict) -> dict:
    policy = project.get("manifest", {}).get("journey_delivery_binding_v2", {})
    if (journey.get("state") not in {"awaiting_source", "intake_accepted"}
            or journey.get("project_id") != project.get("id")
            or control.get("state") != "running"
            or getattr(github, "repository", None) != project.get("repository")
            or not isinstance(policy, dict) or policy.get("source_mode") != "main_snapshot"):
        raise JourneyBindingBlocked("journey_terminal_refresh_identity_invalid")
    try:
        journey_id = str(UUID(journey["id"]))
    except (KeyError, ValueError, TypeError, AttributeError):
        raise JourneyBindingBlocked("journey_terminal_refresh_identity_invalid") from None
    if journey_id != journey["id"] or not isinstance(policy.get("digest"), str):
        raise JourneyBindingBlocked("journey_terminal_refresh_identity_invalid")
    params = {"p_project_key": project["project_key"], "p_journey_id": journey_id,
              "p_expected_generation": control["generation"], "p_expected_version": control["version"],
              "p_expected_policy_digest": policy["digest"]}
    try:
        plan = queue._rpc("factory_plan_terminal_journey_refresh_v2", params)
    except RuntimeError:
        raise JourneyBindingBlocked("journey_terminal_refresh_not_authorized_or_not_quiescent") from None
    ref = "preview/journey-base-" + journey_id
    if (not isinstance(plan, dict) or plan.get("project_id") != project["id"]
            or plan.get("repository") != project["repository"] or plan.get("journey_id") != journey_id
            or plan.get("request_id") != journey.get("request_id")
            or plan.get("preview_ref") != ref or plan.get("prior_policy_digest") != policy["digest"]
            or plan.get("generation") != control["generation"] or plan.get("version") != control["version"]
            or plan.get("prior_source_sha") != policy.get("source_commit_pin")):
        raise JourneyBindingBlocked("journey_terminal_refresh_plan_invalid")
    main = github.get_branch_sha("main")
    if not isinstance(main, str) or not _SHA.fullmatch(main):
        raise JourneyBindingBlocked("journey_terminal_refresh_main_invalid")
    if not _ancestor(github, plan["prior_source_sha"], main):
        raise JourneyBindingBlocked("journey_terminal_refresh_source_diverged")
    # CRITICAL: a closed Preview-only journey is not a release. Never discard
    # its deliverable when rotating to current main. Human release is separate.
    if not _ancestor(github, plan.get("prior_delivery_sha"), main):
        raise JourneyBindingBlocked("journey_prior_preview_not_released")
    if github.get_branch_sha("main") != main or queue._rpc("factory_plan_terminal_journey_refresh_v2", params) != plan:
        raise JourneyBindingBlocked("journey_terminal_refresh_preflight_changed")
    # Explicit per-project opt-in is checked by both SQL preflights. This may
    # create exactly one Preview base for the actual request, never a deployment
    # request for a synthetic test. An existing ref must have the exact SHA.
    if github.ensure_branch_at_sha(ref, main) != main:
        raise JourneyBindingBlocked("journey_terminal_refresh_preview_invalid")
    if (github.get_branch_sha("main") != main or github.get_branch_sha(ref) != main
            or not _ancestor(github, plan["prior_delivery_sha"], main)):
        raise JourneyBindingBlocked("journey_terminal_refresh_refs_changed")
    evidence = {"repository": project["repository"], "main_sha": main, "preview_sha": main,
                "preview_ref": ref, "prior_source_sha": plan["prior_source_sha"],
                "prior_delivery_sha": plan["prior_delivery_sha"], "source_ancestor_verified": True,
                "delivery_ancestor_verified": True, "verification_source": "github_exact_refs",
                "production_release_authorized": False}
    result = queue._rpc("factory_commit_terminal_journey_refresh_v2", params | {"p_evidence": evidence})
    if (not isinstance(result, dict) or result.get("status") != "rotated"
            or result.get("journey_id") != journey_id or result.get("source_commit") != main
            or result.get("preview_ref") != ref or result.get("production_release_authorized") is not False
            or result.get("generation") != control["generation"] + 1
            or result.get("version") != control["version"] + 1):
        raise JourneyBindingBlocked("journey_terminal_refresh_receipt_invalid")
    return result
