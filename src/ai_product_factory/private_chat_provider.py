"""Disabled-by-default SQL-InfoDive private Chat Completions provider.

This module is deliberately not registered as a Factory primary, Direct or Codex
provider. The IBM model's fitness for general product development is unproven.
No network request or secret access occurs until an explicit execute() call.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .model_executor import ModelRequest, ModelResult, ModelRole

PROVIDER_KEY = "infodive_ibm_cloud"
SECRET_ENV = "FACTORY_SQL_INFODIVE_API_KEY"
_MAX_RESPONSE_BYTES = 200_000
Transport = Callable[[str, str, dict[str, str], bytes, int], tuple[int, Any]]
_MODEL_PATTERN = re.compile(r"[A-Za-z0-9_.:-]{1,128}")
_HOST_PATTERN = re.compile(r"[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*")


class PrivateModelError(RuntimeError):
    """Sanitized error; provider responses and secrets must never be included."""


def _bounded_int(value: str, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise PrivateModelError("invalid private provider limit") from None
    if not 1 <= parsed <= maximum:
        raise PrivateModelError("invalid private provider limit")
    return parsed


@dataclass(frozen=True, repr=False)
class PrivateChatConfig:
    base_url: str
    model_id: str
    host_header: str | None = None
    allow_private_http: bool = False
    timeout_seconds: int = 180
    max_tokens: int = 4096

    def __repr__(self) -> str:
        return "PrivateChatConfig(<redacted>)"

    def __post_init__(self) -> None:
        try:
            uri = urllib.parse.urlsplit(self.base_url)
            hostname = uri.hostname
            port = uri.port
        except (TypeError, ValueError):
            raise PrivateModelError("invalid private model endpoint") from None
        if not isinstance(self.base_url, str) or not hostname or uri.scheme not in {"https", "http"}:
            raise PrivateModelError("invalid private model endpoint")
        if (port == 0 or uri.username or uri.password or uri.query or uri.fragment
                or uri.path not in {"", "/"}):
            raise PrivateModelError("invalid private model endpoint")
        # Both HTTPS and HTTP must target a literal RFC1918 IPv4 endpoint.
        # Public HTTPS is not a safe fallback for a private bearer credential.
        try:
            ip = ipaddress.ip_address(hostname)
        except ValueError:
            raise PrivateModelError("private model requires a literal IP") from None
        if (ip.version != 4 or not ip.is_private or ip.is_loopback
                or ip.is_link_local or ip.is_reserved or ip.is_unspecified
                or ip.is_multicast):
            raise PrivateModelError("private model requires a private IP")
        if uri.scheme == "http" and not self.allow_private_http:
            raise PrivateModelError("private HTTP requires explicit VPN approval")
        if uri.scheme == "https" and self.allow_private_http:
            raise PrivateModelError("HTTP exception requires HTTP")
        if not isinstance(self.model_id, str) or not _MODEL_PATTERN.fullmatch(self.model_id):
            raise PrivateModelError("invalid private model identifier")
        if self.host_header is not None:
            if (uri.scheme != "http" or not isinstance(self.host_header, str)
                    or not _HOST_PATTERN.fullmatch(self.host_header)
                    or ".." in self.host_header):
                raise PrivateModelError("invalid private HTTP Host")
        if not isinstance(self.timeout_seconds, int) or not 1 <= self.timeout_seconds <= 300:
            raise PrivateModelError("invalid private provider timeout")
        if not isinstance(self.max_tokens, int) or not 1 <= self.max_tokens <= 8192:
            raise PrivateModelError("invalid private provider output limit")
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))

    @classmethod
    def from_env(cls, source: Mapping[str, str] | None = None) -> "PrivateChatConfig":
        env = os.environ if source is None else source
        if env.get("FACTORY_SQL_INFODIVE_ENABLED") != "true":
            raise PrivateModelError("private model is disabled")
        if env.get("FACTORY_SQL_INFODIVE_PRIVATE_ROUTE_ATTESTED") != "true":
            raise PrivateModelError("private model network route is unverified")
        return cls(
            base_url=env.get("FACTORY_SQL_INFODIVE_BASE_URL", ""),
            model_id=env.get("FACTORY_SQL_INFODIVE_MODEL", ""),
            host_header=env.get("FACTORY_SQL_INFODIVE_HTTP_HOST") or None,
            allow_private_http=env.get("FACTORY_SQL_INFODIVE_ALLOW_PRIVATE_HTTP") == "true",
            timeout_seconds=_bounded_int(env.get("FACTORY_SQL_INFODIVE_TIMEOUT_SECONDS", "180"), 300),
            max_tokens=_bounded_int(env.get("FACTORY_SQL_INFODIVE_MAX_TOKENS", "4096"), 8192),
        )

    @property
    def endpoint(self) -> str:
        return self.base_url + "/api/chat/completions"


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _private_transport(method: str, url: str, headers: dict[str, str],
                       body: bytes, timeout: int) -> tuple[int, Any]:
    # No ambient proxy and no redirects: never forward the token across hosts.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _RefuseRedirects)
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
            if len(raw) > _MAX_RESPONSE_BYTES:
                raise PrivateModelError("private model response too large")
            return response.status, json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, {}
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeError, ValueError):
        raise PrivateModelError("private model transport unavailable") from None


class SqlInfodiveProvider:
    """Implements ModelProvider, but is never implicitly selected by the runtime."""

    def __init__(self, config: PrivateChatConfig, *,
                 credential: Callable[[], str],
                 transport: Transport | None = None) -> None:
        self.config = config
        self._credential = credential
        self._transport = transport or _private_transport

    def __repr__(self) -> str:
        return "SqlInfodiveProvider(<redacted>)"

    def verify_route(self) -> None:
        # The real transport always requires the existing VPS WireGuard route.
        # Injected offline test transports do not contact any network.
        if self._transport is _private_transport:
            from .private_model_vps_route import (
                PrivateVpsRouteError, verify_existing_vps_route,
            )
            try:
                verify_existing_vps_route(
                    self.config.base_url,
                    interface=os.getenv("FACTORY_SQL_INFODIVE_WG_INTERFACE", "wg-ibm"),
                )
            except PrivateVpsRouteError:
                raise PrivateModelError("private VPS route unavailable") from None

    def execute(self, request: ModelRequest) -> ModelResult:
        if not isinstance(request, ModelRequest):
            raise PrivateModelError("invalid private model request")
        # Check route BEFORE reading the bearer: never leak it to the
        # default interface, public internet or an untrusted worker host.
        self.verify_route()
        try:
            secret = self._credential()
        except Exception:
            raise PrivateModelError("private model credential unavailable") from None
        if (not isinstance(secret, str) or not secret or
                any(ord(c) < 33 or ord(c) > 126 for c in secret)):
            raise PrivateModelError("private model credential unavailable")
        headers = {
            "Content-Type": "application/json", "Accept": "application/json",
            "Authorization": "Bearer " + secret,
        }
        if self.config.host_header is not None:
            headers["Host"] = self.config.host_header
        prompt = {
            "objective": request.objective, "context": request.context,
            "constraints": list(request.constraints),
            "acceptance_criteria": list(request.acceptance_criteria),
            "files": list(request.files),
        }
        # General Factory models also need structured product and code output.
        # Use plain Chat Completions JSON instructions rather than assuming
        # the private API supports OpenAI response_format.
        if request.output_schema is not None:
            if not isinstance(request.output_schema, dict):
                raise PrivateModelError("invalid structured model output contract")
            try:
                encoded = json.dumps(request.output_schema, ensure_ascii=False)
            except (TypeError, ValueError):
                raise PrivateModelError("invalid structured model output contract") from None
            if len(encoded) > 32000:
                raise PrivateModelError("structured model output contract too large")
            prompt["output_schema"] = request.output_schema
            prompt["output_rule"] = "Return only JSON matching output_schema; no Markdown fences."
        body = json.dumps({
            "model": self.config.model_id,
            "messages": [{"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}],
            "temperature": 0, "max_tokens": self.config.max_tokens, "stream": False,
        }, ensure_ascii=False).encode("utf-8")
        try:
            status, payload = self._transport("POST", self.config.endpoint,
                                               headers, body, self.config.timeout_seconds)
        except Exception:
            raise PrivateModelError("private model transport failed") from None
        if status in {401, 403}:
            raise PrivateModelError("private model authentication denied")
        if status == 429:
            raise PrivateModelError("private model rate limited")
        if not isinstance(status, int) or not 200 <= status < 300:
            raise PrivateModelError("private model unavailable")
        try:
            choice = payload["choices"][0]
            text = choice["message"]["content"]
            finish_reason = choice.get("finish_reason")
            usage = payload["usage"]
            inp = usage["prompt_tokens"]
            out = usage["completion_tokens"]
            total = usage.get("total_tokens", inp + out)
            if (not isinstance(text, str) or not text.strip()
                    or any(isinstance(n, bool) or not isinstance(n, int) or n < 0
                           for n in (inp, out, total))
                    or total < inp + out):
                raise ValueError
        except (ValueError, TypeError, KeyError, IndexError):
            raise PrivateModelError("private model output or usage unverifiable") from None
        return ModelResult(
            role=ModelRole.PRIMARY, output=text,
            model=self.config.model_id, provider_ref=PROVIDER_KEY,
            usage={"input_tokens": float(inp),
                   "output_tokens": float(out), "total_tokens": float(total)},
            output_limit_reached=out >= self.config.max_tokens,
            output_truncated=finish_reason in ("length", "max_tokens"),
        )


def build_sql_infodive_provider(*, env: Mapping[str, str] | None = None,
                                transport: Transport | None = None) -> SqlInfodiveProvider:
    """Construct only after an explicit SQL-specific authorization.

    This is not a provider switch. No general Factory runtime calls it.
    An external caller also needs approved pricing and ledger integration.
    """
    source = os.environ if env is None else env
    config = PrivateChatConfig.from_env(source)
    if not source.get(SECRET_ENV):
        raise PrivateModelError("private model credential unavailable")
    return SqlInfodiveProvider(
        config, credential=lambda: source.get(SECRET_ENV, ""), transport=transport,
    )
