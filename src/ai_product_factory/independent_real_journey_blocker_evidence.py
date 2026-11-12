"""Independent B4 blocker witness: factual, read-only, and never a PASS."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from scripts.audit_block1_real_journeys_readonly import (
    CRM_KEY, JourneyEvidenceUnverifiable, SHA, UUID, collect,
)


class RealJourneyBlockerEvidenceBlocked(RuntimeError):
    """Only fixed local codes; no provider response is retained."""


RECEIPT_FIELDS = frozenset({
    "schema", "crm_project", "crm_journey_id", "crm_journey_state",
    "crm_candidate_sha", "crm_production_release_sha_observed", "crm_blocker",
    "retired_service_desk_eligible", "other_active_greenfield_count",
    "greenfield_blocker", "critical_journeys_certified", "critical_e2e_certified",
    "product_ready", "writes", "paid_calls",
})


@dataclass(frozen=True)
class VerifiedRealJourneyBlockers:
    receipt_value: dict

    def receipt(self) -> dict:
        return self.receipt_value


def verify_real_journey_blockers(*, control_plane_get: Callable[[str], object]) -> VerifiedRealJourneyBlockers:
    try:
        receipt = collect(control_plane_get)
    except (JourneyEvidenceUnverifiable, ValueError, RuntimeError, OSError,
            KeyError, TypeError, UnicodeError) as exc:
        raise RealJourneyBlockerEvidenceBlocked("real_journey_source_unavailable") from exc
    allowed_crm = {
        "legitimate_existing_start_missing", "human_merge_or_release_unverified",
        "independent_full_journey_e2e_unverified",
    }
    allowed_greenfield = {
        "legitimate_new_greenfield_target_missing",
        "legitimate_human_authorized_greenfield_journey_unverified",
    }
    if (not isinstance(receipt, dict) or set(receipt) != RECEIPT_FIELDS
            or receipt.get("schema") != "factory-block1-real-journey-readonly-witness-v1"
            or receipt.get("crm_project") != CRM_KEY
            or (receipt.get("crm_journey_id") is not None
                and (not isinstance(receipt["crm_journey_id"], str)
                     or UUID.fullmatch(receipt["crm_journey_id"]) is None))
            or (receipt.get("crm_journey_state") is not None
                and (not isinstance(receipt["crm_journey_state"], str)
                     or not receipt["crm_journey_state"]))
            or (receipt.get("crm_candidate_sha") is not None
                and (not isinstance(receipt["crm_candidate_sha"], str)
                     or SHA.fullmatch(receipt["crm_candidate_sha"]) is None))
            or type(receipt.get("crm_production_release_sha_observed")) is not bool
            or receipt.get("crm_blocker") not in allowed_crm
            or receipt.get("greenfield_blocker") not in allowed_greenfield
            or receipt.get("retired_service_desk_eligible") is not False
            or receipt.get("critical_journeys_certified") is not False
            or receipt.get("critical_e2e_certified") is not False
            or receipt.get("product_ready") is not False
            or type(receipt.get("other_active_greenfield_count")) is not int
            or receipt["other_active_greenfield_count"] < 0
            or type(receipt.get("writes")) is not int or receipt["writes"] != 0
            or type(receipt.get("paid_calls")) is not int or receipt["paid_calls"] != 0):
        raise RealJourneyBlockerEvidenceBlocked("real_journey_receipt_invalid")
    return VerifiedRealJourneyBlockers(receipt)
