#!/usr/bin/env python3
"""Trusted post-CI global readiness observation, never a scheduler/model."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from ai_product_factory.existing_project_github_inventory import _get as github_read
from ai_product_factory.github_auth import resolve_github_token
from ai_product_factory.global_readiness_evidence import (
    REPO, SHA, observe_current_product, find_current_validation_run,
)
from ai_product_factory.admission_diagnostics import SupabaseAdmissionReader

MAX_EVENT_BYTES = 256 * 1024


def validate_event(event: object, repository: str) -> tuple[str, int]:
    if not isinstance(event, dict):
        raise ValueError("invalid event")
    job = event.get("workflow_run")
    repo = event.get("repository")
    if not isinstance(job, dict) or not isinstance(repo, dict):
        raise ValueError("missing CI event provenance")
    sha = job.get("head_sha")
    run_id = job.get("id")
    if (repo.get("full_name") != repository or not isinstance(sha,str)
            or SHA.fullmatch(sha) is None
            or type(run_id) is not int or run_id < 1
            or job.get("name") != "validate" or job.get("event") != "push"
            or job.get("head_branch") != repo.get("default_branch")
            or job.get("conclusion") != "success" or job.get("status") != "completed"):
        raise ValueError("not an approved exact-HEAD validation event")
    return sha, run_id



def resolve_observer_event(event: object, repository: str) -> tuple[str,int,str]:
    """Only exact main-push CI or completed authenticated visual may observe."""
    if not isinstance(event,dict) or not isinstance(event.get("workflow_run"),dict):
        raise ValueError("missing workflow_run event")
    if not isinstance(event.get("repository"),dict):
        raise ValueError("missing repository identity")
    run = event["workflow_run"]
    if run.get("name") == "validate":
        sha,run_id = validate_event(event,repository)
        return sha,run_id,"validate"
    repo = event["repository"]
    if (run.get("name") != "Authenticated Console visual evidence"
            or run.get("event") != "push" or run.get("status") != "completed"
            or run.get("conclusion") not in ("success","failure")
            or repo.get("full_name") != repository
            or run.get("head_branch") != repo.get("default_branch")
            or not isinstance(run.get("head_sha"),str)
            or SHA.fullmatch(run["head_sha"]) is None
            or type(run.get("id")) is not int or run["id"] <= 0):
        raise ValueError("not an approved exact-HEAD visual event")
    return run["head_sha"],run["id"],"visual"

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    output = {"status":"blocked","reason_code":"unverifiable_global_readiness_evidence",
              "product_ready":False,"paid_calls":0,"writes":0}
    code = 2
    phase = "event"
    try:
        repository = os.environ.get("GITHUB_REPOSITORY","")
        if not isinstance(repository,str) or REPO.fullmatch(repository) is None:
            raise ValueError("invalid workflow repository")
        if (not args.event_path.is_file()
                or args.event_path.stat().st_size > MAX_EVENT_BYTES):
            raise ValueError("event missing or too large")
        event = json.loads(args.event_path.read_text(encoding="utf-8"))
        sha, source_run_id, source_workflow = resolve_observer_event(event,repository)
        phase = "github_token"
        token = resolve_github_token(repository)
        gh_get = lambda path: github_read(token,path)
        validation_run_id = source_run_id
        if source_workflow == "visual":
            phase = "validation_identity"
            validation_run_id = find_current_validation_run(
                repository=repository,sha=sha,
                branch=event["repository"]["default_branch"],github_get=gh_get,
            )
        phase = "control_plane_access"
        reader = SupabaseAdmissionReader()
        phase = "evidence_collection"
        report = observe_current_product(
            repository=repository,sha=sha,validation_run_id=validation_run_id,
            github_get=gh_get,cp_get=reader._get,
            visual_trigger_run_id=source_run_id if source_workflow == "visual" else None,
        )
        output = report
        output["observation_trigger"] = "visual_completed" if source_workflow == "visual" else "ci_completed"
        output["source_workflow_run_id"] = source_run_id
        output["status"] = "observed"
        output["product_ready"] = report["global_readiness"]["product_ready"]
        code = 0
    except (ValueError, TypeError, RuntimeError, KeyError, OSError,
            UnicodeError, json.JSONDecodeError) as exc:
        # Fixed diagnostic vocabulary: no HTTP body, token, private source,
        # prompt or arbitrary exception message can enter the artifact.
        output["reason_code"] = {
            "event":"invalid_or_stale_workflow_event",
            "github_token":"github_read_credential_unavailable",
            "validation_identity":"matching_validate_run_unavailable",
            "control_plane_access":"control_plane_oidc_unavailable",
            "evidence_collection":"exact_head_or_control_plane_evidence_unavailable",
        }[phase]
        output["error_class"] = type(exc).__name__ if type(exc).__name__ in {
            "ValueError","TypeError","RuntimeError","KeyError","OSError",
            "JSONDecodeError","UnicodeDecodeError","GlobalReadinessEvidenceError",
            "BaselineInventoryError","PermissionError","HTTPError","URLError",
        } else "unexpected_error"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":output["status"],
        "product_ready":output["product_ready"],
        "source_sha":output.get("assessed_commit"),
        "unverified_domains":len(output.get("global_readiness",{}).get("missing_or_unverified_domains",[])),
        "writes":0,"paid_calls":0,
    },sort_keys=True))
    return code


if __name__=="__main__":
    sys.exit(main())
