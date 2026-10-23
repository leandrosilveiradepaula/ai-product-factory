"""Bounded GitHub Actions failed-job evidence for the autonomous CI repair lane.

Only exact run/attempt/commit job metadata is admissible. This module never
reads logs, learns patches, dispatches CI or grants write scopes. Unknown
and mixed failures remain non-code and cannot trigger speculative edits.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_SHA = re.compile(r"[0-9a-f]{40}")
_CODE_STEPS = {
    "tests": "tests",
    "unit tests": "unit-tests",
    "integration tests": "integration-tests",
    "pytest": "pytest",
    "npm test": "npm-test",
    "typescript": "typescript",
    "typecheck": "typecheck",
    "type check": "typecheck",
    "lint": "lint",
    "new lint errors": "lint",
    "build": "build",
    "compile": "compile",
    "test collection guard": "test-collection",
    "dependency audit regression guard": "dependency-audit",
}
_MAX_JOBS = 100
_MAX_STEPS = 80
_MAX_FAILURES = 20


@dataclass(frozen=True)
class NativeJobFailure:
    name: str
    failure_class: str
    details_url: str
    summary: str


def parse_failed_native_job_steps(
    payload: object, *, repository: str, run_id: int,
    run_attempt: int, candidate_sha: str,
) -> tuple[NativeJobFailure, ...] | None:
    """Fail closed on incomplete provenance; None means no job-level proof.

    The caller must fetch /actions/runs/{id}/attempts/{attempt}/jobs, never
    mix the latest job from a different retry or another commit.
    """
    if (not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
        or type(run_id) is not int or run_id < 1
        or type(run_attempt) is not int or run_attempt < 1
        or not isinstance(candidate_sha, str) or not _SHA.fullmatch(candidate_sha)):
        raise ValueError("invalid native CI job provenance inputs")
    if not isinstance(payload, dict):
        raise RuntimeError("native CI job evidence must be an object")
    jobs = payload.get("jobs")
    count = payload.get("total_count")
    if (not isinstance(jobs, list) or type(count) is not int
        or count < 0 or count > _MAX_JOBS or len(jobs) != count):
        raise RuntimeError("native CI job inventory is truncated or unbounded")
    if not jobs:
        return None

    failures: list[NativeJobFailure] = []
    seen: set[int] = set()
    for job in jobs:
        if not isinstance(job, dict):
            raise RuntimeError("native CI job entry is malformed")
        job_id = job.get("id")
        if job_id in seen:
            raise RuntimeError("native CI job inventory contains duplicate ID")
        if (type(job_id) is not int or job_id <= 0
            or job.get("run_id") != run_id
            or job.get("run_attempt") != run_attempt
            or job.get("head_sha") != candidate_sha
            or job.get("status") != "completed"):
            raise RuntimeError("native CI job identity, SHA or attempt mismatch")
        seen.add(job_id)
        conclusion = job.get("conclusion")
        if conclusion in ("success", "neutral", "skipped"):
            continue
        if conclusion not in ("failure", "timed_out", "cancelled", "action_required", "startup_failure"):
            raise RuntimeError("native CI job has invalid conclusion")
        raw_steps = job.get("steps")
        if not isinstance(raw_steps, list) or len(raw_steps) > _MAX_STEPS:
            raise RuntimeError("native CI job steps are missing or unbounded")
        failing_steps = [step for step in raw_steps
                         if isinstance(step, dict) and step.get("conclusion") == "failure"]
        if any(not isinstance(step, dict) for step in raw_steps):
            raise RuntimeError("native CI job has malformed step entries")
        if conclusion != "failure" or not failing_steps:
            failing_steps = [{"name": None, "status": "completed", "conclusion": "failure"}]
        for step in failing_steps:
            if step.get("status") != "completed":
                raise RuntimeError("native CI failed step is not completed")
            name = step.get("name")
            normalized = " ".join(name.lower().split()) if isinstance(name, str) and len(name) <= 120 else ""
            category = _CODE_STEPS.get(normalized)
            # Use only enumerated, non-sensitive step names in durable records.
            step_name = category or "unclassified"
            failures.append(NativeJobFailure(
                name="native-ci/" + step_name,
                failure_class="code" if category is not None else "unknown",
                details_url=f"https://github.com/{repository}/actions/runs/{run_id}/job/{job_id}",
                summary="Verified failed GitHub Actions step (run and attempt bound)",
            ))
            if len(failures) > _MAX_FAILURES:
                raise RuntimeError("native CI failure evidence exceeds bounded repair scope")
    # GitHub workflow failure without a failed job cannot certify the cause.
    return tuple(failures) if failures else None
