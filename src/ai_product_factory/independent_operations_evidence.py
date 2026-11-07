"""Source-bound evidence that the current operational runbooks match a real run.

This verifies a bounded documentation criterion only.  It does not claim a
production recovery, a release, or any other readiness domain.
"""
from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping

from .product_readiness_certification import VerifiedCriterionEvidence

REPOSITORY = "leandrosilveiradepaula/ai-product-factory"
OWNER_WORKFLOW = ".github/workflows/autonomous-runner.yml"
SOURCE_RUN = 42392345319
SOURCE_SHA = "c62297b7538ba9479aabd8f870ffd9eb142187ca"
REQUIRED_JOBS = frozenset({"schedule-probe", "alerts"})
SOURCE_FILES = frozenset({
    "docs/OPERATIONS.md", "docs/RELEASE_AUTONOMY.md",
    "docs/FINALIZATION_EXECUTION_CONTRACT.md",
    "src/ai_product_factory/runtime_cli.py",
    "src/ai_product_factory/operational_alerts.py",
    "src/ai_product_factory/external_webhook_recovery.py",
    "src/ai_product_factory/supabase_scheduler_liveness.py",
})
SHA = re.compile(r"[0-9a-f]{40}\Z")


class OperationsEvidenceBlocked(RuntimeError):
    pass


def _require(value: bool, code: str) -> None:
    if not value:
        raise OperationsEvidenceBlocked(code)


def _blobs(tree: object) -> dict[str, tuple[str, str]]:
    _require(isinstance(tree, dict) and tree.get("truncated") is False,
             "operations_tree_unavailable")
    rows = tree.get("tree")
    _require(isinstance(rows, list) and 0 < len(rows) <= 20_000,
             "operations_tree_invalid")
    found: dict[str, tuple[str, str]] = {}
    for row in rows:
        _require(isinstance(row, dict), "operations_tree_entry_invalid")
        path = row.get("path")
        if path not in SOURCE_FILES:
            continue
        blob, mode = row.get("sha"), row.get("mode")
        _require(row.get("type") == "blob" and isinstance(blob, str)
                 and SHA.fullmatch(blob) is not None and isinstance(mode, str)
                 and path not in found, "operations_source_blob_invalid")
        found[path] = (blob, mode)
    _require(set(found) == SOURCE_FILES, "operations_source_blob_missing")
    return found


def _upstream(event: Mapping[str, object], assessed_commit: str) -> int:
    run = event.get("workflow_run")
    _require(isinstance(run, dict) and run.get("name") == "validate"
             and run.get("path") == ".github/workflows/validate.yml"
             and run.get("event") == "push" and run.get("status") == "completed"
             and run.get("conclusion") == "success"
             and run.get("head_sha") == assessed_commit
             and run.get("head_branch") == "main" and run.get("run_attempt") == 1
             and isinstance(run.get("repository"), dict)
             and run["repository"].get("full_name") == REPOSITORY,
             "operations_upstream_validate_invalid")
    run_id = run.get("id")
    _require(type(run_id) is int and run_id > 0, "operations_upstream_run_invalid")
    return run_id


def verify_operations_runbook(*, repository: str, assessed_commit: str,
                              github_get: Callable[[str], object],
                              environment: Mapping[str, str] | None = None,
                              event_payload: Mapping[str, object] | None = None) -> VerifiedCriterionEvidence:
    env = os.environ if environment is None else environment
    _require(repository == REPOSITORY and isinstance(assessed_commit, str)
             and SHA.fullmatch(assessed_commit) is not None,
             "operations_repository_or_sha_invalid")
    _require(env.get("GITHUB_ACTIONS") == "true"
             and env.get("GITHUB_REPOSITORY") == REPOSITORY
             and env.get("GITHUB_EVENT_NAME") == "workflow_run"
             and env.get("GITHUB_REF") == "refs/heads/main"
             and env.get("GITHUB_WORKFLOW_REF") == REPOSITORY + "/" + OWNER_WORKFLOW + "@refs/heads/main"
             and str(env.get("GITHUB_RUN_ID", "")).isdecimal(),
             "operations_certifier_identity_invalid")
    if event_payload is None:
        import json
        from pathlib import Path
        event_path = env.get("GITHUB_EVENT_PATH", "")
        _require(bool(event_path), "operations_event_path_missing")
        event_payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
    _require(isinstance(event_payload, Mapping), "operations_event_payload_invalid")
    upstream_id = _upstream(event_payload, assessed_commit)
    prefix = "/repos/" + REPOSITORY
    current_id = int(env["GITHUB_RUN_ID"])
    current = github_get(prefix + "/actions/runs/" + str(current_id))
    _require(isinstance(current, dict) and current.get("id") == current_id
             and current.get("name") == "Factory autonomous runner"
             and current.get("path") == OWNER_WORKFLOW and current.get("event") == "workflow_run"
             and current.get("head_sha") == assessed_commit and current.get("head_branch") == "main"
             and current.get("run_attempt") == 1 and current.get("status") in {"queued", "in_progress", "completed"}
             and (current.get("status") != "completed" or current.get("conclusion") == "success"),
             "operations_certifier_run_unbound")
    source = github_get(prefix + "/actions/runs/" + str(SOURCE_RUN))
    _require(isinstance(source, dict) and source.get("id") == SOURCE_RUN
             and source.get("name") == "Factory autonomous runner" and source.get("path") == OWNER_WORKFLOW
             and source.get("event") == "schedule" and source.get("head_sha") == SOURCE_SHA
             and source.get("head_branch") == "main" and source.get("status") == "completed"
             and source.get("conclusion") == "success" and source.get("run_attempt") == 1
             and isinstance(source.get("repository"), dict) and source["repository"].get("full_name") == REPOSITORY,
             "operations_source_run_invalid")
    jobs = github_get(prefix + "/actions/runs/" + str(SOURCE_RUN) + "/jobs?per_page=100")
    rows = jobs.get("jobs") if isinstance(jobs, dict) else None
    _require(isinstance(rows, list) and 0 < len(rows) <= 100, "operations_source_jobs_invalid")
    successful = {row.get("name") for row in rows if isinstance(row, dict)
                  and row.get("run_id") == SOURCE_RUN and row.get("head_sha") == SOURCE_SHA
                  and row.get("status") == "completed" and row.get("conclusion") == "success"}
    _require(REQUIRED_JOBS.issubset(successful), "operations_source_jobs_missing")
    compare = github_get(prefix + "/compare/" + SOURCE_SHA + "..." + assessed_commit)
    _require(isinstance(compare, dict) and compare.get("status") in {"ahead", "identical"}
             and compare.get("behind_by") == 0 and isinstance(compare.get("merge_base_commit"), dict)
             and compare["merge_base_commit"].get("sha") == SOURCE_SHA,
             "operations_source_not_ancestor")
    source_blobs = _blobs(github_get(prefix + "/git/trees/" + SOURCE_SHA + "?recursive=1"))
    assessed_blobs = _blobs(github_get(prefix + "/git/trees/" + assessed_commit + "?recursive=1"))
    _require(source_blobs == assessed_blobs, "operations_runbook_or_command_drift")
    latest = github_get(prefix + "/git/ref/heads/main")
    _require(isinstance(latest, dict) and isinstance(latest.get("object"), dict)
             and latest["object"].get("sha") == assessed_commit, "operations_main_drift")
    return VerifiedCriterionEvidence(
        domain="documentation", criterion="operations", repository=repository,
        assessed_commit=assessed_commit, verification_state="reviewed",
        source="github-native-scheduled-operations-runbook:" + str(SOURCE_RUN),
        evidence=("https://github.com/" + repository + "/actions/runs/" + str(current_id) + "#sha=" + assessed_commit,),
        retained_receipt={"source_run_id": SOURCE_RUN, "source_sha": SOURCE_SHA,
                          "source_jobs": sorted(REQUIRED_JOBS), "upstream_validate_run_id": upstream_id,
                          "source_blobs": {k: list(v) for k, v in sorted(source_blobs.items())},
                          "assessed_commit": assessed_commit},
    )
