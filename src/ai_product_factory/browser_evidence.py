from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol

@dataclass(frozen=True)
class BrowserEvidence:
 status:str
 preview_url:str
 checks:tuple[str,...]=()
 detail:str|None=None

class BrowserEvidenceAdapter(Protocol):
 name:str
 def verify(self,preview_url:str)->BrowserEvidence:...

def require_browser_evidence(evidence:BrowserEvidence)->BrowserEvidence:
 if evidence.status!="success":raise ValueError("preview requires successful browser/e2e evidence")
 if not evidence.preview_url.startswith(("https://","http://localhost","http://127.0.0.1")):raise ValueError("browser evidence preview URL is invalid")
 return evidence
