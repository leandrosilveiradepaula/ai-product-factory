from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib import error, parse, request

from .model_executor import ModelProvider, ModelRequest, ModelResult, ModelRole
from .models import Complexity


Transport = Callable[[str, str, dict[str, str], bytes | None], tuple[int, Any]]
AccessTokenProvider = Callable[[], str]


def _default_transport(
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes | None,
) -> tuple[int, Any]:
    req = request.Request(url, data=body, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=120) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw)
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {"error": {"message": raw[:500]}}
        request_id = exc.headers.get("x-request-id") if exc.headers else None
        if request_id:
            data["_request_id"] = request_id
        return exc.code, data


class GitHubActionsOpenAIWorkloadIdentity:
    """Exchanges a GitHub Actions OIDC assertion for a short-lived OpenAI API token."""

    token_endpoint = "https://auth.openai.com/oauth/token"

    def __init__(
        self,
        *,
        identity_provider_id: str,
        service_account_id: str,
        audience: str,
        transport: Transport | None = None,
    ) -> None:
        self.identity_provider_id = identity_provider_id
        self.service_account_id = service_account_id
        self.audience = audience
        self.transport = transport or _default_transport
        self._access_token = ""
        self._expires_at = 0.0

    @classmethod
    def from_env(cls, *, transport: Transport | None = None) -> "GitHubActionsOpenAIWorkloadIdentity":
        required = {
            "OPENAI_IDENTITY_PROVIDER_ID": os.getenv("OPENAI_IDENTITY_PROVIDER_ID", "").strip(),
            "OPENAI_SERVICE_ACCOUNT_ID": os.getenv("OPENAI_SERVICE_ACCOUNT_ID", "").strip(),
            "OPENAI_WIF_AUDIENCE": os.getenv("OPENAI_WIF_AUDIENCE", "").strip(),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError("OpenAI API workload identity configuration is incomplete: " + ", ".join(missing))
        return cls(
            identity_provider_id=required["OPENAI_IDENTITY_PROVIDER_ID"],
            service_account_id=required["OPENAI_SERVICE_ACCOUNT_ID"],
            audience=required["OPENAI_WIF_AUDIENCE"],
            transport=transport,
        )

    def get_access_token(self) -> str:
        if self._access_token and time.time() < self._expires_at - 60:
            return self._access_token

        request_url = os.getenv("ACTIONS_ID_TOKEN_REQUEST_URL", "").strip()
        request_token = os.getenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "").strip()
        if not request_url or not request_token:
            raise RuntimeError(
                "GitHub Actions OIDC environment is unavailable; id-token: write is required for OpenAI API WIF"
            )

        parts = parse.urlsplit(request_url)
        query = dict(parse.parse_qsl(parts.query, keep_blank_values=True))
        query["audience"] = self.audience
        oidc_url = parse.urlunsplit(
            (parts.scheme, parts.netloc, parts.path, parse.urlencode(query), parts.fragment)
        )
        status, oidc = self.transport(
            "GET",
            oidc_url,
            {"Authorization": f"bearer {request_token}"},
            None,
        )
        if status < 200 or status >= 300 or not isinstance(oidc, dict) or not oidc.get("value"):
            raise RuntimeError(f"GitHub OIDC token request failed: HTTP {status}")

        payload = {
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
            "subject_token": oidc["value"],
            "identity_provider_id": self.identity_provider_id,
            "service_account_id": self.service_account_id,
        }
        status, exchanged = self.transport(
            "POST",
            self.token_endpoint,
            {"Content-Type": "application/json"},
            json.dumps(payload).encode("utf-8"),
        )
        if status < 200 or status >= 300 or not isinstance(exchanged, dict):
            details = [f"HTTP {status}"]
            if isinstance(exchanged, dict):
                error_data = exchanged.get("error")
                if isinstance(error_data, dict):
                    for key in ("type", "code", "message"):
                        value = error_data.get(key)
                        if isinstance(value, str) and value:
                            details.append(f"{key}={value}")
                elif isinstance(error_data, str) and error_data:
                    details.append(f"error={error_data}")
                request_id = exchanged.get("_request_id")
                if isinstance(request_id, str) and request_id:
                    details.append(f"request_id={request_id}")
            raise RuntimeError("OpenAI workload identity token exchange failed: " + "; ".join(details))

        access_token = exchanged.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise RuntimeError("OpenAI workload identity token exchange returned no access token")

        expires_at = exchanged.get("expires_at")
        if isinstance(expires_at, (int, float)):
            self._expires_at = float(expires_at)
        else:
            self._expires_at = time.time() + float(exchanged.get("expires_in") or 300)
        self._access_token = access_token
        return access_token


@dataclass(frozen=True)
class OpenAIModelPolicy:
    low: str = "gpt-5.6-luna"
    medium: str = "gpt-5.6-terra"
    high: str = "gpt-5.6-terra"
    very_high: str = "gpt-5.6-sol"
    default_reasoning_effort: str = "medium"
    max_output_tokens: int = 12000

    def model_for(self, complexity: Complexity) -> str:
        return {
            Complexity.LOW: self.low,
            Complexity.MEDIUM: self.medium,
            Complexity.HIGH: self.high,
            Complexity.VERY_HIGH: self.very_high,
        }[complexity]


class OpenAIResponsesProvider(ModelProvider):
    """OpenAI Responses API provider supporting API key or GitHub Actions WIF."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        access_token_provider: AccessTokenProvider | None = None,
        policy: OpenAIModelPolicy | None = None,
        transport: Transport | None = None,
        api_url: str = "https://api.openai.com/v1/responses",
    ) -> None:
        self.transport = transport or _default_transport
        key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")
        wif_values = {
            "OPENAI_IDENTITY_PROVIDER_ID": os.getenv("OPENAI_IDENTITY_PROVIDER_ID", "").strip(),
            "OPENAI_SERVICE_ACCOUNT_ID": os.getenv("OPENAI_SERVICE_ACCOUNT_ID", "").strip(),
            "OPENAI_WIF_AUDIENCE": os.getenv("OPENAI_WIF_AUDIENCE", "").strip(),
        }
        if access_token_provider is not None:
            self._access_token_provider = access_token_provider
        elif any(wif_values.values()):
            missing = [name for name, value in wif_values.items() if not value]
            if missing:
                raise ValueError("OpenAI API workload identity configuration is incomplete: " + ", ".join(missing))
            wif = GitHubActionsOpenAIWorkloadIdentity.from_env(transport=self.transport)
            self._access_token_provider = wif.get_access_token
        elif key:
            self._access_token_provider = lambda: key
        else:
            raise ValueError("OPENAI_API_KEY or OpenAI API workload identity configuration is required")
        self.policy = policy or OpenAIModelPolicy()
        self.api_url = api_url

    def execute_for_complexity(
        self,
        request_data: ModelRequest,
        complexity: Complexity,
        *,
        reasoning_effort: str | None = None,
    ) -> ModelResult:
        model = self.policy.model_for(complexity)
        effort = reasoning_effort or self.policy.default_reasoning_effort
        prompt = self._render_prompt(request_data)

        payload = {
            "model": model,
            "input": prompt,
            "reasoning": {"effort": effort},
            "max_output_tokens": self.policy.max_output_tokens,
            "store": False,
        }
        status, data = self.transport(
            "POST",
            self.api_url,
            {
                "Authorization": f"Bearer {self._access_token_provider()}",
                "Content-Type": "application/json",
            },
            json.dumps(payload).encode("utf-8"),
        )
        if status < 200 or status >= 300:
            error_data = data.get("error") if isinstance(data, dict) else None
            if not isinstance(error_data, dict):
                error_data = {}
            error_type = error_data.get("type")
            error_code = error_data.get("code")
            message = error_data.get("message")
            request_id = data.get("_request_id") if isinstance(data, dict) else None
            details = [
                f"HTTP {status}",
                f"type={error_type}" if error_type else None,
                f"code={error_code}" if error_code else None,
                f"message={message}" if message else None,
                f"request_id={request_id}" if request_id else None,
            ]
            raise RuntimeError("OpenAI request failed: " + "; ".join(x for x in details if x))

        output_text = self._extract_output_text(data)
        usage_raw = data.get("usage") or {}
        usage = {
            key: float(value)
            for key, value in usage_raw.items()
            if isinstance(value, (int, float))
        }
        details = usage_raw.get("input_tokens_details") if isinstance(usage_raw, dict) else None
        if isinstance(details, dict):
            cached = details.get("cached_tokens")
            if isinstance(cached, (int, float)):
                usage["cached_input_tokens"] = float(cached)
        return ModelResult(
            role=ModelRole.PRIMARY,
            output=output_text,
            provider_ref=data.get("id"),
            usage=usage,
            model=model,
        )

    def execute(self, request_data: ModelRequest) -> ModelResult:
        return self.execute_for_complexity(request_data, Complexity.MEDIUM)

    @staticmethod
    def _render_prompt(request_data: ModelRequest) -> str:
        lines = [
            "OBJECTIVE:",
            request_data.objective,
            "",
            "CONTEXT:",
            request_data.context,
        ]
        if request_data.files:
            lines.extend(["", "RELEVANT FILES:", *[f"- {x}" for x in request_data.files]])
        if request_data.constraints:
            lines.extend(["", "CONSTRAINTS:", *[f"- {x}" for x in request_data.constraints]])
        if request_data.acceptance_criteria:
            lines.extend(["", "ACCEPTANCE CRITERIA:", *[f"- {x}" for x in request_data.acceptance_criteria]])
        return "\n".join(lines)

    @staticmethod
    def _extract_output_text(data: dict[str, Any]) -> str:
        direct = data.get("output_text")
        if isinstance(direct, str) and direct:
            return direct

        parts: list[str] = []
        for item in data.get("output") or []:
            for content in item.get("content") or []:
                text = content.get("text")
                if content.get("type") in {"output_text", "text"} and isinstance(text, str):
                    parts.append(text)
        if not parts:
            raise RuntimeError("OpenAI response did not contain output text")
        return "\n".join(parts)
