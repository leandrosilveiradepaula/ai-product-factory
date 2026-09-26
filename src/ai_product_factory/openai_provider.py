from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable
from urllib import error, request

from .model_executor import ModelProvider, ModelRequest, ModelResult, ModelRole
from .models import Complexity


Transport = Callable[[str, str, dict[str, str], bytes], tuple[int, Any]]


def _default_transport(method: str, url: str, headers: dict[str, str], body: bytes) -> tuple[int, Any]:
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
    """OpenAI Responses API provider for the factory's primary model path."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        policy: OpenAIModelPolicy | None = None,
        transport: Transport | None = None,
        api_url: str = "https://api.openai.com/v1/responses",
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required")
        self.policy = policy or OpenAIModelPolicy()
        self.transport = transport or _default_transport
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
                "Authorization": f"Bearer {self.api_key}",
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
        return ModelResult(
            role=ModelRole.PRIMARY,
            output=output_text,
            provider_ref=data.get("id"),
            usage=usage,
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
