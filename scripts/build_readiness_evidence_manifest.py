#!/usr/bin/env python3
"""Read-only, source-verified 19-criterion handoff, never an assessment writer.

Runs inside the existing trusted post-CI observer identity. Emits positive
claims only for checks whose exact run and jobs were fetched from GitHub.
Other dimensions remain missing/partial; no Supabase credential, LLM, model
cost, scheduler wake, Start, or deployment is used.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from ai_product_factory.existing_project_github_inventory import _get as github_read
from ai_product_factory.github_auth import resolve_github_token
from ai_product_factory.product_readiness_certification import (
    certify_product_readiness,
    conservative_verified_manifest,
)
from audit_global_readiness import resolve_observer_event, MAX_EVENT_BYTES


def build_verified_baseline(*, repository: str, sha: str, github_get) -> dict:
    manifest = conservative_verified_manifest(
        repository=repository, assessed_commit=sha, github_get=github_get
    )
    certification = certify_product_readiness(
        repository=repository, assessed_commit=sha,
        manifest=manifest, github_get=github_get,
    )
    statuses = [
        {"domain": domain, "criterion": key, "status": evidence["status"],
         "reason": evidence["reason"], "evidence": evidence["evidence"]}
        for domain, criteria in certification.report["criteria"].items()
        for key, evidence in criteria.items()
    ]
    if len(statuses) != 19 or certification.assessment.ready:
        raise ValueError("conservative baseline cannot certify the whole Factory")
    return {
        "schema_version": 1,
        "scope": "read_only_independent_source_verified_baseline",
        "assessed_commit": sha,
        "repository": repository,
        "evidence_digest": certification.evidence_digest,
        "source_snapshot": certification.report["source_snapshot"],
        "criteria": statuses,
        "manifest": manifest,
        "assessment": certification.assessment.as_result(),
        "writes": 0,
        "paid_calls": 0,
        "start_authorized": False,
        "product_ready": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only verified Factory readiness baseline")
    parser.add_argument("--event-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if (not args.event_path.is_file()
            or not 0 < args.event_path.stat().st_size <= MAX_EVENT_BYTES):
        raise SystemExit("UNVERIFIABLE_CERTIFICATION_EVENT")
    event = json.loads(args.event_path.read_text(encoding="utf-8"))
    sha, _, _ = resolve_observer_event(event, repo)
    token = resolve_github_token(repo)
    github_get = lambda path: github_read(token, path)
    report = build_verified_baseline(repository=repo, sha=sha, github_get=github_get)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "verified_not_ready",
        "assessed_commit": sha,
        "verified_criteria": sum(x["status"] == "passed" for x in report["criteria"]),
        "missing_or_partial_criteria": sum(x["status"] != "passed" for x in report["criteria"]),
        "writes": 0,
        "paid_calls": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
