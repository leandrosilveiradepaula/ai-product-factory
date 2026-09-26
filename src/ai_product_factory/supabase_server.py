from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SupabaseServerConfig:
    url: str
    key: str
    headers: dict[str, str]


def resolve_supabase_server_config(
    *,
    url: str | None = None,
    secret_key: str | None = None,
    service_role_key: str | None = None,
) -> SupabaseServerConfig:
    resolved_url = (url or os.getenv("SUPABASE_URL", "")).rstrip("/")
    key = (
        secret_key
        or os.getenv("SUPABASE_SECRET_KEY", "")
        or service_role_key
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    )
    if not resolved_url or not key:
        raise RuntimeError("Supabase runtime credentials are not configured")
    headers = {"apikey": key}
    if not key.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {key}"
    return SupabaseServerConfig(url=resolved_url, key=key, headers=headers)
