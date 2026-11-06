"""Fail-closed static reachability audit for Console privileged credentials.

This is deliberately a source control, not an authentication or runtime
certification. It rejects a privileged environment name in a browser bundle
or the known unauthenticated endpoint, including through local or ``@/``
imports. The receipt never contains a credential value.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import deque
from pathlib import Path

PRIVILEGED_ENV = frozenset({"SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY", "FACTORY_RELEASE_GITHUB_TOKEN", "FACTORY_SUPABASE_MANAGEMENT_TOKEN", "FACTORY_GITHUB_WORKFLOW_DISPATCH_TOKEN", "OPENAI_API_KEY"})
ENV_REFERENCE = re.compile(r"\bprocess\.env(?:\.([A-Z0-9_]+)|\[['\"]([A-Z0-9_]+)['\"]\])")
IMPORT = re.compile(r"(?:import|export)\s+(?:[^'\"]*?\s+from\s+)?['\"]([^'\"]+)['\"]|import\(['\"]([^'\"]+)['\"]\)")
CLIENT_DIRECTIVE = re.compile(r"^\s*['\"]use client['\"]\s*;?", re.MULTILINE)
SERVER_DIRECTIVE = re.compile(r"^\s*['\"]use server['\"]\s*;?", re.MULTILINE)
PUBLIC_HEALTH = "apps/console/app/api/health/route.ts"
SOURCE_SUFFIXES = (".ts", ".tsx")
OPERATOR_GUARD = re.compile(r"\bawait\s+requireConsole(?:Admin|Operator)\s*\(")
WEBHOOK_GUARD = re.compile(r"\bauthenticateGitHubWebhook\s*\(")
HTTP_HANDLER = re.compile(r"\bexport\s+(?:async\s+)?(?:function\s+)?(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b")

def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()

def _resolve_import(console: Path, source: Path, target: str) -> Path | None:
    candidate = console / target[2:] if target.startswith("@/") else source.parent / target if target.startswith(".") else None
    if candidate is None:
        return None
    choices = [candidate, *(candidate.with_suffix(suffix) for suffix in SOURCE_SUFFIXES), *(candidate / f"index{suffix}" for suffix in SOURCE_SUFFIXES)]
    for resolved in choices:
        if resolved.is_file() and resolved.resolve().is_relative_to(console.resolve()):
            return resolved.resolve()
    return None

def _source_files(console: Path) -> list[Path]:
    files = sorted((path.resolve() for suffix in SOURCE_SUFFIXES for path in console.rglob(f"*{suffix}")), key=lambda path: path.as_posix())
    if any(path.is_symlink() for path in files):
        raise ValueError("symlinked_console_source")
    return files

def _privileged_environment(body: str) -> set[str]:
    found = {first or second for first, second in ENV_REFERENCE.findall(body)}
    return {name for name in found if name in PRIVILEGED_ENV or name.startswith("NEXT_PUBLIC_") and any(secret in name for secret in ("SECRET", "TOKEN", "SERVICE_ROLE", "OPENAI"))}

def _graph(console: Path, files: list[Path]) -> tuple[dict[Path, set[Path]], dict[Path, set[str]], set[Path]]:
    edges: dict[Path, set[Path]] = {path: set() for path in files}
    environment: dict[Path, set[str]] = {}
    clients: set[Path] = set()
    for path in files:
        body = path.read_text(encoding="utf-8")
        environment[path] = _privileged_environment(body)
        if CLIENT_DIRECTIVE.search(body):
            clients.add(path)
        for first, second in IMPORT.findall(body):
            resolved = _resolve_import(console, path, first or second)
            # Next.js server actions are serialized references, not client
            # module dependencies. Traversing past this boundary would turn a
            # legitimate server-only secret into a false browser exposure.
            if resolved is not None and not SERVER_DIRECTIVE.search(resolved.read_text(encoding="utf-8")):
                edges[path].add(resolved)
    return edges, environment, clients

def _reachable_privileged(start: Path, edges: dict[Path, set[Path]], environment: dict[Path, set[str]]) -> tuple[Path, set[str]] | None:
    pending: deque[Path] = deque([start])
    visited: set[Path] = set()
    while pending:
        current = pending.popleft()
        if current in visited:
            continue
        visited.add(current)
        if environment[current]:
            return current, environment[current]
        pending.extend(sorted(edges[current] - visited, key=lambda path: path.as_posix()))
    return None

def _handler_block_start(body: str, start: int) -> int | None:
    """Find a function body after its complete parameter declaration."""
    parentheses = 0
    saw_parameter_close = False
    quote: str | None = None
    escaped = False
    for index in range(start, len(body)):
        char = body[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in "'\"`":
            quote = char
        elif char == "(":
            parentheses += 1
        elif char == ")" and parentheses:
            parentheses -= 1
            saw_parameter_close |= parentheses == 0
        elif char == "{" and parentheses == 0 and saw_parameter_close:
            return index
    return None


def _balanced_block(body: str, start: int) -> str | None:
    """Return the handler body, rejecting malformed TypeScript fail-closed."""
    opening = _handler_block_start(body, start)
    if opening < 0:
        return None
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(opening, len(body)):
        char = body[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in "'\"`":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return body[opening + 1:index]
    return None


def _route_guards(body: str) -> dict[str, str | None]:
    """Find an authentication guard in every exported HTTP handler.

    A route can expose more than one method.  A guard in POST must never
    authorize a separate GET handler that reaches privileged configuration.
    """
    handlers: dict[str, str | None] = {}
    for match in HTTP_HANDLER.finditer(body):
        handler = _balanced_block(body, match.end())
        if handler is None:
            handlers[match.group(1)] = None
        elif ("405" in handler and "await" not in handler and
              "process.env" not in handler):
            # Explicit method rejection cannot consume a server-side import
            # merely because a sibling handler in the same route module does.
            handlers[match.group(1)] = "method_rejected"
        elif OPERATOR_GUARD.search(handler):
            handlers[match.group(1)] = "operator_authentication"
        elif WEBHOOK_GUARD.search(handler):
            handlers[match.group(1)] = "github_webhook_hmac"
        else:
            handlers[match.group(1)] = None
    return handlers


def _route_guard(body: str) -> str | None:
    """Compatibility helper for a single-handler route."""
    guards = _route_guards(body)
    return next(iter(guards.values()), None) if len(guards) == 1 else None

def audit(root: Path) -> dict:
    root = root.resolve(strict=True)
    console = root / "apps" / "console"
    files = _source_files(console)
    edges, environment, clients = _graph(console, files)
    findings: list[dict[str, object]] = []
    for path, names in environment.items():
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "NEXT_PUBLIC_" in line and any(name in line for name in names):
                findings.append({"path": _relative(root, path), "line": line_number, "kind": "privileged_next_public_name"})
    surfaces = set(clients)
    health = (root / PUBLIC_HEALTH).resolve()
    if health.is_file():
        surfaces.add(health)
    for surface in sorted(surfaces, key=lambda path: path.as_posix()):
        reached = _reachable_privileged(surface, edges, environment)
        if reached is not None:
            source, names = reached
            findings.append({"path": _relative(root, surface), "line": 1, "kind": "privileged_environment_reachable_from_public_surface", "source_path": _relative(root, source), "environment_names": sorted(names)})
    route_handlers = [path for path in files if path.name == "route.ts" and "/app/api/" in path.as_posix()]
    for route in route_handlers:
        if route == health:
            continue
        reached = _reachable_privileged(route, edges, environment)
        if reached is None:
            continue
        handlers = _route_guards(route.read_text(encoding="utf-8"))
        unguarded = sorted(name for name, guard in handlers.items() if guard is None)
        if not handlers or unguarded:
            source, names = reached
            findings.append({"path": _relative(root, route), "line": 1, "kind": "privileged_environment_reachable_from_unprotected_route", "source_path": _relative(root, source), "environment_names": sorted(names), "unguarded_handlers": unguarded})
    findings.sort(key=lambda finding: (str(finding["path"]), int(finding["line"]), str(finding["kind"])))
    return {"schema": "factory-block1-credential-exposure-v4", "scope": "static-import-reachability-for-client-public-health-and-per-http-handler-guards-not-runtime-authentication", "console_files_scanned": len(files), "client_entrypoints_scanned": len(clients), "route_handlers_scanned": len(route_handlers), "public_surface_roots": [PUBLIC_HEALTH], "findings": findings, "privileged_values_read": False, "credential_exposure_detected": bool(findings), "security_certified": False, "writes": 0, "paid_calls": 0}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    result = audit(args.root)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(1 if result["credential_exposure_detected"] else 0)
