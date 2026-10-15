"""Read-only committed-tree inventory for an imported/existing project.

This is a pre-audit artifact, deliberately NOT an existing_project_baseline
evaluation: git paths alone cannot verify inherited debt, user journeys,
remote auth, or the target project's production database.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess


_SHA = re.compile(r"[0-9a-f]{40}\Z")
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_MAX_BYTES = 16 * 1024 * 1024
_MAX_PATHS = 100_000


class BaselineInventoryError(ValueError):
    """Input, checkout provenance or bounded inventory is not verifiable."""


def _git(root: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise BaselineInventoryError("git inventory could not be verified") from exc
    if len(result.stdout) > _MAX_BYTES:
        raise BaselineInventoryError("git inventory exceeds safe byte limit")
    return result.stdout


def scan_existing_checkout(*, root: Path, candidate_sha: str, repository: str) -> dict:
    """Inventory a pinned commit without reading source content or credentials.

    The caller must independently attest the remote repository identity, CI,
    migrations, auth/RLS and critical browser journeys. The output cannot be
    used as a passing factory_evaluations row.
    """
    if not _SHA.fullmatch(candidate_sha):
        raise BaselineInventoryError("candidate must be an exact lowercase SHA")
    if not _REPOSITORY.fullmatch(repository):
        raise BaselineInventoryError("repository must use owner/name syntax")
    root = root.resolve()
    if not root.is_dir():
        raise BaselineInventoryError("checkout directory missing")

    try:
        toplevel = _git(root, "rev-parse", "--show-toplevel").decode("utf-8").strip()
        head = _git(root, "rev-parse", "HEAD").decode("ascii").strip()
    except UnicodeError as exc:
        raise BaselineInventoryError("malformed git identity") from exc
    if Path(toplevel).resolve() != root:
        raise BaselineInventoryError("checkout must be repository root")
    if head != candidate_sha:
        raise BaselineInventoryError("checkout HEAD differs from candidate")

    raw = _git(root, "ls-tree", "-r", "-z", "--name-only", candidate_sha)
    if not raw or not raw.endswith(b"\0"):
        raise BaselineInventoryError("empty or malformed committed tree")
    try:
        paths = [value.decode("utf-8") for value in raw[:-1].split(b"\0")]
    except UnicodeDecodeError as exc:
        raise BaselineInventoryError("non-UTF8 tracked paths") from exc
    if len(paths) > _MAX_PATHS or len(set(paths)) != len(paths):
        raise BaselineInventoryError("repository tree exceeds limits or repeats paths")
    if any(not p or p.startswith("/") or ".." in p.split("/") for p in paths):
        raise BaselineInventoryError("unsafe committed tree path")

    lower = [p.lower() for p in paths]
    source_files = sum(p.startswith(("src/", "app/", "apps/", "pages/", "lib/", "packages/")) for p in lower)
    tests = sum(
        p.startswith(("tests/", "test/", "e2e/", "scripts/tests/"))
        or p.endswith((".test.ts", ".test.tsx", ".test.js", ".spec.ts", ".spec.tsx", ".spec.js"))
        for p in lower
    )
    migrations = sum(
        p.startswith(("supabase/migrations/", "db/migrations/", "prisma/migrations/", "migrations/"))
        for p in lower
    )
    workflows = sum(p.startswith(".github/workflows/") and p.endswith((".yml", ".yaml")) for p in lower)
    routes = sum(p.endswith(("/page.ts", "/page.tsx", "/route.ts", "/route.tsx")) for p in lower)
    debt_docs = any(p in ("docs/operations.md", "docs/technical-debt.md", "docs/release_rollback.md") for p in lower)
    blockers = [
        "inherited_debt: independently reviewed debt register/evidence missing",
        "critical_journeys: authenticated exact-SHA end-to-end results missing",
        "remote_repository: independently verified GitHub origin and checks missing",
        "runtime_schema_rls: target environment verification missing",
    ]
    if source_files == 0:
        blockers.append("repository_inventory: no recognized application sources")
    if tests == 0:
        blockers.append("repository_inventory: no recognized tests")
    if not debt_docs:
        blockers.append("inherited_debt: operational/debt document not found")

    return {
        "schema_version": 1,
        "repository_claim": repository,
        "assessed_commit": candidate_sha,
        "baseline_ref": candidate_sha,
        "project_kind": "existing",
        "status": "not_assessed",
        "verification_state": "inventory_only",
        "coverage": ["repository_inventory"],
        "inventory": {
            "tracked_files": len(paths),
            "source_files": source_files,
            "test_files": tests,
            "migration_files": migrations,
            "workflow_files": workflows,
            "route_files": routes,
            "debt_documentation_present": debt_docs,
        },
        "blockers": blockers,
        "evidence": [],
        "remote_identity_verified": False,
        "production_schema_verified": False,
        "authenticated_journeys_verified": False,
        "working_tree_contents_inspected": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate non-passing existing project git inventory")
    parser.add_argument("--repo-path", type=Path, required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--repository", required=True)
    args = parser.parse_args(argv)
    try:
        result = scan_existing_checkout(
            root=args.repo_path, candidate_sha=args.candidate_sha, repository=args.repository
        )
    except BaselineInventoryError as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
