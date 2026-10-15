"""GitHub App read-only inventory for an exact open existing-project PR.

Do not promote this result to an existing_project_baseline or product readiness.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib import request, error

from .existing_project_inventory import BaselineInventoryError
from .github_auth import resolve_github_token

SHA = re.compile(r"[0-9a-f]{40}\Z")
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
MAX_BYTES = 16 * 1024 * 1024
MAX_PATHS = 100_000


def inventory_candidate(*, repository: str, candidate_sha: str, pr_number: int, get_json) -> dict:
    if (not isinstance(repository, str) or not REPO.fullmatch(repository)
        or any(part in (".", "..") for part in repository.split("/"))):
        raise BaselineInventoryError("invalid repository identity")
    if not isinstance(candidate_sha, str) or not SHA.fullmatch(candidate_sha):
        raise BaselineInventoryError("invalid candidate SHA")
    if type(pr_number) is not int or pr_number < 1:
        raise BaselineInventoryError("invalid PR number")
    prefix = f"/repos/{repository}"
    repo = get_json(prefix)
    if not isinstance(repo, dict) or repo.get("full_name") != repository or repo.get("default_branch") != "main":
        raise BaselineInventoryError("repository identity mismatch")
    pull = get_json(f"{prefix}/pulls/{pr_number}")
    if not isinstance(pull, dict) or pull.get("number") != pr_number or pull.get("state") != "open":
        raise BaselineInventoryError("PR no longer open")
    head, base = pull.get("head"), pull.get("base")
    if (not isinstance(head, dict) or not isinstance(base, dict)
        or head.get("sha") != candidate_sha or not isinstance(head.get("repo"), dict)
        or head["repo"].get("full_name") != repository or base.get("ref") != "main"
        or not isinstance(base.get("repo"), dict) or base["repo"].get("full_name") != repository):
        raise BaselineInventoryError("PR head/base mismatch")
    commit = get_json(f"{prefix}/git/commits/{candidate_sha}")
    if not isinstance(commit, dict) or commit.get("sha") != candidate_sha:
        raise BaselineInventoryError("commit identity mismatch")
    tree_sha = (commit.get("tree") or {}).get("sha")
    if not isinstance(tree_sha, str) or not SHA.fullmatch(tree_sha):
        raise BaselineInventoryError("missing commit tree")
    tree = get_json(f"{prefix}/git/trees/{tree_sha}?recursive=1")
    if (not isinstance(tree, dict) or tree.get("sha") != tree_sha
        or tree.get("truncated") is not False or not isinstance(tree.get("tree"), list)):
        raise BaselineInventoryError("incomplete or mismatched GitHub tree")
    paths = []
    for entry in tree["tree"]:
        if not isinstance(entry, dict):
            raise BaselineInventoryError("invalid tree item")
        if entry.get("type") == "tree" and entry.get("mode") == "040000":
            continue
        if entry.get("type") != "blob" or entry.get("mode") not in ("100644", "100755"):
            raise BaselineInventoryError("unsupported symlink or submodule")
        paths.append(entry.get("path"))
    if (not paths or len(paths) > MAX_PATHS or any(
        not isinstance(path, str) or not path or path.startswith("/")
        or ".." in path.split("/") or "\x00" in path for path in paths
    ) or len(paths) != len(set(paths))):
        raise BaselineInventoryError("invalid or unsafe committed paths")
    low = [path.lower() for path in paths]
    counts = {
        "tracked_files": len(paths),
        "source_files": sum(p.startswith(("src/", "app/", "apps/", "pages/", "lib/", "packages/")) for p in low),
        "test_files": sum(
            p.startswith(("tests/", "test/", "e2e/", "scripts/tests/"))
            or p.endswith((".test.ts", ".test.tsx", ".test.js", ".spec.ts", ".spec.tsx", ".spec.js"))
            for p in low
        ),
        "migration_files": sum(p.startswith(("supabase/migrations/", "db/migrations/", "prisma/migrations/", "migrations/")) for p in low),
        "workflow_files": sum(p.startswith(".github/workflows/") and p.endswith((".yml", ".yaml")) for p in low),
        "route_files": sum(p.endswith(("/page.ts", "/page.tsx", "/route.ts", "/route.tsx")) for p in low),
        "debt_documentation_present": any(p in (
            "docs/operations.md", "docs/technical-debt.md", "docs/release_rollback.md"
        ) for p in low),
    }
    return {
        "schema_version": 1, "repository_claim": repository, "project_kind": "existing",
        "assessed_commit": candidate_sha, "baseline_ref": candidate_sha,
        "candidate_pr_number": pr_number, "github_tree_sha": tree_sha,
        "remote_identity_verified": True, "status": "not_assessed",
        "verification_state": "inventory_only", "coverage": ["repository_inventory"],
        "inventory": counts, "evidence": [],
        "blockers": [
            "inherited_debt: independently reviewed evidence missing",
            "critical_journeys: authenticated remote tests missing",
            "runtime_schema_rls: target CRM database evidence missing",
        ],
        "production_schema_verified": False, "authenticated_journeys_verified": False,
    }


def _get(token: str, path: str):
    req = request.Request("https://api.github.com" + path, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }, method="GET")
    try:
        with request.urlopen(req, timeout=30) as response:
            data = response.read(MAX_BYTES + 1)
    except (error.HTTPError, error.URLError, TimeoutError) as exc:
        raise BaselineInventoryError("read-only GitHub API unavailable") from exc
    if len(data) > MAX_BYTES:
        raise BaselineInventoryError("GitHub inventory exceeds size bound")
    try:
        return json.loads(data)
    except (UnicodeError, ValueError) as exc:
        raise BaselineInventoryError("invalid GitHub response") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        target = json.loads(args.target.read_text(encoding="utf-8"))
        if not isinstance(target, dict) or set(target) != {"repository", "candidate_sha", "pr_number"}:
            raise BaselineInventoryError("target must be exactly pinned")
        repository = target["repository"]
        token = resolve_github_token(repository)
        result = inventory_candidate(
            repository=repository, candidate_sha=target["candidate_sha"],
            pr_number=target["pr_number"], get_json=lambda path: _get(token, path)
        )
        if result["status"] != "not_assessed" or result["verification_state"] != "inventory_only":
            raise BaselineInventoryError("passing inventory forbidden")
    except (BaselineInventoryError, ValueError, TypeError, PermissionError, KeyError, OSError) as exc:
        parser.error("inventory failed closed: " + str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "inventory_only", "candidate_sha": result["assessed_commit"],
                      "tracked_files": result["inventory"]["tracked_files"],
                      "product_ready": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
