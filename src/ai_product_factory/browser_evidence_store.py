from __future__ import annotations
from .browser_evidence import BrowserEvidence,require_browser_evidence

class BrowserEvidenceRecorder:
 def __init__(self,store)->None:self.store=store
 def record(self,*,run_id:str,evidence:BrowserEvidence)->BrowserEvidence:
  payload={"preview_url":evidence.preview_url,"checks":list(evidence.checks),"detail":evidence.detail}
  self.store.record_evaluation(run_id=run_id,eval_type="browser_e2e",status=evidence.status,baseline_ref=evidence.preview_url,result=payload)
  self.store.record_audit_event(run_id=run_id,event_type="preview.browser_evidence_recorded",payload={"status":evidence.status,**payload},actor_ref="browser-evidence")
  return require_browser_evidence(evidence)
