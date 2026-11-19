"""Read-only verification on the existing VPS wg-ibm interface.

No WireGuard key handling or new tunnel. No n8n, LangGraph, HTTP requests,
SQL, API tokens or model calls. Run on the actual VPS host (not GitHub Actions).
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

# Running this CLI from the repository root also resolves src/ without a pip
# install; it does not depend on the Agente Financeiro Python environment.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ai_product_factory.private_chat_provider import PrivateChatConfig, PrivateModelError
from ai_product_factory.private_model_vps_route import (
    PrivateVpsRouteError, verify_existing_vps_route,
)


def check_vps(env, *, route_reader=None, tcp_dialer=None):
    """Probe the ACTUAL VPS network stack, no token or model required."""
    cfg = PrivateChatConfig(
        base_url=env.get("FACTORY_SQL_INFODIVE_BASE_URL", ""),
        model_id=env.get("FACTORY_SQL_INFODIVE_MODEL", ""),
        host_header=env.get("FACTORY_SQL_INFODIVE_HTTP_HOST") or None,
        allow_private_http=env.get("FACTORY_SQL_INFODIVE_ALLOW_PRIVATE_HTTP") == "true",
    )
    return verify_existing_vps_route(
        cfg.base_url,
        interface=env.get("FACTORY_SQL_INFODIVE_WG_INTERFACE", "wg-ibm"),
        tcp=True,
        route_reader=route_reader, tcp_dialer=tcp_dialer,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="VPS direct IBM private network preflight")
    parser.add_argument("--check-only", action="store_true", required=True)
    args = parser.parse_args(argv)
    try:
        result = check_vps(os.environ)
    except (PrivateModelError, PrivateVpsRouteError, OSError):
        print("FACTORY_SQL_INFODIVE_VPS_NETWORK=BLOCKED")
        return 2
    # Sanitized metadata only. No private address, peer ID, raw HTTP or token.
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
