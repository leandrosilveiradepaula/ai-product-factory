"""Read-only factual witness for real Block 1 B4 journeys, never an E2E PASS.

Only the existing CRM journey may count as an existing-project candidate.
The retired Service Desk is NEVER a valid new greenfield product.
A source/preview receipt without human merge and observed release is incomplete.
"""
from __future__ import annotations

import argparse
import json
import re
from typing import Callable

from ai_product_factory.admission_diagnostics import SupabaseAdmissionReader

CRM_REPO = "leandrosilveiradepaula/crm-infodive"
CRM_KEY = "crm-infodive"
RETIRED_GREENFIELD = frozenset({"infodive-service-desk"})
SHA = re.compile(r"[0-9a-f]{40}\Z")
UUID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\Z")


class JourneyEvidenceUnverifiable(RuntimeError):
    pass


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise JourneyEvidenceUnverifiable(reason)


def assess(*, projects: object, journeys: object,
           greenfield: object) -> dict:
    require(isinstance(projects, list) and len(projects) == 1,
            "crm_project_identity_unverifiable")
    project = projects[0]
    require(isinstance(project, dict)
            and project.get("project_key") == CRM_KEY
            and project.get("repository") == CRM_REPO
            and isinstance(project.get("id"), str)
            and UUID.fullmatch(project["id"]) is not None
            and project.get("is_active") is True,
            "crm_project_binding_invalid")
    require(isinstance(journeys, list) and 0 <= len(journeys) <= 25
            and all(isinstance(j, dict) for j in journeys),
            "crm_journey_inventory_unverifiable")
    ids = set()
    actual = []
    for j in journeys:
        require(isinstance(j.get("id"), str)
                and UUID.fullmatch(j["id"]) is not None
                and j["id"] not in ids
                and j.get("project_id") == project["id"]
                and isinstance(j.get("state"), str)
                and bool(j["state"]),
                "crm_journey_identity_invalid")
        ids.add(j["id"])
        # Superseded rows are historical, not candidates for a completed
        # lifecycle. Their identifiers and project binding were still checked.
        if j.get("state") == "superseded":
            continue
        require(j.get("request_source") in {"github-owner", "factory-console"},
                "crm_journey_source_invalid")
        if j.get("request_source") == "github-owner":
            require(j.get("issue_repository") == "leandrosilveiradepaula/ai-product-factory"
                    and type(j.get("issue_number")) is int
                    and j["issue_number"] > 0,
                    "crm_owner_start_unverified")
        if j.get("request_source") == "factory-console":
            # Console Start is legitimate only with a persisted journey; its
            # existence alone does not establish a human release decision.
            require(j.get("issue_repository") in (None, "leandrosilveiradepaula/ai-product-factory"),
                    "crm_console_start_repository_invalid")
        for sha_key in ("candidate_commit", "preview_merge_sha", "production_release_sha"):
            value = j.get(sha_key)
            require(value is None or (isinstance(value, str)
                    and SHA.fullmatch(value) is not None),
                    "crm_journey_sha_invalid")
        if j.get("production_release_sha") is not None:
            require(j.get("candidate_commit") is not None
                    and j.get("preview_merge_sha") is not None,
                    "crm_release_without_candidate_or_preview")
        if j.get("preview_merge_sha") is not None:
            require(j.get("candidate_commit") is not None,
                    "crm_preview_without_candidate")
        actual.append(j)
    # Multiple active journeys are not a single complete end-to-end proof.
    require(len(actual) <= 1, "crm_parallel_journey_ambiguous")
    current = actual[0] if actual else None
    require(isinstance(greenfield, list) and len(greenfield) <= 50
            and all(isinstance(p, dict) for p in greenfield),
            "greenfield_inventory_unverifiable")
    genuine = []
    seen = set()
    for p in greenfield:
        key = p.get("project_key")
        require(isinstance(key, str) and key and key not in seen
                and p.get("project_kind") == "greenfield",
                "greenfield_project_identity_invalid")
        seen.add(key)
        if key in RETIRED_GREENFIELD:
            continue
        if p.get("is_active") is True:
            require(isinstance(p.get("repository"), str)
                    and "/" in p["repository"],
                    "greenfield_repository_missing")
            genuine.append(key)
    # All greenfield candidates still require a human-authorized Start and
    # independent E2E receipt. Existence alone provides no readiness.
    crm_gate = ("legitimate_existing_start_missing" if current is None else
                "human_merge_or_release_unverified" if current.get("production_release_sha") is None else
                "independent_full_journey_e2e_unverified")
    return {
        "schema": "factory-block1-real-journey-readonly-witness-v1",
        "crm_project": CRM_KEY,
        "crm_journey_id": current["id"] if current else None,
        "crm_journey_state": current["state"] if current else None,
        "crm_candidate_sha": current.get("candidate_commit") if current else None,
        "crm_production_release_sha_observed": bool(
            current and current.get("production_release_sha")),
        "crm_blocker": crm_gate,
        "retired_service_desk_eligible": False,
        "other_active_greenfield_count": len(genuine),
        "greenfield_blocker": ("legitimate_human_authorized_greenfield_journey_unverified"
                               if genuine else "legitimate_new_greenfield_target_missing"),
        "critical_journeys_certified": False,
        "critical_e2e_certified": False,
        "product_ready": False,
        "writes": 0,
        "paid_calls": 0,
    }


def collect(get: Callable[[str], object]) -> dict:
    projects = get("factory_projects?select=id,project_key,repository,is_active"
                   "&project_key=eq.crm-infodive&limit=2")
    if not isinstance(projects, list) or len(projects) != 1:
        raise JourneyEvidenceUnverifiable("crm_project_source_unavailable")
    pid = projects[0].get("id") if isinstance(projects[0], dict) else None
    require(isinstance(pid, str) and UUID.fullmatch(pid) is not None,
            "crm_project_source_invalid")
    journeys = get("factory_journeys?select=id,project_id,state,request_source,"
                   "issue_repository,issue_number,candidate_commit,preview_merge_sha,"
                   "production_release_sha,created_at&project_id=eq." + pid
                   + "&order=created_at.desc&limit=26")
    require(isinstance(journeys, list) and len(journeys) <= 25,
            "crm_journey_inventory_limit_exceeded")
    greenfield = get("factory_projects?select=project_key,project_kind,repository,is_active"
                     "&project_kind=eq.greenfield&limit=51")
    require(isinstance(greenfield, list) and len(greenfield) <= 50,
            "greenfield_inventory_limit_exceeded")
    return assess(projects=projects, journeys=journeys, greenfield=greenfield)


def main() -> int:
    parser = argparse.ArgumentParser(description="Real journey witness; never an E2E pass")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        receipt = collect(SupabaseAdmissionReader()._get)
    except (JourneyEvidenceUnverifiable, ValueError, RuntimeError,
            OSError, KeyError, TypeError, UnicodeError):
        print(json.dumps({"status": "unverifiable",
                          "critical_e2e_certified": False,
                          "product_ready": False}))
        return 2
    from pathlib import Path
    Path(args.output).write_text(json.dumps(receipt, sort_keys=True) + "\n",
                                 encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
