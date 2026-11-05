"""Read-only Console API auth/CSRF inventory with explicit public exceptions.

Static contract check, not an authenticated browser or penetration test.
Unexpected API endpoints fail closed until explicitly reviewed. Never
imports or executes server routes, accesses tokens or changes production.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

PUBLIC = {
    "health/route.ts": "health_no_sensitive_data",
    "integrations/github-app/webhook/route.ts": "hmac_and_feature_gate",
    "integrations/github-app/callback/route.ts": "oauth_callback",
    "integrations/supabase/callback/route.ts": "oauth_callback",
}
MUTATION = re.compile(r"export\s+(?:async\s+)?function\s+(POST|PUT|PATCH|DELETE)\s*\(")
HANDLER = re.compile(r"export\s+(?:async\s+)?function\s+(GET|POST|PUT|PATCH|DELETE)\s*\(")
OPERATOR = re.compile(r"\brequireConsole(?:Operator|Admin)\s*\(")


def audit(root: Path) -> dict:
    root = root.resolve(strict=True)
    api = root / "apps" / "console" / "app" / "api"
    if not api.is_dir() or api.is_symlink():
        raise ValueError("Console API tree missing")
    entries = []
    for path in sorted(api.rglob("route.ts")):
        if path.is_symlink():
            raise ValueError("symlinked route")
        rel = path.relative_to(api).as_posix()
        body = path.read_text(encoding="utf-8")
        handlers = sorted(set(HANDLER.findall(body)))
        category = PUBLIC.get(rel, "operator_required")
        has_guard = bool(OPERATOR.search(body))
        mutation = bool(MUTATION.search(body))
        has_origin = "request.headers.get(\"origin\")" in body or "request.headers.get('origin')" in body
        has_content_type = "content-type" in body
        flags = []
        if not handlers:
            flags.append("no_exported_http_handler")
        if category == "operator_required" and not has_guard:
            flags.append("operator_guard_not_found")
        if category == "operator_required" and mutation and not has_origin:
            flags.append("mutation_origin_guard_not_found")
        if category == "operator_required" and mutation and not has_content_type:
            flags.append("mutation_content_type_guard_not_found")
        if category == "hmac_and_feature_gate" and (
            "authenticateGitHubWebhook" not in body or
            "FACTORY_GITHUB_WEBHOOK_ENABLED" not in body
        ):
            flags.append("webhook_signature_or_feature_gate_not_found")
        entries.append({"route": rel, "category": category,
                        "methods": handlers, "flags": flags})
    unknown_exceptions = sorted(set(PUBLIC) - {e["route"] for e in entries})
    blockers = [{"route": x["route"], "flags": x["flags"]} for x in entries if x["flags"]]
    return {"scope": "static_console_route_inventory_not_authentication_certification",
            "routes": entries, "count": len(entries),
            "stale_public_exceptions": unknown_exceptions,
            "blockers": blockers, "authenticated_negative_tests_executed": False,
            "security_certified": False, "writes": 0, "paid_calls": 0}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    result = audit(args.root)
    print(json.dumps(result, sort_keys=True))
    # Audit is advisory until source gaps are classified; do not hide findings.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
