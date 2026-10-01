from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from .deployment import DeploymentRequest, DeploymentResult
from .release_policy import ReleaseEnvironment
from .github_auth import resolve_github_token


_VERCEL_HOST=re.compile(r"(?P<host>[A-Za-z0-9][A-Za-z0-9-]*\.vercel\.app)")


@dataclass(frozen=True)
class GitHubVercelPreviewConfig:
    repository: str
    token: str
    api_url: str = "https://api.github.com"
    poll_attempts: int = 20
    poll_interval_seconds: float = 3.0
    pull_request_number: int | None = None

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

    def _get_json(self,url:str)->Any:
        req=urllib.request.Request(url,method="GET",headers={
            "Authorization":f"Bearer {self.config.token}",
            "Accept":"application/vnd.github+json",
            "X-GitHub-Api-Version":"2022-11-28",
        })
        with urllib.request.urlopen(req,timeout=30) as response:
            raw=response.read().decode("utf-8")
        return json.loads(raw) if raw else {}

    def _checks(self,sha:str)->list[dict[str,Any]]:
        url=f"{self.config.api_url.rstrip('/')}/repos/{self.config.repository}/commits/{sha}/check-runs?per_page=100"
        try:
            payload=self._get_json(url)
        except urllib.error.HTTPError as exc:
            if exc.code!=403:
                raise RuntimeError(f"GitHub Vercel check discovery failed ({exc.code})") from exc
            return []
        return list(payload.get("check_runs") or [])

    def _statuses(self,sha:str)->list[dict[str,Any]]:
        url=f"{self.config.api_url.rstrip('/')}/repos/{self.config.repository}/commits/{sha}/status"
        try:
            payload=self._get_json(url)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"GitHub Vercel status discovery failed ({exc.code})") from exc
        return list(payload.get("statuses") or [])

    @staticmethod
    def _preview_url(check:dict[str,Any])->str|None:
        output=check.get("output") or {}
        haystack="\n".join(str(x or "") for x in (output.get("title"),output.get("summary"),output.get("text"),check.get("details_url"),check.get("target_url")))
        match=_VERCEL_HOST.search(haystack)
        return f"https://{match.group('host')}" if match else None

    def _quota_blocked(self)->bool:
        if self.config.pull_request_number is None:
            return False
        url=f"{self.config.api_url.rstrip('/')}/repos/{self.config.repository}/issues/{self.config.pull_request_number}/comments?per_page=100"
        req=urllib.request.Request(url,method="GET",headers={
            "Authorization":f"Bearer {self.config.token}",
            "Accept":"application/vnd.github+json",
            "X-GitHub-Api-Version":"2022-11-28",
        })
        try:
            with urllib.request.urlopen(req,timeout=30) as response:
                raw=response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"GitHub Vercel quota discovery failed ({exc.code})") from exc
        for row in json.loads(raw) if raw else []:
            login=str((row.get("user") or {}).get("login") or "").lower()
            body=str(row.get("body") or "").lower()
            if "vercel" in login and "api-deployments-free-per-day" in body:
                return True
        return False

    def deploy(self,request_:DeploymentRequest)->DeploymentResult:
        if request_.environment is not ReleaseEnvironment.PREVIEW:
            raise PermissionError("GitHubVercelPreviewAdapter refuses non-preview deployments")
        for attempt in range(self.config.poll_attempts):
            if self._quota_blocked():
                return DeploymentResult(self.name,request_.environment,"blocked_quota","vercel-daily-deployment-quota",None)
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

            if not checks:
                statuses=[row for row in self._statuses(request_.candidate_commit) if "vercel" in str(row.get("context") or "").lower()]
                for row in statuses:
                    state=str(row.get("state") or "").lower()
                    preview_url=self._preview_url(row)
                    if state=="success" and preview_url:
                        return DeploymentResult(self.name,request_.environment,"success",f"vercel-status-{row.get('id') or 'unknown'}",preview_url)
                terminal=[row for row in statuses if str(row.get("state") or "").lower() in {"failure","error"}]
                if terminal:
                    return DeploymentResult(self.name,request_.environment,"failure",f"vercel-status-{terminal[0].get('id') or 'unknown'}",None)
            if attempt+1<self.config.poll_attempts:
                self.sleeper(self.config.poll_interval_seconds)
        raise TimeoutError("Vercel GitHub Preview was not discoverable for the candidate commit")


def config_from_env(repository:str,*,pull_request_number:int|None=None)->GitHubVercelPreviewConfig:
    return GitHubVercelPreviewConfig(repository=repository,token=resolve_github_token(repository),pull_request_number=pull_request_number)
