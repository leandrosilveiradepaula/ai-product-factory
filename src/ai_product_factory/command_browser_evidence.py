from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Callable

from .browser_evidence import BrowserEvidence

Runner=Callable[[tuple[str,...],dict[str,str],float],tuple[int,str,str]]

_BROWSER_ENV_ALLOWLIST=(
    "PATH",
    "HOME",
    "TMPDIR",
    "TMP",
    "TEMP",
    "LANG",
    "LC_ALL",
    "TZ",
    "CI",
    "PLAYWRIGHT_BROWSERS_PATH",
    "FACTORY_PREVIEW_EXPECTED_TEXT",
    "FACTORY_VERCEL_TRUSTED_OIDC_TOKEN",
)

def _browser_env(preview_url:str)->dict[str,str]:
    env={key:value for key in _BROWSER_ENV_ALLOWLIST if (value:=os.getenv(key)) is not None}
    env["FACTORY_PREVIEW_URL"]=preview_url
    return env

def _default_runner(argv:tuple[str,...],env:dict[str,str],timeout:float)->tuple[int,str,str]:
    completed=subprocess.run(list(argv),env=env,capture_output=True,text=True,timeout=timeout,check=False)
    return completed.returncode,completed.stdout,completed.stderr

@dataclass(frozen=True)
class CommandBrowserEvidenceConfig:
    argv:tuple[str,...]
    timeout_seconds:float=120.0

    def validate(self)->None:
        if not self.argv or any(not str(x).strip() for x in self.argv):
            raise ValueError("browser evidence command argv must contain non-empty strings")
        if self.timeout_seconds<=0:
            raise ValueError("browser evidence command timeout must be positive")

    @classmethod
    def from_env(cls)->"CommandBrowserEvidenceConfig":
        raw=os.getenv("FACTORY_BROWSER_EVIDENCE_COMMAND_JSON","")
        if not raw:
            raise ValueError("FACTORY_BROWSER_EVIDENCE_COMMAND_JSON is not configured")
        try:
            parsed=json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("FACTORY_BROWSER_EVIDENCE_COMMAND_JSON must be valid JSON") from exc
        if not isinstance(parsed,list) or not all(isinstance(x,str) for x in parsed):
            raise ValueError("FACTORY_BROWSER_EVIDENCE_COMMAND_JSON must be a JSON array of strings")
        timeout=float(os.getenv("FACTORY_BROWSER_EVIDENCE_TIMEOUT_SECONDS","120"))
        config=cls(tuple(parsed),timeout)
        config.validate()
        return config

class CommandBrowserEvidenceAdapter:
    name="command-browser-evidence"

    def __init__(self,config:CommandBrowserEvidenceConfig,*,runner:Runner|None=None)->None:
        config.validate()
        self.config=config
        self.runner=runner or _default_runner

    def verify(self,preview_url:str)->BrowserEvidence:
        if not preview_url.startswith(("https://","http://localhost","http://127.0.0.1")):
            return BrowserEvidence("failure",preview_url,(),"invalid preview URL")
        env=_browser_env(preview_url)
        try:
            code,stdout,stderr=self.runner(self.config.argv,env,self.config.timeout_seconds)
        except subprocess.TimeoutExpired:
            return BrowserEvidence("failure",preview_url,(),"browser/e2e command timed out")
        except OSError as exc:
            return BrowserEvidence("failure",preview_url,(),f"browser/e2e command could not start: {exc}")
        if code!=0:
            detail=(stderr or stdout or f"command exited {code}").strip()[:2000]
            return BrowserEvidence("failure",preview_url,(),detail)
        try:
            payload=json.loads(stdout)
        except json.JSONDecodeError:
            return BrowserEvidence("failure",preview_url,(),"browser/e2e command did not return valid JSON")
        if not isinstance(payload,dict):
            return BrowserEvidence("failure",preview_url,(),"browser/e2e result must be a JSON object")
        status=str(payload.get("status") or "failure")
        checks_raw=payload.get("checks") or []
        checks=tuple(str(x) for x in checks_raw) if isinstance(checks_raw,list) else ()
        detail=payload.get("detail")
        return BrowserEvidence(status,preview_url,checks,None if detail is None else str(detail)[:2000])
