from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .review_gate import EvalResult, QualityGateDecision, ReviewFinding


@dataclass(frozen=True)
class EvidenceBundle:
    source_commit: str | None
    candidate_commit: str | None
    ci_status: str
    findings: tuple[ReviewFinding, ...] = ()
    evals: tuple[EvalResult, ...] = ()
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_commit": self.source_commit,
            "candidate_commit": self.candidate_commit,
            "ci_status": self.ci_status,
            "findings": [asdict(x) for x in self.findings],
            "evals": [asdict(x) for x in self.evals],
            "metadata": dict(self.metadata or {}),
        }


def build_quality_evidence(
    *,
    source_commit: str | None,
    candidate_commit: str | None,
    ci_status: str,
    decision: QualityGateDecision,
    findings: tuple[ReviewFinding, ...] = (),
    evals: tuple[EvalResult, ...] = (),
    metadata: dict[str, Any] | None = None,
) -> EvidenceBundle:
    merged_metadata = dict(metadata or {})
    merged_metadata["quality_gate_passed"] = decision.passed
    merged_metadata["quality_gate_reasons"] = list(decision.reasons)
    return EvidenceBundle(
        source_commit=source_commit,
        candidate_commit=candidate_commit,
        ci_status=ci_status,
        findings=findings,
        evals=evals,
        metadata=merged_metadata,
    )
