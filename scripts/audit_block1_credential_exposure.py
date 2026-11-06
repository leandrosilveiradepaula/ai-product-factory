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
    findings.sort(key=lambda finding: (str(finding["path"]), int(finding["line"]), str(finding["kind"])))
    return {"schema": "factory-block1-credential-exposure-v2", "scope": "static-import-reachability-for-client-and-public-health-surfaces-not-runtime-authentication", "console_files_scanned": len(files), "client_entrypoints_scanned": len(clients), "public_surface_roots": [PUBLIC_HEALTH], "findings": findings, "privileged_values_read": False, "credential_exposure_detected": bool(findings), "security_certified": False, "writes": 0, "paid_calls": 0}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    result = audit(args.root)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(1 if result["credential_exposure_detected"] else 0)
