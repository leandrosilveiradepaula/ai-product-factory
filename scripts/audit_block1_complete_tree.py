"""Independent Gitleaks scan of the complete committed candidate tree.

The pre-existing PR scanner examines git history under a first-parent range.
This second, fail-closed scan examines *every tracked file* from the exact
HEAD tree, including files reachable through merge commits. It never reports
secret-bearing output and never attests full historical leak remediation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile

SHA = re.compile(r"[a-f0-9]{40}\Z")
VERSION = "8.24.3"
CI_SCANNER = Path("/tmp/gitleaks-8.24.3/gitleaks")


class ScanBlocked(RuntimeError):
    """Expected fail-closed outcome, without secret content."""


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, text=True, timeout=20, check=False,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
             "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
             "GIT_TERMINAL_PROMPT": "0"},
    )
    if result.returncode != 0:
        raise ScanBlocked("git_identity_not_verified")
    return result.stdout.strip()


def _extract_committed_tree(archive: Path, target: Path) -> int:
    """Reject tar traversal, symlinks, and duplicate names before extraction."""
    seen: set[str] = set()
    count = 0
    try:
        with tarfile.open(archive, "r") as tar:
            members = tar.getmembers()
            if not 0 < len(members) <= 30000:
                raise ScanBlocked("archive_entries_out_of_bounds")
            for member in members:
                item = PurePosixPath(member.name)
                if (item.is_absolute() or ".." in item.parts or
                        not item.parts or item.parts[0] == ".git" or
                        member.name in seen or
                        not (member.isdir() or member.isfile()) or
                        member.size > 40 * 1024 * 1024):
                    raise ScanBlocked("unsafe_or_ambiguous_committed_tree")
                seen.add(member.name)
            for member in members:
                dest = target.joinpath(*PurePosixPath(member.name).parts)
                if member.isdir():
                    dest.mkdir(parents=True, exist_ok=True)
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                source = tar.extractfile(member)
                if source is None:
                    raise ScanBlocked("tracked_blob_missing")
                with source, dest.open("xb") as output:
                    shutil.copyfileobj(source, output)
                count += 1
    except (OSError, tarfile.TarError) as exc:
        raise ScanBlocked("tracked_tree_archive_invalid") from exc
    if count == 0:
        raise ScanBlocked("empty_committed_tree")
    return count


def audit(root: Path, scanner: Path) -> dict:
    root = root.resolve(strict=True)
    scanner = scanner.resolve(strict=True)
    if (not scanner.is_file() or
            root == scanner or root in scanner.parents or
            _git(root, "rev-parse", "--show-toplevel") != str(root)):
        raise ScanBlocked("scanner_or_repository_identity_invalid")
    if os.environ.get("GITHUB_ACTIONS") == "true" and scanner != CI_SCANNER:
        raise ScanBlocked("untrusted_ci_scanner_path")
    sha = _git(root, "rev-parse", "HEAD")
    tree = _git(root, "rev-parse", "HEAD^{tree}")
    if not SHA.fullmatch(sha) or not SHA.fullmatch(tree):
        raise ScanBlocked("not_an_exact_git_commit")
    version_result = subprocess.run([str(scanner), "--version"], capture_output=True,
                                    text=True, timeout=10, check=False)
    version_text = version_result.stdout + version_result.stderr
    if version_result.returncode != 0 or not re.search(r"(?<!\d)8\.24\.3(?!\d)", version_text):
        raise ScanBlocked("gitleaks_version_not_pinned")
    with tempfile.TemporaryDirectory(prefix="factory-block1-full-tree-") as folder:
        temporary = Path(folder)
        source = temporary / "source"
        source.mkdir()
        archive = temporary / "candidate.tar"
        create = subprocess.run(
            ["git", "-C", str(root), "archive", "--format=tar",
             "--output", str(archive), sha],
            capture_output=True, timeout=35, check=False,
        )
        if create.returncode != 0 or not archive.is_file():
            raise ScanBlocked("committed_snapshot_not_available")
        if not 0 < archive.stat().st_size <= 150 * 1024 * 1024:
            raise ScanBlocked("committed_snapshot_size_invalid")
        count = _extract_committed_tree(archive, source)
        config = temporary / "trusted.toml"
        config.write_text("[extend]\nuseDefault = true\n", encoding="utf-8")
        ignore = temporary / "no-allowlist"
        ignore.write_text("", encoding="utf-8")
        report_file = temporary / "private-results.json"
        command = [
            str(scanner), "dir", "--config", str(config),
            "--gitleaks-ignore-path", str(ignore),
            "--ignore-gitleaks-allow", "--redact", "--no-banner",
            "--report-format", "json", "--report-path", str(report_file),
            "--exit-code", "2", str(source),
        ]
        scan = subprocess.run(command, capture_output=True, timeout=150, check=False,
                              env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                                   "HOME": str(temporary)})
        # Raw scanner stdout, stderr, and findings remain private; none is
        # written to an Actions artifact or included in this receipt.
        if scan.returncode != 0:
            raise ScanBlocked("secret_findings_detected" if scan.returncode == 2 else "scanner_runtime_error")
        if report_file.exists():
            try:
                parsed = json.loads(report_file.read_text(encoding="utf-8"))
            except (UnicodeError, ValueError, OSError) as exc:
                raise ScanBlocked("scan_report_invalid") from exc
            if not isinstance(parsed, list) or parsed:
                raise ScanBlocked("unexpected_nonempty_scan_report")
    return {
        "schema": "factory-block1-complete-tracked-tree-gitleaks-v1",
        "assessed_commit": sha,
        "tree_oid": tree,
        "tracked_files_scanned": count,
        "scanner": "gitleaks",
        "scanner_version": VERSION,
        "scope": "complete_committed_tree_not_all_historical_git_commits",
        "trusted_builtin_rules": True,
        "repository_allowlists_ignored": True,
        "source_digest": hashlib.sha256((sha + ":" + tree).encode()).hexdigest(),
        "scan_passed": True,
        "all_history_scanned": False,
        "secrets_dependencies_certified": False,
        "block1_certified": False,
        "production_writes": 0,
        "paid_calls": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scanner", type=Path, default=CI_SCANNER)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=Path("block1-full-tree-scan-receipt.json"))
    args = parser.parse_args()
    try:
        result = audit(args.root, args.scanner)
        code = 0
    except (ScanBlocked, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        error_code = str(exc) if type(exc) is ScanBlocked else type(exc).__name__
        result = {"schema": "factory-block1-complete-tracked-tree-gitleaks-v1",
                  "block_reason": error_code, "scan_passed": False, "secrets_dependencies_certified": False,
                  "block1_certified": False, "paid_calls": 0,
                  "production_writes": 0}
        code = 1
    args.output.write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
