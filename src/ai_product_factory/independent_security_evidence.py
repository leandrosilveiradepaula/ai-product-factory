"""Revalidate bounded Gitleaks and dependency evidence without secrets.

This provider deliberately accepts only the two independently executed
pull-request scans.  It reopens their run/job/artifact provenance, verifies
the downloaded ZIP digest and receipt shape, and revokes reuse if any source
that defines the scanned tree/lockfile scope drifted after the human merge.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable, Mapping

from .product_readiness_certification import VerifiedCriterionEvidence

REPO = "leandrosilveiradepaula/ai-product-factory"
SOURCE_SHA = "07fe30d6c7a83614016610ab6b734e16cd306a27"
MERGE_SHA = "163f6a00789885049d56ad0cb69247bd67f5d1ed"
OWNER_WORKFLOW = ".github/workflows/autonomous-runner.yml"
SHA = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z", re.ASCII)
SCANS = (
    (42220370461, "Block 1 independent secret scanner", "gitleaks",
     "block1-full-tree-gitleaks", 13502489760,
     "block1-full-tree-scan-receipt.json",
     ".github/workflows/block1-independent-secrets.yml",
     ("Scan PR/history with independent Gitleaks engine",
      "Scan complete exact commit tree independently of PR diff")),
    (42220370361, "Block 1 independent dependency advisory evidence", "npm",
     "block1-npm-advisories", 13503196981,
     "block1-npm-audit-summary.json",
     ".github/workflows/block1-independent-dependency-audit.yml",
     ("Scan exact production lockfile without package installation",)),
)
SOURCE_FILES = (
    "scripts/audit_block1_complete_tree.py", "scripts/audit_block1_supply_chain.py",
    "apps/console/package.json", "apps/console/package-lock.json", "pyproject.toml",
    "tests/test_block1_independent_security_evidence.py",
    "tests/test_block1_independent_dependency_audit.py",
    ".github/workflows/block1-independent-secrets.yml",
    ".github/workflows/block1-independent-dependency-audit.yml",
)


class SecurityEvidenceBlocked(RuntimeError):
    pass


def require(value: bool, code: str) -> None:
    if not value:
        raise SecurityEvidenceBlocked(code)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _download(url: str, token: str, artifact_id: int) -> bytes:
    expected = f"https://api.github.com/repos/{REPO}/actions/artifacts/{artifact_id}/zip"
    require(url == expected and bool(token), "security_artifact_source_invalid")
    req = urllib.request.Request(expected, headers={"Accept": "application/vnd.github+json", "Authorization": "Bearer " + token})
    try:
        with urllib.request.build_opener(_NoRedirect).open(req, timeout=25) as response:
            raw = response.read(32769)
    except urllib.error.HTTPError as exc:
        require(exc.code in (301, 302, 303, 307, 308), "security_artifact_download_denied")
        target = urllib.parse.urlsplit(exc.headers.get("Location", ""))
        host = (target.hostname or "").lower()
        require(target.scheme == "https" and not target.username and not target.password and (host.endswith(".blob.core.windows.net") or host.endswith(".actions.githubusercontent.com") or host == "pipelines.actions.githubusercontent.com"), "security_artifact_redirect_untrusted")
        with urllib.request.urlopen(urllib.request.Request(target.geturl(), headers={"Accept": "application/zip"}), timeout=25) as response:
            raw = response.read(32769)
    require(0 < len(raw) <= 32768, "security_artifact_size_invalid")
    return raw


def _receipt(raw: bytes, digest: str, kind: str, member: str) -> dict:
    require(digest == "sha256:" + hashlib.sha256(raw).hexdigest(), "security_artifact_digest_invalid")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            rows = archive.infolist()
            require(0 < len(rows) <= 2 and any(x.filename == member and 0 < x.file_size <= 16384 for x in rows), "security_archive_members_invalid")
            value = json.loads(archive.read(member).decode("utf-8"))
    except (zipfile.BadZipFile, OSError, UnicodeError, ValueError) as exc:
        raise SecurityEvidenceBlocked("security_archive_unreadable") from exc
    require(isinstance(value, dict), "security_receipt_invalid")
    if kind == "gitleaks":
        require(value.get("schema") == "factory-block1-complete-tracked-tree-gitleaks-v1" and value.get("assessed_commit") == SOURCE_SHA and value.get("scan_passed") is True and value.get("zero_unreviewed_findings") is True and value.get("trusted_builtin_rules") is True and value.get("repository_allowlists_ignored") is True and type(value.get("tracked_files_scanned")) is int and value["tracked_files_scanned"] > 0 and value.get("all_history_scanned") is False and value.get("secrets_dependencies_certified") is False and value.get("block1_certified") is False and value.get("paid_calls") == 0 and value.get("production_writes") == 0, "security_gitleaks_receipt_scope_invalid")
    else:
        require(value.get("schema") == "factory-block1-npm-advisory-evidence-v1" and value.get("sha") == SOURCE_SHA and value.get("scope") == "production_dependencies_lockfile" and value.get("scanner") == "npm audit" and value.get("valid_report") is True and value.get("passed") is True and value.get("high") == 0 and value.get("critical") == 0 and value.get("scanner_exit_code") == 0 and value.get("block1_certified") is False, "security_npm_receipt_scope_invalid")
    return value


def verify_existing_secrets_dependencies(*, repository: str, assessed_commit: str,
        github_get: Callable[[str], object], archive_fetch: Callable[[str, str, int], bytes] = _download,
        environment: Mapping[str, str] | None = None) -> VerifiedCriterionEvidence:
    env = os.environ if environment is None else environment
    require(repository == REPO and isinstance(assessed_commit, str) and SHA.fullmatch(assessed_commit) and env.get("GITHUB_ACTIONS") == "true" and env.get("GITHUB_REPOSITORY") == REPO and env.get("GITHUB_EVENT_NAME") == "workflow_run" and env.get("GITHUB_REF") == "refs/heads/main" and env.get("GITHUB_WORKFLOW_REF") == REPO + "/" + OWNER_WORKFLOW + "@refs/heads/main", "security_runner_identity_invalid")
    current_id = env.get("GITHUB_RUN_ID", "")
    require(current_id.isdecimal(), "security_current_run_invalid")
    prefix = "/repos/" + REPO
    current = github_get(prefix + "/actions/runs/" + current_id)
    require(isinstance(current, dict) and current.get("id") == int(current_id) and current.get("name") == "Factory autonomous runner" and current.get("path") == OWNER_WORKFLOW and current.get("event") == "workflow_run" and current.get("head_sha") == assessed_commit and current.get("head_branch") == "main" and current.get("run_attempt") == 1, "security_current_runner_unbound")
    main = github_get(prefix + "/git/ref/heads/main")
    require(isinstance(main, dict) and (main.get("object") or {}).get("sha") == assessed_commit, "security_main_drift")
    if assessed_commit != MERGE_SHA:
        compare = github_get(prefix + "/compare/" + MERGE_SHA + "..." + assessed_commit)
        require(isinstance(compare, dict) and compare.get("status") == "ahead" and compare.get("behind_by") == 0 and (compare.get("merge_base_commit") or {}).get("sha") == MERGE_SHA, "security_merge_not_ancestor")
    for path in SOURCE_FILES:
        old = github_get(prefix + "/contents/" + path + "?ref=" + SOURCE_SHA)
        new = github_get(prefix + "/contents/" + path + "?ref=" + assessed_commit)
        require(isinstance(old, dict) and isinstance(new, dict) and isinstance(old.get("sha"), str) and old.get("sha") == new.get("sha") and old.get("size") == new.get("size") and type(old.get("size")) is int and old["size"] > 0, "security_source_code_drift")
    receipts = {}
    for run_id, name, kind, artifact_name, artifact_id, member, workflow, steps in SCANS:
        run = github_get(prefix + "/actions/runs/" + str(run_id))
        require(isinstance(run, dict) and run.get("id") == run_id and run.get("name") == name and run.get("path") == workflow and run.get("event") == "pull_request" and run.get("head_sha") == SOURCE_SHA and run.get("status") == "completed" and run.get("conclusion") == "success" and run.get("run_attempt") == 1, "security_source_run_invalid")
        jobs = github_get(prefix + "/actions/runs/" + str(run_id) + "/jobs?per_page=100")
        rows = jobs.get("jobs") if isinstance(jobs, dict) else None
        require(isinstance(rows, list) and jobs.get("total_count") == 1 and len(rows) == 1 and isinstance(rows[0], dict) and rows[0].get("run_id") == run_id and rows[0].get("head_sha") == SOURCE_SHA and rows[0].get("status") == "completed" and rows[0].get("conclusion") == "success" and all(any(isinstance(x, dict) and x.get("name") == step and x.get("status") == "completed" and x.get("conclusion") == "success" for x in rows[0].get("steps", [])) for step in steps), "security_source_job_invalid")
        inventory = github_get(prefix + "/actions/runs/" + str(run_id) + "/artifacts?per_page=100")
        artifacts = inventory.get("artifacts") if isinstance(inventory, dict) else None
        require(isinstance(artifacts, list) and inventory.get("total_count") == 1 and len(artifacts) == 1 and isinstance(artifacts[0], dict), "security_artifact_inventory_invalid")
        artifact = artifacts[0]; binding = artifact.get("workflow_run") or {}
        require(artifact.get("id") == artifact_id and artifact.get("name") == artifact_name and artifact.get("expired") is False and isinstance(artifact.get("digest"), str) and DIGEST.fullmatch(artifact["digest"]) and type(artifact.get("size_in_bytes")) is int and 0 < artifact["size_in_bytes"] <= 32768 and binding.get("id") == run_id and binding.get("head_sha") == SOURCE_SHA and binding.get("head_repository_id") == 1387883686, "security_artifact_provenance_invalid")
        receipts[kind] = _receipt(archive_fetch(artifact.get("archive_download_url", ""), env.get("GITHUB_TOKEN", ""), artifact_id), artifact["digest"], kind, member)
    latest = github_get(prefix + "/git/ref/heads/main")
    require(isinstance(latest, dict) and (latest.get("object") or {}).get("sha") == assessed_commit, "security_main_changed_while_verifying")
    return VerifiedCriterionEvidence(domain="security", criterion="secrets_dependencies", repository=repository, assessed_commit=assessed_commit, verification_state="reviewed", source="source-verified-gitleaks-and-npm:" + ":".join(str(x[0]) for x in SCANS), evidence=("https://github.com/" + repository + "/actions/runs/" + str(current_id) + "#sha=" + assessed_commit,), retained_receipt={"gitleaks": receipts["gitleaks"], "npm": receipts["npm"]})
