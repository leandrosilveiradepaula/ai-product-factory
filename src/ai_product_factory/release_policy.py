from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .gates import requires_human_gate
from .models import RiskProfile


class ReleaseEnvironment(StrEnum):
    DEV = "dev"
    PREVIEW = "preview"
    PROD = "prod"


@dataclass(frozen=True)
class ReleaseDecision:
    may_release_autonomously: bool
    human_gate_required: bool
    reasons: tuple[str, ...]


def evaluate_release(
    environment: ReleaseEnvironment,
    risk: RiskProfile | None = None,
) -> ReleaseDecision:
    risk = risk or RiskProfile()
    gate, reasons = requires_human_gate(risk)

    if environment == ReleaseEnvironment.PROD:
        prod_reasons = list(reasons)
        if "mudanca em producao" not in prod_reasons:
            prod_reasons.append("release em producao")
        return ReleaseDecision(False, True, tuple(prod_reasons))

    if gate:
        return ReleaseDecision(False, True, reasons)

    return ReleaseDecision(
        may_release_autonomously=True,
        human_gate_required=False,
        reasons=("ambiente nao-produtivo e mudanca low-risk",),
    )
