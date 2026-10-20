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
    REPO, SHA, observe_current_product,
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    output = {"status":"blocked","reason_code":"unverifiable_global_readiness_evidence",
              "product_ready":False,"paid_calls":0,"writes":0}
    code = 2
    try:
        repository = os.environ.get("GITHUB_REPOSITORY","")
        if not isinstance(repository,str) or REPO.fullmatch(repository) is None:
            raise ValueError("invalid workflow repository")
        if (not args.event_path.is_file()
                or args.event_path.stat().st_size > MAX_EVENT_BYTES):
            raise ValueError("event missing or too large")
        event = json.loads(args.event_path.read_text(encoding="utf-8"))
        sha, run_id = validate_event(event,repository)
        token = resolve_github_token(repository)
        reader = SupabaseAdmissionReader()
        report = observe_current_product(
            repository=repository,sha=sha,validation_run_id=run_id,
            github_get=lambda path: github_read(token,path),
            cp_get=reader._get,
        )
        output = report
        output["status"] = "observed"
        output["product_ready"] = report["global_readiness"]["product_ready"]
        code = 0
    except (ValueError, TypeError, RuntimeError, KeyError, OSError,
            UnicodeError, json.JSONDecodeError):
        # Do not print HTTP responses, JWTs, model prompts, private repository
        # content or error messages from the remote API. Failure is fail closed.
        pass
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
