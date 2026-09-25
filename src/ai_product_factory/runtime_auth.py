from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum


class AuthKind(StrEnum):
    OPENAI_API_KEY = "openai_api_key"
    CHATGPT_ACCESS_TOKEN = "chatgpt_access_token"
    WORKLOAD_IDENTITY = "workload_identity"
    NONE = "none"


@dataclass(frozen=True)
class RuntimeAuth:
    kind: AuthKind
    source: str
    configured: bool


class RuntimeAuthResolver:
    """Resolve auth capability without reading or persisting secret values."""

    def __init__(self, environ: dict[str, str] | None = None) -> None:
        self.environ = environ if environ is not None else os.environ

    def resolve(self) -> RuntimeAuth:
        if self.environ.get("OPENAI_WORKLOAD_IDENTITY_FILE"):
            return RuntimeAuth(AuthKind.WORKLOAD_IDENTITY, "OPENAI_WORKLOAD_IDENTITY_FILE", True)
        if self.environ.get("CHATGPT_ACCESS_TOKEN"):
            return RuntimeAuth(AuthKind.CHATGPT_ACCESS_TOKEN, "CHATGPT_ACCESS_TOKEN", True)
        if self.environ.get("OPENAI_API_KEY"):
            return RuntimeAuth(AuthKind.OPENAI_API_KEY, "OPENAI_API_KEY", True)
        return RuntimeAuth(AuthKind.NONE, "none", False)

    def available_kinds(self) -> tuple[AuthKind, ...]:
        kinds: list[AuthKind] = []
        if self.environ.get("OPENAI_WORKLOAD_IDENTITY_FILE"):
            kinds.append(AuthKind.WORKLOAD_IDENTITY)
        if self.environ.get("CHATGPT_ACCESS_TOKEN"):
            kinds.append(AuthKind.CHATGPT_ACCESS_TOKEN)
        if self.environ.get("OPENAI_API_KEY"):
            kinds.append(AuthKind.OPENAI_API_KEY)
        return tuple(kinds)
