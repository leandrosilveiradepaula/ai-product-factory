"""Map simulation markers to the runtime CLI import closure, fail closed.

The marker inventory is intentionally broad.  This companion audit answers a
narrower question: whether a marker-bearing module is statically importable by
the production CLI, and whether the marker is part of an explicit rejection
guard.  It does not attest runtime reachability, authorization, or release.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from collections import deque
from pathlib import Path

ROOT_MODULE = "runtime_cli"
MARKER = re.compile(r"(?i)(?<![a-z0-9_])(dry_run|dry-run|mock|noop|no_op|fixture|demo|simulated|placeholder|deferred)(?![a-z0-9_])")
MARKER_KINDS = {"dry_run": "simulation", "dry-run": "simulation", "mock": "test_double", "noop": "no_operation", "no_op": "no_operation", "fixture": "fixture", "demo": "demonstration", "simulated": "simulation", "placeholder": "simulation", "deferred": "simulation"}


def _module_path(source: Path, name: str) -> Path:
    return source / f"{name}.py"


def _relative_import(module: str, level: int, name: str | None) -> str | None:
    parts = module.split(".")
    base = parts[:-level] if level else []
    if level and len(parts) < level:
        return None
    if name:
        base.extend(name.split("."))
    return ".".join(base) or None


def _imports(module: str, tree: ast.Module) -> set[str]:
    output: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            target = _relative_import(module, node.level, node.module)
            if target:
                output.add(target)
        elif isinstance(node, ast.Import):
            output.update(alias.name for alias in node.names if not alias.name.startswith(("typing", "pathlib", "json", "os", "sys", "datetime", "uuid", "dataclasses", "collections", "re", "hashlib", "urllib", "subprocess", "time", "argparse")))
    return output


def _marker_constants(tree: ast.Module) -> dict[str, set[str]]:
    values: dict[str, set[str]] = {}
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names = [target.id for target in targets if isinstance(target, ast.Name)]
        if not names:
            continue
        strings = {value.value for value in ast.walk(node.value) if isinstance(value, ast.Constant) and isinstance(value.value, str) and MARKER.search(value.value)}
        for name in names:
            if strings:
                values[name] = strings
    return values


def _guarded_names(tree: ast.Module, constants: dict[str, set[str]]) -> set[str]:
    guarded: set[str] = set()
    for function in (node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))):
        used = {node.id for node in ast.walk(function) if isinstance(node, ast.Name) and node.id in constants}
        if used and any(isinstance(node, ast.Raise) for node in ast.walk(function)):
            guarded.update(used)
    return guarded


def audit(root: Path) -> dict:
    root = root.resolve(strict=True)
    source = root / "src" / "ai_product_factory"
    if not source.is_dir() or source.is_symlink():
        raise ValueError("missing_or_symlinked_runtime_tree")
    pending: deque[str] = deque([ROOT_MODULE])
    parsed: dict[str, ast.Module] = {}
    while pending:
        module = pending.popleft()
        if module in parsed:
            continue
        path = _module_path(source, module)
        if not path.is_file() or path.is_symlink():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        parsed[module] = tree
        for imported in _imports(module, tree):
            if _module_path(source, imported).is_file():
                pending.append(imported)
    rows: list[dict[str, object]] = []
    for module, tree in sorted(parsed.items()):
        constants = _marker_constants(tree)
        guarded = _guarded_names(tree, constants)
        path = _module_path(source, module).relative_to(root).as_posix()
        for name, values in sorted(constants.items()):
            rows.append({"module": module, "path": path, "constant": name, "markers": sorted(values), "classification": "explicit_rejection_guard" if name in guarded else "unclassified_runtime_marker"})
    unsafe = [row for row in rows if row["classification"] != "explicit_rejection_guard"]
    return {"schema": "factory-block1-runtime-simulation-reachability-v1", "scope": "static-runtime-cli-import-closure-and-guard-classification-not-runtime-proof", "entrypoint": "src/ai_product_factory/runtime_cli.py", "reachable_modules": sorted(parsed), "marker_bindings": rows, "unclassified_runtime_markers": unsafe, "simulation_can_authorize_release": False, "independent_pass": False, "functional_completeness_certified": False, "writes": 0, "paid_calls": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    result = audit(args.root)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(1 if result["unclassified_runtime_markers"] else 0)
