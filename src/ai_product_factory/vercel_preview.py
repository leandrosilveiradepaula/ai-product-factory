from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib import parse, request

from .deployment import DeploymentRequest, DeploymentResult
from .release_policy import ReleaseEnvironment


Transport = Callable[[str, str, dict[str, str], bytes | None], tuple[int, Any]]


def _default_transport(method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, Any]:
    req = request.Request(url, data=body, headers=headers, method=method)
    with request.urlopen(req, timeout=30) as response:
        raw = response.read().decode("utf-8")
        return response.status, json.loads(raw) if raw else None


@dataclass(frozen=True)
class VercelPreviewConfig:
    token: str
    team_id: str
    project_name: str
    github_org: str
    github_repo: str
    api_url: str = "https://api.vercel.com"
    poll_attempts: int = 20
    poll_interval_seconds: float = 3.0

    def validate(self) -> None:
        required = {
            "token": self.token,
            "team_id": self.team_id,
            "project_name": self.project_name,
            "github_org": self.github_org,
            "github_repo": self.github_repo,
        }
        missing = [name for name, value in required.items() if not str(value).strip()]
        if missing:
            raise ValueError("missing Vercel preview configuration: " + ", ".join(sorted(missing)))
        if self.poll_attempts < 1:
            raise ValueError("poll_attempts must be at least 1")
        if self.poll_interval_seconds < 0:
            raise ValueError("poll_interval_seconds cannot be negative")


class VercelPreviewAdapter:
    name = "vercel"

    def __init__(
        self,
        config: VercelPreviewConfig,
        *,
        transport: Transport | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        config.validate()
        self.config = config
        self.transport = transport or _default_transport
        self.sleeper = sleeper or time.sleep

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.token}",
            "Content-Type": "application/json",
        }

    def _call(self, method: str, path: str, *, payload: Any = None) -> Any:
        query = parse.urlencode({"teamId": self.config.team_id})
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        status, data = self.transport(
            method,
            f"{self.config.api_url.rstrip('/')}{path}?{query}",
            self._headers(),
            body,
        )
        if status < 200 or status >= 300:
            raise RuntimeError(f"Vercel request failed with HTTP {status}")
        return data or {}

    @staticmethod
    def _state(row: dict[str, Any]) -> str:
        return str(row.get("readyState") or row.get("state") or row.get("status") or "").upper()

    @staticmethod
    def _preview_url(row: dict[str, Any]) -> str | None:
        value = row.get("url")
        if not value:
            return None
        return value if str(value).startswith(("http://", "https://")) else f"https://{value}"

    def deploy(self, request_: DeploymentRequest) -> DeploymentResult:
        if request_.environment is not ReleaseEnvironment.PREVIEW:
            raise PermissionError("VercelPreviewAdapter refuses non-preview deployments")

        created = self._call(
            "POST",
            "/v13/deployments",
            payload={
                "name": self.config.project_name,
                "gitSource": {
                    "type": "github",
                    "org": self.config.github_org,
                    "repo": self.config.github_repo,
                    "ref": request_.candidate_commit,
                },
            },
        )
        deployment_id = created.get("id") or created.get("uid")
        if not deployment_id:
            raise RuntimeError("Vercel did not return a deployment id")

        row = created
        for attempt in range(self.config.poll_attempts):
            state = self._state(row)
            if state == "READY":
                return DeploymentResult(
                    provider=self.name,
                    environment=request_.environment,
                    status="success",
                    deployment_ref=str(deployment_id),
                    preview_url=self._preview_url(row),
                )
            if state in {"ERROR", "CANCELED", "CANCELLED"}:
                return DeploymentResult(
                    provider=self.name,
                    environment=request_.environment,
                    status="failure",
                    deployment_ref=str(deployment_id),
                    preview_url=self._preview_url(row),
                )
            if attempt + 1 < self.config.poll_attempts:
                self.sleeper(self.config.poll_interval_seconds)
                row = self._call("GET", f"/v13/deployments/{deployment_id}")

        raise TimeoutError("Vercel preview did not reach a terminal state within the configured polling window")
