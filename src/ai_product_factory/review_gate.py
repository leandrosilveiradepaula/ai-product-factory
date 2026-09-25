from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True)
class ReviewFinding:
    code: str
    severity: Severity
    message: str
    path: str | None = None


@dataclass(frozen=True)
class EvalResult:
    name: str
    passed: bool
    required: bool = True
    score: float | None = None
    details: str | None = None


@dataclass(frozen=True)
class QualityGateDecision:
    passed: bool
    reasons: tuple[str, ...]
    critical_findings: tuple[ReviewFinding, ...]
    failed_required_evals: tuple[EvalResult, ...]


def evaluate_quality_gate(
    *,
    findings: tuple[ReviewFinding, ...] = (),
    evals: tuple[EvalResult, ...] = (),
) -> QualityGateDecision:
    critical = tuple(f for f in findings if f.severity == Severity.CRITICAL)
    errors = tuple(f for f in findings if f.severity == Severity.ERROR)
    failed_required = tuple(e for e in evals if e.required and not e.passed)

    reasons: list[str] = []
    if critical:
        reasons.append(f"{len(critical)} critical review finding(s)")
    if errors:
        reasons.append(f"{len(errors)} error review finding(s)")
    if failed_required:
        reasons.append(f"{len(failed_required)} required evaluation(s) failed")

    return QualityGateDecision(
        passed=not critical and not errors and not failed_required,
        reasons=tuple(reasons) if reasons else ("quality gates passed",),
        critical_findings=critical,
        failed_required_evals=failed_required,
    )
