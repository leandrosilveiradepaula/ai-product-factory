"""Independent bounded selection of a genuinely executed native scheduler source.

Never treat workflow_dispatch, an unverified job, or a changed executable blob
as a replacement for a native scheduled execution. Query GitHub afresh for the
assessed commit instead of pinning a historical run ID forever.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from collections.abc import Callable

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_WORKFLOW = ".github/workflows/autonomous-runner.yml"
_QUERY = "/actions/workflows/autonomous-runner.yml/runs?event=schedule&status=success&branch=main&per_page=50"


class NativeScheduleProofBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class NativeScheduleProof:
    run_id: int
    source_sha: str
    source_blobs: dict[str, tuple[str, str]]


def _require(cond: bool, code: str) -> None:
    if not cond:
        raise NativeScheduleProofBlocked(code)


def _blobs(tree: object, paths: frozenset[str]) -> dict[str, tuple[str, str]]:
    _require(isinstance(tree, dict) and tree.get("truncated") is False,
             "native_schedule_tree_unavailable")
    rows = tree.get("tree")
    _require(isinstance(rows, list) and 0 < len(rows) <= 20000,
             "native_schedule_tree_invalid")
    found = {}
    for row in rows:
        _require(isinstance(row, dict), "native_schedule_tree_entry_invalid")
        path = row.get("path")
        if path not in paths:
            continue
        sha, mode = row.get("sha"), row.get("mode")
        _require(row.get("type") == "blob" and isinstance(sha, str)
                 and _SHA.fullmatch(sha) is not None and isinstance(mode, str)
                 and path not in found, "native_schedule_blob_invalid")
        found[path] = (sha, mode)
    _require(set(found) == paths, "native_schedule_blobs_missing")
    return found


def select_native_schedule_proof(
    *, repository: str, assessed_commit: str,
    github_get: Callable[[str], object], source_files: frozenset[str],
    required_jobs: frozenset[str],
) -> NativeScheduleProof:
    _require(isinstance(repository, str) and repository.count("/") == 1
             and isinstance(assessed_commit, str)
             and _SHA.fullmatch(assessed_commit) is not None
             and isinstance(source_files, frozenset) and bool(source_files)
             and isinstance(required_jobs, frozenset) and bool(required_jobs),
             "native_schedule_identity_invalid")
    prefix = "/repos/" + repository
    data = github_get(prefix + _QUERY)
    _require(isinstance(data, dict), "native_schedule_list_unavailable")
    runs = data.get("workflow_runs")
    _require(isinstance(runs, list) and len(runs) <= 50,
             "native_schedule_list_invalid")
    main = github_get(prefix + "/git/ref/heads/main")
    _require(isinstance(main, dict)
             and isinstance(main.get("object"), dict)
             and main["object"].get("sha") == assessed_commit,
             "native_schedule_main_drift")
    target = _blobs(github_get(prefix + "/git/trees/" + assessed_commit + "?recursive=1"), source_files)
    visited = set()
    # At most 16 official schedule runs; no paid models, no dispatch, no writes.
    for candidate in runs[:16]:
        if not isinstance(candidate, dict):
            continue
        rid, sha = candidate.get("id"), candidate.get("head_sha")
        if type(rid) is not int or rid <= 0 or rid in visited:
            continue
        visited.add(rid)
        if not isinstance(sha, str) or _SHA.fullmatch(sha) is None:
            continue
        if (candidate.get("event") != "schedule"
            or candidate.get("status") != "completed"
            or candidate.get("conclusion") != "success"
            or candidate.get("head_branch") != "main"
            or candidate.get("run_attempt") != 1
            or candidate.get("path") != _WORKFLOW
            or candidate.get("name") != "Factory autonomous runner"
            or not isinstance(candidate.get("repository"), dict)
            or candidate["repository"].get("full_name") != repository):
            continue
        exact = github_get(prefix + "/actions/runs/" + str(rid))
        if not isinstance(exact, dict) or exact != candidate:
            # The list can omit incidental fields; enforce only trusted
            # immutable identity and outcome against a fresh run API read.
            if not isinstance(exact, dict) or any(exact.get(k) != candidate.get(k) for k in
                ("id", "head_sha", "event", "status", "conclusion", "head_branch", "run_attempt", "path", "name")):
                continue
            if not isinstance(exact.get("repository"), dict) or exact["repository"].get("full_name") != repository:
                continue
        jobs_obj = github_get(prefix + "/actions/runs/" + str(rid) + "/jobs?per_page=100")
        jobs = jobs_obj.get("jobs") if isinstance(jobs_obj, dict) else None
        _require(isinstance(jobs, list) and 0 < len(jobs) <= 100, "native_schedule_jobs_invalid")
        successful = {j.get("name") for j in jobs if isinstance(j, dict)
                      and j.get("run_id") == rid and j.get("head_sha") == sha
                      and j.get("status") == "completed" and j.get("conclusion") == "success"}
        if not required_jobs.issubset(successful):
            continue
        compare = github_get(prefix + "/compare/" + sha + "..." + assessed_commit)
        if not (isinstance(compare, dict)
                and compare.get("status") in {"ahead", "identical"}
                and compare.get("behind_by") == 0
                and isinstance(compare.get("merge_base_commit"), dict)
                and compare["merge_base_commit"].get("sha") == sha):
            continue
        blobs = _blobs(github_get(prefix + "/git/trees/" + sha + "?recursive=1"), source_files)
        if blobs != target:
            continue
        return NativeScheduleProof(rid, sha, blobs)
    raise NativeScheduleProofBlocked("no_matching_native_schedule_proof")
