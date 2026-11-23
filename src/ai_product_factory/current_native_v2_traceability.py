"""Current-SHA, read-only CRM V2 traceability evidence.

This is deliberately separate from the historical-artifact verifier.  The
underlying V2 audit reads the durable Control Plane lineage and the exact
GitHub/Preview facts again on the current trusted post-CI runner, so expired
artifacts can never make a current assessment pass or fail by themselves.
"""
from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping

from .autonomy_journey_reader import SupabaseJourneyReader
from .native_v2_journey_audit import EvidenceBlocked, audit_existing_native_v2
from .product_readiness_certification import VerifiedCriterionEvidence

REPO = "leandrosilveiradepaula/ai-product-factory"
OWNER_WORKFLOW = ".github/workflows/autonomous-runner.yml"
PROJECT_KEY = "crm-infodive"
JOURNEY_ID = "bb14e150-2c7e-423b-8e5d-e211dab6225c"
SHA = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)


class CurrentTraceabilityBlocked(RuntimeError):
    """Fail-closed, fixed-vocabulary source-verification failure."""


def require(value: bool, code: str) -> None:
    if not value:
        raise CurrentTraceabilityBlocked(code)


def verify_current_crm_v2_traceability(*, repository: str, assessed_commit: str,
                                       github_get: Callable[[str], object],
                                       reader: SupabaseJourneyReader | None = None,
                                       environment: Mapping[str, str] | None = None,
                                       audit=audit_existing_native_v2) -> VerifiedCriterionEvidence:
    """Re-run the bounded V2 audit in the exact post-CI trusted identity."""
    env = os.environ if environment is None else environment
    require(
        repository == REPO and isinstance(assessed_commit, str)
        and SHA.fullmatch(assessed_commit) is not None
        and env.get("GITHUB_ACTIONS") == "true"
        and env.get("GITHUB_REPOSITORY") == REPO
        and env.get("GITHUB_EVENT_NAME") == "workflow_run"
        and env.get("GITHUB_REF") == "refs/heads/main"
        and env.get("GITHUB_WORKFLOW_REF") == REPO + "/" + OWNER_WORKFLOW + "@refs/heads/main",
        "current_v2_runner_identity_invalid",
    )
    run_id = env.get("GITHUB_RUN_ID", "")
    require(run_id.isdecimal() and 0 < int(run_id) < 10**18, "current_v2_runner_id_invalid")
    prefix = "/repos/" + REPO
    current = github_get(prefix + "/actions/runs/" + run_id)
    require(
        isinstance(current, dict) and current.get("id") == int(run_id)
        and current.get("name") == "Factory autonomous runner"
        and current.get("path") == OWNER_WORKFLOW
        and current.get("event") == "workflow_run"
        and current.get("head_branch") == "main"
        and current.get("head_sha") == assessed_commit
        and current.get("run_attempt") == 1,
        "current_v2_runner_unbound",
    )
    try:
        receipt = audit(
            reader=reader if reader is not None else SupabaseJourneyReader(),
            project_key=PROJECT_KEY, journey_id=JOURNEY_ID,
        )
    except EvidenceBlocked as exc:
        raise CurrentTraceabilityBlocked("current_v2_audit_blocked") from exc
    require(
        isinstance(receipt, dict)
        and receipt.get("schema_version") == 1
        and receipt.get("project_key") == PROJECT_KEY
        and receipt.get("journey_id") == JOURNEY_ID
        and receipt.get("requirement_met") is True
        and receipt.get("status") == "integrated_nonproduction"
        and receipt.get("production_released") is False
        and receipt.get("product_ready") is False
        and receipt.get("paid_calls") == 0 and receipt.get("writes") == 0,
        "current_v2_audit_scope_invalid",
    )
    latest = github_get(prefix + "/git/ref/heads/main")
    require(
        isinstance(latest, dict) and isinstance(latest.get("object"), dict)
        and latest["object"].get("sha") == assessed_commit,
        "current_v2_main_changed_while_verifying",
    )
    return VerifiedCriterionEvidence(
        domain="observability_operations", criterion="traceability",
        repository=repository, assessed_commit=assessed_commit,
        verification_state="observed",
        source="current-readonly-native-v2-audit:" + run_id,
        evidence=("https://github.com/" + repository + "/actions/runs/" + run_id + "#sha=" + assessed_commit,),
        retained_receipt=receipt,
    )
