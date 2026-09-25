from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .evidence import EvidenceBundle
from .models import RiskProfile
from .release_policy import ReleaseDecision, ReleaseEnvironment, evaluate_release


@dataclass(frozen=True)
class DeploymentRequest:
    project_key: str
    environment: ReleaseEnvironment
    candidate_commit: str
    evidence: EvidenceBundle
    risk: RiskProfile = RiskProfile()


@dataclass(frozen=True)
class DeploymentResult:
    provider: str
    environment: ReleaseEnvironment
    status: str
    deployment_ref: str | None = None
    preview_url: str | None = None


class DeploymentAdapter(Protocol):
    name: str

    def deploy(self, request: DeploymentRequest) -> DeploymentResult:
        ...


class DeploymentCoordinator:
    def authorize(self, request: DeploymentRequest) -> ReleaseDecision:
        if request.evidence.candidate_commit != request.candidate_commit:
            raise ValueError("evidence candidate_commit does not match deployment candidate")
        if request.evidence.ci_status != "success":
            raise ValueError("deployment requires successful CI evidence")
        metadata = request.evidence.metadata or {}
        if metadata.get("quality_gate_passed") is False:
            raise ValueError("deployment requires passed quality gate")
        return evaluate_release(request.environment, request.risk)

    def deploy_if_autonomous(
        self,
        adapter: DeploymentAdapter,
        request: DeploymentRequest,
    ) -> DeploymentResult:
        decision = self.authorize(request)
        if decision.human_gate_required:
            raise PermissionError("; ".join(decision.reasons))
        return adapter.deploy(request)
