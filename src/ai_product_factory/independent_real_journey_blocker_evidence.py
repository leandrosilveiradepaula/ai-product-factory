"""Independent B4 blocker witness: factual, read-only, and never a PASS."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from scripts.audit_block1_real_journeys_readonly import (
    CRM_KEY, JourneyEvidenceUnverifiable, collect,
)


class RealJourneyBlockerEvidenceBlocked(RuntimeError):
    """Only fixed local codes; no provider response is retained."""


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
    if (not isinstance(receipt, dict)
            or receipt.get("schema") != "factory-block1-real-journey-readonly-witness-v1"
            or receipt.get("crm_project") != CRM_KEY
            or receipt.get("crm_blocker") not in allowed_crm
            or receipt.get("greenfield_blocker") not in allowed_greenfield
            or receipt.get("retired_service_desk_eligible") is not False
            or receipt.get("critical_journeys_certified") is not False
            or receipt.get("critical_e2e_certified") is not False
            or receipt.get("product_ready") is not False
            or receipt.get("writes") != 0 or receipt.get("paid_calls") != 0):
        raise RealJourneyBlockerEvidenceBlocked("real_journey_receipt_invalid")
    return VerifiedRealJourneyBlockers(receipt)
