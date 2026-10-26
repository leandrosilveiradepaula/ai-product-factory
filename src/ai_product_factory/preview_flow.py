from __future__ import annotations
from dataclasses import dataclass
from .browser_evidence import BrowserEvidence,BrowserEvidenceAdapter
from .browser_evidence_store import BrowserEvidenceRecorder
from .deployment import DeploymentAdapter,DeploymentCoordinator,DeploymentRequest,DeploymentResult
from .release_policy import ReleaseEnvironment
from .preview_session_probe import is_session_backend_503

@dataclass(frozen=True)
class VerifiedPreviewResult:
 deployment:DeploymentResult
 browser_evidence:BrowserEvidence

class PreviewDeferred(RuntimeError):
 def __init__(self,deployment:DeploymentResult)->None:
  super().__init__(f"preview deferred: {deployment.status}")
  self.deployment=deployment

class PreviewExternalBackendUnavailable(RuntimeError):
 def __init__(self,preview_url:str)->None:
  super().__init__("Preview backend unavailable: browser HTTP 503 /api/session")
  self.preview_url=preview_url


class VerifiedPreviewCoordinator:
 def __init__(self,*,deployment:DeploymentCoordinator|None=None)->None:self.deployment=deployment or DeploymentCoordinator()
 def execute(self,*,run_id:str,request:DeploymentRequest,deployment_adapter:DeploymentAdapter,browser_adapter:BrowserEvidenceAdapter,evidence_recorder:BrowserEvidenceRecorder)->VerifiedPreviewResult:
  if request.environment is not ReleaseEnvironment.PREVIEW:raise PermissionError("verified preview flow refuses non-preview environments")
  deployed=self.deployment.deploy_if_autonomous(deployment_adapter,request)
  if deployed.status=="blocked_quota":raise PreviewDeferred(deployed)
  if deployed.status!="success":raise RuntimeError("preview deployment did not succeed")
  if not deployed.preview_url:raise RuntimeError("preview deployment did not provide a preview URL")
  evidence=browser_adapter.verify(deployed.preview_url)
  # A missing hosted backend is an EXTERNAL configuration dependency, not a
  # failed implementation. Keep the real browser failure durable and prevent
  # release, but let the scheduled Preview preflight retry after remediation.
  try:
   recorded=evidence_recorder.record(run_id=run_id,evidence=evidence)
  except ValueError as exc:
   if (str(exc)=="preview requires successful browser/e2e evidence"
       and evidence.status=="failure"
       and evidence.preview_url==deployed.preview_url
       and is_session_backend_503(evidence.detail)):
    raise PreviewExternalBackendUnavailable(deployed.preview_url) from exc
   raise
  if recorded.preview_url!=deployed.preview_url:raise ValueError("browser evidence URL does not match deployed preview")
  return VerifiedPreviewResult(deployment=deployed,browser_evidence=recorded)
