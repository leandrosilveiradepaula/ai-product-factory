#!/usr/bin/env python3
"""Schedule-only GitHub Actions wake from a Linux VPS.

This process does not claim tasks, access Supabase, start a product, or call
a model. It dispatches the already defined workflow on the protected main
branch; all job admission remains inside GitHub Actions and the Control Plane.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Callable

REPOSITORY = "leandrosilveiradepaula/ai-product-factory"
WORKFLOW = "autonomous-runner.yml"
URL = f"https://api.github.com/repos/{REPOSITORY}/actions/workflows/{WORKFLOW}/dispatches"
PAYLOAD = {"ref": "main", "inputs": {"vps_wake": "true"}}


def dispatch(*, token: str, opener: Callable = urllib.request.urlopen) -> str:
    if not isinstance(token, str) or not token.strip() or "\n" in token or "\r" in token:
        return "missing_token"
    request = urllib.request.Request(
        URL,
        data=json.dumps(PAYLOAD, separators=(",", ":")).encode("utf-8"),
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token.strip(),
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ai-product-factory-vps-wake/1.0",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with opener(request, timeout=12) as response:
            if response.status == 204:
                return "accepted"
            return "unexpected_response"
    except urllib.error.HTTPError as error:
        # Never log headers, response bodies, or secrets.
        if error.code in (401, 403):
            return "permission_denied"
        if error.code == 404:
            return "workflow_not_found"
        if error.code == 422:
            return "workflow_input_rejected"
        if error.code == 429 or 500 <= error.code <= 599:
            return "transient_error"
        return "request_rejected"
    except (urllib.error.URLError, TimeoutError, OSError):
        return "transport_error"


def main() -> int:
    result = dispatch(token=os.environ.get("FACTORY_VPS_GITHUB_TOKEN", ""))
    print(json.dumps({
        "component": "factory-vps-wake",
        "result": result,
        "workflow": WORKFLOW,
        "calls_to_paid_model": 0,
        "release_authorized": False,
    }, sort_keys=True))
    return 0 if result == "accepted" else 1


if __name__ == "__main__":
    sys.exit(main())
