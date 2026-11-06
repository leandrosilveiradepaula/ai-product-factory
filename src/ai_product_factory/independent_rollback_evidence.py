"""Revalidate one bounded, independent rollback rehearsal for documentation.

The rehearsal proves that the documented *code* rollback procedure and human
production gate were exercised in an isolated repository.  It explicitly
cannot prove a production or schema rollback, and therefore only attests the
documentation/release_rollback criterion.
"""
from __future__ import annotations

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
SOURCE_RUN = 42220370480
ARTIFACT_ID = 13503341190
ARTIFACT_NAME = "block1-offline-revert-receipt"
ARTIFACT_FILE = "block1-isolated-revert-receipt.json"
WORKFLOW = ".github/workflows/block1-offline-revert-evidence.yml"
OWNER_WORKFLOW = ".github/workflows/autonomous-runner.yml"
SOURCE_FILES = ("scripts/verify_block1_isolated_revert.py", "src/ai_product_factory/release_policy.py", "src/ai_product_factory/models.py", WORKFLOW)
SHA = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)


class RollbackEvidenceBlocked(RuntimeError):
    pass


def require(condition: bool, code: str) -> None:
    if not condition:
        raise RollbackEvidenceBlocked(code)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _download(url: str, token: str) -> bytes:
    expected = f"https://api.github.com/repos/{REPO}/actions/artifacts/{ARTIFACT_ID}/zip"
    require(url == expected and bool(token), "rollback_artifact_source_invalid")
    request = urllib.request.Request(expected, method="GET", headers={"Accept": "application/vnd.github+json", "Authorization": "Bearer " + token})
    try:
        with urllib.request.build_opener(_NoRedirect).open(request, timeout=25) as response:
            raw = response.read(16385)
    except urllib.error.HTTPError as exc:
        require(exc.code in (301, 302, 303, 307, 308), "rollback_artifact_download_denied")
        location = exc.headers.get("Location", "")
        target = urllib.parse.urlsplit(location)
        host = (target.hostname or "").lower()
        require(target.scheme == "https" and not target.username and not target.password and (host.endswith(".blob.core.windows.net") or host.endswith(".actions.githubusercontent.com") or host == "pipelines.actions.githubusercontent.com"), "rollback_artifact_redirect_untrusted")
        with urllib.request.urlopen(urllib.request.Request(location, headers={"Accept": "application/zip"}), timeout=25) as response:
            raw = response.read(16385)
    require(0 < len(raw) <= 16384, "rollback_artifact_size_invalid")
    return raw


def _receipt(raw: bytes, digest: str) -> dict:
    require(digest == "sha256:" + hashlib.sha256(raw).hexdigest(), "rollback_artifact_digest_invalid")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            rows = archive.infolist()
            require(len(rows) == 1 and rows[0].filename == ARTIFACT_FILE and 0 < rows[0].file_size <= 8192, "rollback_archive_members_invalid")
            value = json.loads(archive.read(rows[0]).decode("utf-8"))
    except (zipfile.BadZipFile, UnicodeError, ValueError, OSError) as exc:
        raise RollbackEvidenceBlocked("rollback_archive_unreadable") from exc
    expected = {
        "schema": "factory-block1-isolated-git-revert-v1", "scope": "synthetic_offline_revert_not_production_rollback",
        "git_revert_executed": True, "reverted_tree_equal_to_baseline": True, "working_tree_clean": True,
        "no_git_remotes": True, "original_bytes_restored": True, "distinct_revert_commit": True,
        "commit_count": 3, "production_human_gate_required": True, "passed": True,
        "production_rollback_executed": False, "schema_rollback_executed": False,
        "block1_certified": False, "paid_calls": 0, "production_writes": 0,
    }
    require(isinstance(value, dict) and all(value.get(key) == item for key, item in expected.items()) and isinstance(value.get("baseline_tree_digest"), str) and isinstance(value.get("revert_tree_digest"), str), "rollback_receipt_scope_invalid")
    return value


def verify_existing_isolated_rollback(*, repository: str, assessed_commit: str, github_get: Callable[[str], object], archive_fetch: Callable[[str, str], bytes] = _download, environment: Mapping[str, str] | None = None) -> VerifiedCriterionEvidence:
    env = os.environ if environment is None else environment
    require(repository == REPO and isinstance(assessed_commit, str) and SHA.fullmatch(assessed_commit) and env.get("GITHUB_ACTIONS") == "true" and env.get("GITHUB_REPOSITORY") == REPO and env.get("GITHUB_EVENT_NAME") == "workflow_run" and env.get("GITHUB_REF") == "refs/heads/main" and env.get("GITHUB_WORKFLOW_REF") == REPO + "/" + OWNER_WORKFLOW + "@refs/heads/main", "rollback_runner_identity_invalid")
    current_id = env.get("GITHUB_RUN_ID", "")
    require(current_id.isdecimal(), "rollback_current_run_invalid")
    prefix = "/repos/" + REPO
    current = github_get(prefix + "/actions/runs/" + current_id)
    require(isinstance(current, dict) and current.get("id") == int(current_id) and current.get("name") == "Factory autonomous runner" and current.get("path") == OWNER_WORKFLOW and current.get("event") == "workflow_run" and current.get("head_sha") == assessed_commit and current.get("head_branch") == "main" and current.get("run_attempt") == 1, "rollback_current_runner_unbound")
    source = github_get(prefix + "/actions/runs/" + str(SOURCE_RUN))
    require(isinstance(source, dict) and source.get("id") == SOURCE_RUN and source.get("name") == "Block 1 isolated rollback rehearsal" and source.get("path") == WORKFLOW and source.get("event") == "pull_request" and source.get("head_sha") == SOURCE_SHA and source.get("run_attempt") == 1 and source.get("status") == "completed" and source.get("conclusion") == "success", "rollback_source_run_invalid")
    jobs = github_get(prefix + "/actions/runs/" + str(SOURCE_RUN) + "/jobs?per_page=100")
    rows = jobs.get("jobs") if isinstance(jobs, dict) else None
    require(isinstance(rows, list) and jobs.get("total_count") == 1 and len(rows) == 1 and isinstance(rows[0], dict) and rows[0].get("name") == "isolated-git-revert" and rows[0].get("run_id") == SOURCE_RUN and rows[0].get("head_sha") == SOURCE_SHA and rows[0].get("status") == "completed" and rows[0].get("conclusion") == "success" and any(isinstance(step, dict) and step.get("name") == "Reproduce offline Git revert and enforce production human gate" and step.get("status") == "completed" and step.get("conclusion") == "success" for step in rows[0].get("steps", [])), "rollback_source_job_invalid")
    main = github_get(prefix + "/git/ref/heads/main")
    require(isinstance(main, dict) and (main.get("object") or {}).get("sha") == assessed_commit, "rollback_main_drift")
    if assessed_commit != MERGE_SHA:
        comparison = github_get(prefix + "/compare/" + MERGE_SHA + "..." + assessed_commit)
        require(isinstance(comparison, dict) and comparison.get("status") == "ahead" and comparison.get("behind_by") == 0 and (comparison.get("merge_base_commit") or {}).get("sha") == MERGE_SHA, "rollback_merge_not_ancestor")
    for path in SOURCE_FILES:
        old = github_get(prefix + "/contents/" + path + "?ref=" + SOURCE_SHA)
        new = github_get(prefix + "/contents/" + path + "?ref=" + assessed_commit)
        require(isinstance(old, dict) and isinstance(new, dict) and isinstance(old.get("sha"), str) and old.get("sha") == new.get("sha") and type(old.get("size")) is int and old["size"] > 0 and old.get("size") == new.get("size"), "rollback_source_code_drift")
    inventory = github_get(prefix + "/actions/runs/" + str(SOURCE_RUN) + "/artifacts?per_page=100")
    artifacts = inventory.get("artifacts") if isinstance(inventory, dict) else None
    require(isinstance(artifacts, list) and inventory.get("total_count") == 1 and len(artifacts) == 1 and isinstance(artifacts[0], dict), "rollback_artifact_inventory_invalid")
    artifact = artifacts[0]
    binding = artifact.get("workflow_run") or {}
    require(artifact.get("id") == ARTIFACT_ID and artifact.get("name") == ARTIFACT_NAME and artifact.get("expired") is False and isinstance(artifact.get("digest"), str) and re.fullmatch(r"sha256:[0-9a-f]{64}", artifact["digest"]) and type(artifact.get("size_in_bytes")) is int and 0 < artifact["size_in_bytes"] <= 16384 and binding.get("id") == SOURCE_RUN and binding.get("head_sha") == SOURCE_SHA and binding.get("head_repository_id") == 1387883686, "rollback_artifact_provenance_invalid")
    receipt = _receipt(archive_fetch(artifact.get("archive_download_url", ""), env.get("GITHUB_TOKEN", "")), artifact["digest"])
    latest = github_get(prefix + "/git/ref/heads/main")
    require(isinstance(latest, dict) and (latest.get("object") or {}).get("sha") == assessed_commit, "rollback_main_changed_while_verifying")
    return VerifiedCriterionEvidence(domain="documentation", criterion="release_rollback", repository=repository, assessed_commit=assessed_commit, verification_state="reviewed", source="source-verified-isolated-code-rollback:" + str(SOURCE_RUN) + "/" + str(ARTIFACT_ID) + ":" + artifact["digest"], evidence=("https://github.com/" + repository + "/actions/runs/" + current_id + "#sha=" + assessed_commit,), retained_receipt=receipt)
