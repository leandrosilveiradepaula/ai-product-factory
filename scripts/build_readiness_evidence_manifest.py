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
from ai_product_factory.native_v2_traceability_certification import (
    TraceabilityUnverified, verify_existing_crm_v2_traceability,
)
from ai_product_factory.independent_health_evidence import (
    HealthEvidenceBlocked, verify_health_for_certification,
)
from audit_global_readiness import resolve_observer_event, MAX_EVENT_BYTES


def build_verified_baseline(*, repository: str, sha: str, github_get,
                            verify_native_v2: bool = False,
                            verify_health: bool = False) -> dict:
    manifest = conservative_verified_manifest(
        repository=repository, assessed_commit=sha, github_get=github_get
    )
    proof = None
    if verify_native_v2:
        try:
            proof = verify_existing_crm_v2_traceability(
                repository=repository, assessed_commit=sha, github_get=github_get,
            )
        except (TraceabilityUnverified, ValueError, RuntimeError, OSError, KeyError,
                TypeError, UnicodeError):
            # Preserve existing exact-SHA unit/integration baseline; never
            # manufacture a positive traceability claim after failed source.
            proof = None
        if proof is not None:
            entry = manifest["criteria"]["observability_operations"]["traceability"]
            entry.update(
                status="passed",
                verification_state=proof.verification_state,
                reason="independent native V2 evidence reverified on current SHA",
                evidence=list(proof.evidence),
            )
    health_proof = None
    if verify_health:
        try:
            health_proof = verify_health_for_certification(
                repository=repository, assessed_commit=sha, github_get=github_get,
            )
        except (HealthEvidenceBlocked, ValueError, RuntimeError, OSError,
                KeyError, TypeError, UnicodeError):
            # Failure remains MISSING: no guessed deployment, no synthetic
            # scheduler events and no unverified data-driven PASS.
            health_proof = None
        if health_proof is not None:
            health = manifest["criteria"]["observability_operations"]["health"]
            health.update(
                status="passed", verification_state=health_proof.verification_state,
                reason="independent current-SHA live health attestation",
                evidence=list(health_proof.evidence),
            )
    def trusted(domain, criterion, snapshot):
        if (domain, criterion) == ("observability_operations", "traceability"):
            return proof
        if (domain, criterion) == ("observability_operations", "health"):
            return health_proof
        return None
    certification = certify_product_readiness(
        repository=repository, assessed_commit=sha,
        manifest=manifest, github_get=github_get,
        trusted_verifier=trusted if (proof is not None or health_proof is not None) else None,
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
    parser.add_argument("--verify-native-v2-traceability", action="store_true")
    parser.add_argument("--verify-independent-health", action="store_true")
    args = parser.parse_args(argv)
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if (not args.event_path.is_file()
            or not 0 < args.event_path.stat().st_size <= MAX_EVENT_BYTES):
        raise SystemExit("UNVERIFIABLE_CERTIFICATION_EVENT")
    event = json.loads(args.event_path.read_text(encoding="utf-8"))
    sha, _, _ = resolve_observer_event(event, repo)
    token = resolve_github_token(repo)
    github_get = lambda path: github_read(token, path)
    report = build_verified_baseline(
        repository=repo, sha=sha, github_get=github_get,
        verify_native_v2=args.verify_native_v2_traceability,
        verify_health=args.verify_independent_health,
    )
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
