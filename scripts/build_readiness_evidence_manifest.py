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
from ai_product_factory.independent_setup_evidence import (
    SetupEvidenceBlocked, verify_existing_clean_setup,
)
from ai_product_factory.independent_rollback_evidence import (
    RollbackEvidenceBlocked, verify_existing_isolated_rollback,
)
from ai_product_factory.independent_security_evidence import (
    SecurityEvidenceBlocked, verify_existing_secrets_dependencies,
)
from audit_global_readiness import resolve_observer_event, MAX_EVENT_BYTES


def build_verified_baseline(*, repository: str, sha: str, github_get,
                            verify_native_v2: bool = False,
                            verify_health: bool = False,
                            verify_setup: bool = False,
                            verify_rollback: bool = False,
                            verify_secrets_dependencies: bool = False) -> dict:
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
    setup_proof = None
    if verify_setup:
        try:
            setup_proof = verify_existing_clean_setup(
                repository=repository, assessed_commit=sha, github_get=github_get,
            )
        except (SetupEvidenceBlocked, ValueError, RuntimeError, OSError,
                KeyError, TypeError, UnicodeError):
            # Missing or stale artifact is not a passing documentation review.
            setup_proof = None
        if setup_proof is not None:
            setup = manifest["criteria"]["documentation"]["setup_configuration"]
            setup.update(
                status="passed", verification_state=setup_proof.verification_state,
                reason="independent credential-free README setup reverified on current SHA",
                evidence=list(setup_proof.evidence),
            )
    rollback_proof = None
    if verify_rollback:
        try:
            rollback_proof = verify_existing_isolated_rollback(
                repository=repository, assessed_commit=sha, github_get=github_get,
            )
        except (RollbackEvidenceBlocked, ValueError, RuntimeError, OSError,
                KeyError, TypeError, UnicodeError):
            rollback_proof = None
        if rollback_proof is not None:
            rollback = manifest["criteria"]["documentation"]["release_rollback"]
            rollback.update(status="passed", verification_state=rollback_proof.verification_state,
                            reason="independent isolated code rollback and human gate reverified",
                            evidence=list(rollback_proof.evidence))
    security_proof = None
    if verify_secrets_dependencies:
        try:
            security_proof = verify_existing_secrets_dependencies(
                repository=repository, assessed_commit=sha, github_get=github_get,
            )
        except (SecurityEvidenceBlocked, ValueError, RuntimeError, OSError,
                KeyError, TypeError, UnicodeError):
            security_proof = None
        if security_proof is not None:
            entry = manifest["criteria"]["security"]["secrets_dependencies"]
            entry.update(status="passed", verification_state=security_proof.verification_state,
                         reason="independent full-tree Gitleaks and production dependency audit reverified",
                         evidence=list(security_proof.evidence))
    def trusted(domain, criterion, snapshot):
        if (domain, criterion) == ("observability_operations", "traceability"):
            return proof
        if (domain, criterion) == ("observability_operations", "health"):
            return health_proof
        if (domain, criterion) == ("documentation", "setup_configuration"):
            return setup_proof
        if (domain, criterion) == ("documentation", "release_rollback"):
            return rollback_proof
        if (domain, criterion) == ("security", "secrets_dependencies"):
            return security_proof
        return None
    certification = certify_product_readiness(
        repository=repository, assessed_commit=sha,
        manifest=manifest, github_get=github_get,
        trusted_verifier=trusted if any(x is not None for x in
            (proof, health_proof, setup_proof, rollback_proof, security_proof)) else None,
    )
    statuses = [
        {"domain": domain, "criterion": key, "status": evidence["status"],
         "reason": evidence["reason"], "evidence": evidence["evidence"]}
        for domain, criteria in certification.report["criteria"].items()
        for key, evidence in criteria.items()
    ]
    if len(statuses) != 19:
        raise ValueError("verified baseline requires exactly 19 criteria")
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
        "product_ready": certification.assessment.ready,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only verified Factory readiness baseline")
    parser.add_argument("--event-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-native-v2-traceability", action="store_true")
    parser.add_argument("--verify-independent-health", action="store_true")
    parser.add_argument("--verify-independent-setup", action="store_true")
    parser.add_argument("--verify-isolated-rollback", action="store_true")
    parser.add_argument("--verify-secrets-dependencies", action="store_true")
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
        verify_setup=args.verify_independent_setup,
        verify_rollback=args.verify_isolated_rollback,
        verify_secrets_dependencies=args.verify_secrets_dependencies,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["assessment"]["status"],
        "assessed_commit": sha,
        "verified_criteria": sum(x["status"] == "passed" for x in report["criteria"]),
        "missing_or_partial_criteria": sum(x["status"] != "passed" for x in report["criteria"]),
        "writes": 0,
        "paid_calls": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
