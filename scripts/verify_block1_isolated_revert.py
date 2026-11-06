"""Execute a real Git revert only in a temporary, remote-less repository.

This is a bounded independent code-rollback rehearsal, NOT a production or
schema rollback certification. Its status can never grant release authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from ai_product_factory.release_policy import ReleaseEnvironment, evaluate_release
from ai_product_factory.models import RiskProfile


def _git(root: Path, env: dict[str, str], *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args], env=env,
        capture_output=True, text=True, check=False, timeout=15,
    )
    if proc.returncode != 0:
        raise RuntimeError("isolated_git_step_failed: " + args[0])
    return proc.stdout.strip()


def exercise(*, root: Path | None = None) -> dict:
    controlled = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_AUTHOR_NAME": "Factory Offline Revert",
        "GIT_AUTHOR_EMAIL": "revert@example.invalid",
        "GIT_COMMITTER_NAME": "Factory Offline Revert",
        "GIT_COMMITTER_EMAIL": "revert@example.invalid",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_NO_REPLACE_OBJECTS": "1",
    }
    prod = evaluate_release(ReleaseEnvironment.PROD, RiskProfile())
    if prod.may_release_autonomously or not prod.human_gate_required:
        raise RuntimeError("production_human_gate_not_enforced")
    if root is not None:
        raise ValueError("external repository path forbidden")
    with tempfile.TemporaryDirectory(prefix="factory-block1-revert-") as folder:
        repo = Path(folder).resolve()
        _git(repo, controlled, "init", "-q", "--initial-branch=main")
        doc = repo / "sample.txt"
        original = b"approved production candidate\n"
        changed = b"candidate with a reversible regression\n"
        doc.write_bytes(original)
        _git(repo, controlled, "add", "sample.txt")
        _git(repo, controlled, "commit", "-q", "-m", "baseline")
        base = _git(repo, controlled, "rev-parse", "HEAD")
        doc.write_bytes(changed)
        _git(repo, controlled, "add", "sample.txt")
        _git(repo, controlled, "commit", "-q", "-m", "introduce regression")
        candidate = _git(repo, controlled, "rev-parse", "HEAD")
        _git(repo, controlled, "revert", "--no-edit", "HEAD")
        reverted = _git(repo, controlled, "rev-parse", "HEAD")
        clean = not _git(repo, controlled, "status", "--porcelain")
        baseline_tree = _git(repo, controlled, "rev-parse", base + "^{tree}")
        final_tree = _git(repo, controlled, "rev-parse", reverted + "^{tree}")
        no_remotes = not _git(repo, controlled, "remote")
        revision_count = _git(repo, controlled, "rev-list", "--count", "HEAD")
        same_file = doc.read_bytes() == original
        passed = (clean and no_remotes and same_file and baseline_tree == final_tree
                  and len({base, candidate, reverted}) == 3 and revision_count == "3")
    return {
        "schema": "factory-block1-isolated-git-revert-v1",
        "scope": "synthetic_offline_revert_not_production_rollback",
        "git_revert_executed": True,
        "reverted_tree_equal_to_baseline": baseline_tree == final_tree,
        "working_tree_clean": clean,
        "no_git_remotes": no_remotes,
        "original_bytes_restored": same_file,
        "distinct_revert_commit": len({base, candidate, reverted}) == 3,
        "commit_count": int(revision_count),
        "baseline_tree_digest": hashlib.sha256(baseline_tree.encode()).hexdigest(),
        "revert_tree_digest": hashlib.sha256(final_tree.encode()).hexdigest(),
        "production_human_gate_required": prod.human_gate_required,
        "passed": passed,
        "production_rollback_executed": False,
        "schema_rollback_executed": False,
        "block1_certified": False,
        "paid_calls": 0,
        "production_writes": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        receipt = exercise()
    except (ValueError, OSError, RuntimeError, subprocess.TimeoutExpired):
        receipt = {"schema": "factory-block1-isolated-git-revert-v1", "passed": False,
                   "block1_certified": False, "production_writes": 0}
    if args.output:
        args.output.write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
