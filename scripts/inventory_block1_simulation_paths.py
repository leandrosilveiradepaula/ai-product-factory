"""Deterministic, read-only inventory of simulation markers in Factory runtime.

This is a triage tool, NOT a proof that a simulated path is unreachable.
Scans production Python sources, excludes tests/docs, emits only paths,
line numbers, and marker kinds. No source lines, credentials or code values.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re

MARKER = re.compile(r"(?i)(?<![a-z0-9_])(dry_run|dry-run|mock|noop|no_op|fixture|demo)(?![a-z0-9_])")
KINDS = {"dry_run": "simulation", "dry-run": "simulation", "mock": "test_double",
         "noop": "no_operation", "no_op": "no_operation",
         "fixture": "fixture", "demo": "demonstration"}
LIMIT = 10000


def inventory(root: Path) -> dict:
    root = root.resolve(strict=True)
    source = root / "src" / "ai_product_factory"
    if not source.is_dir() or source.is_symlink():
        raise ValueError("missing or symlinked runtime tree")
    results = []
    scanned = 0
    for path in sorted(source.rglob("*.py")):
        if path.is_symlink() or not path.is_file():
            raise ValueError("symlinked runtime source")
        rel = path.relative_to(root).as_posix()
        body = path.read_text(encoding="utf-8")
        ast.parse(body, filename=rel)
        scanned += 1
        for lineno, line in enumerate(body.splitlines(), start=1):
            kinds = sorted({KINDS[m.group(1).lower()] for m in MARKER.finditer(line)})
            if kinds:
                results.append({"path": rel, "line": lineno, "kinds": kinds})
            if len(results) > LIMIT:
                raise ValueError("inventory limit exceeded")
    fingerprint = hashlib.sha256(
        json.dumps(results, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": 1,
        "scope": "source_markers_not_runtime_reachability",
        "source_files": scanned,
        "marker_occurrences_by_line": len(results),
        "locations": results,
        "fingerprint": fingerprint,
        "independent_pass": False,
        "production_ready": False,
        "secrets_exposed": False,
        "paid_calls": 0,
        "writes_to_production": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = inventory(args.root)
    serialized = json.dumps(result, sort_keys=True, ensure_ascii=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(json.dumps({key: result[key] for key in
          ("scope", "source_files", "marker_occurrences_by_line", "fingerprint", "independent_pass")},
          sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
