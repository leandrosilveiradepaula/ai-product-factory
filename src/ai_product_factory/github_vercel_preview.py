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
        self.checks_forbidden=False

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
            self.checks_forbidden=True
            return []
        self.checks_forbidden=False
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

    def _vercel_comments(self)->list[dict[str,Any]]:
        if self.config.pull_request_number is None:
            return []
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
            raise RuntimeError(f"GitHub Vercel comment discovery failed ({exc.code})") from exc
        rows=json.loads(raw) if raw else []
        return [row for row in rows if "vercel" in str((row.get("user") or {}).get("login") or "").lower()]

    @staticmethod
    def _quota_signal(*values:Any)->bool:
        text="\n".join(str(value or "") for value in values).lower()
        return any(marker in text for marker in (
            "api-deployments-free-per-day",
            "build-rate-limit",
            "deployment rate limited",
            "deployment rate limit",
        ))

    def _quota_blocked(self,comments:list[dict[str,Any]]|None=None)->bool:
        for row in comments if comments is not None else self._vercel_comments():
            if self._quota_signal(row.get("body")):
                return True
        return False

    def _comment_preview_url(self,comments:list[dict[str,Any]])->str|None:
        for row in reversed(comments):
            body=str(row.get("body") or "")
            if "ready" not in body.lower():
                continue
            match=_VERCEL_HOST.search(body)
            if match:
                return f"https://{match.group('host')}"
        return None

    def deploy(self,request_:DeploymentRequest)->DeploymentResult:
        if request_.environment is not ReleaseEnvironment.PREVIEW:
            raise PermissionError("GitHubVercelPreviewAdapter refuses non-preview deployments")
        vercel_status_succeeded_without_url=False
        for attempt in range(self.config.poll_attempts):
            comments=self._vercel_comments()
            if self._quota_blocked(comments):
                return DeploymentResult(self.name,request_.environment,"blocked_quota","vercel-daily-deployment-quota",None)
            checks=[row for row in self._checks(request_.candidate_commit) if str((row.get("app") or {}).get("slug") or "").lower()=="vercel"]
            for row in checks:
                if str(row.get("status") or "").lower()!="completed":
                    continue
                output=row.get("output") or {}
                if self._quota_signal(
                    row.get("details_url"),row.get("target_url"),
                    output.get("title"),output.get("summary"),output.get("text"),
                ):
                    return DeploymentResult(self.name,request_.environment,"blocked_quota",str(row.get("id") or "vercel-check"),None)
                preview_url=self._preview_url(row)
                conclusion=str(row.get("conclusion") or "").lower()
                if conclusion in {"success","neutral"} and preview_url:
                    return DeploymentResult(self.name,request_.environment,"success",str(row.get("id") or "vercel-check"),preview_url)
            completed=[row for row in checks if str(row.get("status") or "").lower()=="completed"]
            if completed and all(str(row.get("conclusion") or "").lower() in {"failure","cancelled","canceled","timed_out","action_required"} for row in completed):
                return DeploymentResult(self.name,request_.environment,"failure",str(completed[0].get("id") or "vercel-check"),None)

            statuses=[row for row in self._statuses(request_.candidate_commit) if "vercel" in str(row.get("context") or "").lower()]
            preview_url=self._comment_preview_url(comments)
            for row in statuses:
                if self._quota_signal(row.get("description"),row.get("target_url")):
                    return DeploymentResult(self.name,request_.environment,"blocked_quota",f"vercel-status-{row.get('id') or 'unknown'}",None)
                state=str(row.get("state") or "").lower()
                if state=="success" and preview_url:
                    return DeploymentResult(self.name,request_.environment,"success",f"vercel-status-{row.get('id') or 'unknown'}",preview_url)
                if state=="success" and not preview_url:
                    vercel_status_succeeded_without_url=True
            terminal=[row for row in statuses if str(row.get("state") or "").lower() in {"failure","error"}]
            if terminal:
                return DeploymentResult(self.name,request_.environment,"failure",f"vercel-status-{terminal[0].get('id') or 'unknown'}",None)
            if attempt+1<self.config.poll_attempts:
                self.sleeper(self.config.poll_interval_seconds)
        if vercel_status_succeeded_without_url:
            raise RuntimeError(
                "Vercel commit status succeeded, but no Ready preview URL was discoverable. "
                "Grant GitHub Checks read for this repository or ensure the Vercel bot publishes a Ready preview URL."
            )
        raise TimeoutError("Vercel GitHub Preview was not discoverable for the candidate commit")


def config_from_env(repository:str,*,pull_request_number:int|None=None)->GitHubVercelPreviewConfig:
    return GitHubVercelPreviewConfig(repository=repository,token=resolve_github_token(repository),pull_request_number=pull_request_number)
