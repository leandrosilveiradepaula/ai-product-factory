from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from .deployment import DeploymentRequest, DeploymentResult
from .release_policy import ReleaseEnvironment


_VERCEL_HOST=re.compile(r"(?P<host>[A-Za-z0-9][A-Za-z0-9-]*\.vercel\.app)")


@dataclass(frozen=True)
class GitHubVercelPreviewConfig:
    repository: str
    token: str
    api_url: str = "https://api.github.com"
    poll_attempts: int = 20
    poll_interval_seconds: float = 3.0

    def validate(self) -> None:
        if "/" not in self.repository:
            raise ValueError("repository must be in owner/name form")
        if not self.token.strip():
            raise ValueError("GITHUB_TOKEN is required for Vercel Preview discovery")
        if self.poll_attempts < 1:
            raise ValueError("poll_attempts must be at least 1")
        if self.poll_interval_seconds < 0:
            raise ValueError("poll_interval_seconds cannot be negative")


class GitHubVercelPreviewAdapter:
    """Discover an existing Vercel GitHub Preview for the exact candidate SHA."""

    name="vercel-github"

    def __init__(self,config:GitHubVercelPreviewConfig,*,sleeper:Callable[[float],None]|None=None)->None:
        config.validate()
        self.config=config
        self.sleeper=sleeper or time.sleep

    def _checks(self,sha:str)->list[dict[str,Any]]:
        url=f"{self.config.api_url.rstrip('/')}/repos/{self.config.repository}/commits/{sha}/check-runs?per_page=100"
        req=urllib.request.Request(url,method="GET",headers={
            "Authorization":f"Bearer {self.config.token}",
            "Accept":"application/vnd.github+json",
            "X-GitHub-Api-Version":"2022-11-28",
        })
        try:
            with urllib.request.urlopen(req,timeout=30) as response:
                raw=response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"GitHub Vercel check discovery failed ({exc.code})") from exc
        payload=json.loads(raw) if raw else {}
        return list(payload.get("check_runs") or [])

    @staticmethod
    def _preview_url(check:dict[str,Any])->str|None:
        output=check.get("output") or {}
        haystack="\n".join(str(x or "") for x in (output.get("title"),output.get("summary"),output.get("text"),check.get("details_url")))
        match=_VERCEL_HOST.search(haystack)
        return f"https://{match.group('host')}" if match else None

    def deploy(self,request_:DeploymentRequest)->DeploymentResult:
        if request_.environment is not ReleaseEnvironment.PREVIEW:
            raise PermissionError("GitHubVercelPreviewAdapter refuses non-preview deployments")
        for attempt in range(self.config.poll_attempts):
            checks=[row for row in self._checks(request_.candidate_commit) if str((row.get("app") or {}).get("slug") or "").lower()=="vercel"]
            for row in checks:
                if str(row.get("status") or "").lower()!="completed":
                    continue
                preview_url=self._preview_url(row)
                conclusion=str(row.get("conclusion") or "").lower()
                if conclusion in {"success","neutral"} and preview_url:
                    return DeploymentResult(self.name,request_.environment,"success",str(row.get("id") or "vercel-check"),preview_url)
            completed=[row for row in checks if str(row.get("status") or "").lower()=="completed"]
            if completed and all(str(row.get("conclusion") or "").lower() in {"failure","cancelled","canceled","timed_out","action_required"} for row in completed):
                return DeploymentResult(self.name,request_.environment,"failure",str(completed[0].get("id") or "vercel-check"),None)
            if attempt+1<self.config.poll_attempts:
                self.sleeper(self.config.poll_interval_seconds)
        raise TimeoutError("Vercel GitHub Preview was not discoverable for the candidate commit")


def config_from_env(repository:str)->GitHubVercelPreviewConfig:
    return GitHubVercelPreviewConfig(repository=repository,token=os.getenv("GITHUB_TOKEN",""))
