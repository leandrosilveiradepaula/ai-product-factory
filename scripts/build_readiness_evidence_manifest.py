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
import re
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
from ai_product_factory.independent_regression_evidence import (
    RegressionEvidenceBlocked, verify_regression_gates as verify_effective_regression_gates,
)
from ai_product_factory.independent_recovery_evidence import (
    RecoveryEvidenceBlocked, verify_recovery_alerting as verify_recovery_alerting_fn,
)
from ai_product_factory.independent_operations_evidence import (
    OperationsEvidenceBlocked, verify_operations_runbook as verify_operations_runbook_fn,
)
from ai_product_factory.independent_authenticated_console_evidence import (
    AuthenticatedConsoleEvidenceBlocked, verify_authenticated_console_evidence,
    verify_reusable_historical_authenticated_console_evidence,
)
from ai_product_factory.admission_diagnostics import SupabaseAdmissionReader
from trace_block1_requirements import (
    RequirementsInventoryBlocked, verify_requirements_inventory as verify_requirements_inventory_fn,
)
from inventory_block1_simulation_paths import inventory as scan_simulation_sources
from audit_block1_mock_runtime_reachability import audit as audit_simulation_reachability
from audit_global_readiness import resolve_observer_event, MAX_EVENT_BYTES


def build_verified_baseline(*, repository: str, sha: str, github_get,
                            verify_native_v2: bool = False,
                            verify_health: bool = False,
                            verify_setup: bool = False,
                            verify_rollback: bool = False,
                            verify_secrets_dependencies: bool = False,
                            verify_regression_gates: bool = False,
                            verify_recovery_alerting: bool = False,
                            verify_operations_runbook: bool = False,
                            verify_requirements_inventory: bool = False,
                            verify_static_simulation_inventory: bool = False,
                            authenticated_console_run_id: int | None = None,
                            reuse_historical_authenticated_console_evidence: bool = False,
                            control_plane_get=None) -> dict:
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
    health_blocker = None
    if verify_health:
        try:
            health_proof = verify_health_for_certification(
                repository=repository, assessed_commit=sha, github_get=github_get,
            )
        except HealthEvidenceBlocked as exc:
            # The verifier exposes only fixed internal error codes; never
            # record URLs, provider payloads or credentials in the receipt.
            code = str(exc)
            health_blocker = (code if re.fullmatch(r"health_[a-z0-9_]{1,96}", code)
                              else "health_evidence_source_unavailable")
        except (ValueError, RuntimeError, OSError, KeyError, TypeError, UnicodeError):
            health_blocker = "health_evidence_source_unavailable"
        if health_proof is not None:
            health = manifest["criteria"]["observability_operations"]["health"]
            health.update(
                status="passed", verification_state=health_proof.verification_state,
                reason="independent current-SHA live health attestation",
                evidence=list(health_proof.evidence),
            )
        elif health_blocker is not None:
            manifest["criteria"]["observability_operations"]["health"].update(
                status="missing",
                reason="independent operational health evidence blocked: " + health_blocker,
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
    regression_proof = None
    regression_blocker = None
    if verify_regression_gates:
        try:
            regression_proof = verify_effective_regression_gates(
                repository=repository, assessed_commit=sha, github_get=github_get,
            )
        except RegressionEvidenceBlocked as exc:
            # The verifier emits bounded internal error codes. Preserve only
            # valid codes, never provider response bodies or secrets.
            code = str(exc)
            regression_blocker = (code if len(code) <= 100 and code.startswith("regression_")
                                  and all(ch.isascii() and (ch.islower() or ch.isdigit() or ch == "_") for ch in code)
                                  else "regression_evidence_source_unavailable")
        except (ValueError, RuntimeError, OSError, KeyError, TypeError, UnicodeError):
            regression_blocker = "regression_evidence_source_unavailable"
        if regression_proof is not None:
            entry = manifest["criteria"]["test_strategy"]["regression_gates"]
            entry.update(status="passed", verification_state=regression_proof.verification_state,
                         reason="independent effective GitHub regression gates reverified",
                         evidence=list(regression_proof.evidence))
        elif regression_blocker is not None:
            entry = manifest["criteria"]["test_strategy"]["regression_gates"]
            entry.update(status="partial",
                         reason="independent regression gate evidence blocked: " + regression_blocker)
    recovery_proof = None
    if verify_recovery_alerting:
        try:
            recovery_proof = verify_recovery_alerting_fn(
                repository=repository, assessed_commit=sha, github_get=github_get,
            )
        except (RecoveryEvidenceBlocked, ValueError, RuntimeError, OSError,
                KeyError, TypeError, UnicodeError):
            recovery_proof = None
        if recovery_proof is not None:
            entry = manifest["criteria"]["observability_operations"]["recovery_alerting"]
            entry.update(status="passed", verification_state=recovery_proof.verification_state,
                         reason="independent source-bound native recovery and alerting reverified",
                         evidence=list(recovery_proof.evidence))
    operations_proof = None
    if verify_operations_runbook:
        try:
            operations_proof = verify_operations_runbook_fn(
                repository=repository, assessed_commit=sha, github_get=github_get,
            )
        except (OperationsEvidenceBlocked, ValueError, RuntimeError, OSError,
                KeyError, TypeError, UnicodeError):
            operations_proof = None
        if operations_proof is not None:
            entry = manifest["criteria"]["documentation"]["operations"]
            entry.update(status="passed", verification_state=operations_proof.verification_state,
                         reason="independent source-bound scheduled operations and runbooks reverified",
                         evidence=list(operations_proof.evidence))
    authenticated_console_proof = None
    authenticated_console_blocker = None
    if authenticated_console_run_id is not None:
        try:
            authenticated_console_proof = verify_authenticated_console_evidence(
                repository=repository, assessed_commit=sha,
                workflow_run_id=authenticated_console_run_id, github_get=github_get,
            )
        except AuthenticatedConsoleEvidenceBlocked as exc:
            authenticated_console_blocker = "authenticated Console evidence blocked: " + str(exc)
        except (ValueError, RuntimeError, OSError, KeyError, TypeError, UnicodeError):
            # Do not expose HTTP error bodies, broker tokens or provider data.
            authenticated_console_blocker = "authenticated Console evidence source unavailable"
    elif reuse_historical_authenticated_console_evidence:
        try:
            if control_plane_get is None:
                raise AuthenticatedConsoleEvidenceBlocked("Control Plane reader unavailable")
            authenticated_console_proof = verify_reusable_historical_authenticated_console_evidence(
                repository=repository, assessed_commit=sha, github_get=github_get,
                control_plane_get=control_plane_get,
            )
        except AuthenticatedConsoleEvidenceBlocked as exc:
            authenticated_console_blocker = "authenticated Console evidence blocked: " + str(exc)
        except (ValueError, RuntimeError, OSError, KeyError, TypeError, UnicodeError):
            authenticated_console_blocker = "authenticated Console evidence source unavailable"
    if authenticated_console_proof is not None:
        for criterion in ("surface_inventory", "responsive", "accessibility"):
            entry = manifest["criteria"]["product_experience"][criterion]
            entry.update(
                status="partial", verification_state="observed",
                reason="authenticated Console metadata verifies a bounded browser capture; full criterion review remains required",
                evidence=list(authenticated_console_proof.evidence),
            )
    elif authenticated_console_blocker is not None:
        # Explicitly retain a bounded blocker, never a positive evidence claim.
        for criterion in ("surface_inventory", "responsive", "accessibility"):
            manifest["criteria"]["product_experience"][criterion]["reason"] = authenticated_console_blocker

    # Source scan is deliberately BOUNDED: full Python marker inventory and
    # static runtime_cli closure, not dynamic reachability of every entrypoint.
    # It may add partial information but cannot approve the criterion.
    if verify_static_simulation_inventory:
        try:
            source_inventory = scan_simulation_sources(Path.cwd())
            reachable = audit_simulation_reachability(Path.cwd())
            if (source_inventory["source_files"] > 0
                    and source_inventory["writes_to_production"] == 0
                    and source_inventory["paid_calls"] == 0
                    and reachable["reachable_modules"]
                    and reachable["independent_pass"] is False):
                entry = manifest["criteria"]["functional_completeness"]["mock_noop_demo_inventory"]
                entry.update(
                    status="partial", verification_state="reviewed",
                    reason=("full Python source marker inventory and static runtime_cli closure only; "
                            + ("unclassified static markers remain; " if reachable["unclassified_runtime_markers"] else "")
                            + "dynamic production entrypoints remain unverified"),
                    evidence=["https://github.com/" + repository + "/actions/runs/"
                              + str(manifest["source_snapshot"]["validation_run_id"]) + "#sha=" + sha],
                )
        except (ValueError, SyntaxError, OSError, KeyError, TypeError, UnicodeError):
            manifest["criteria"]["functional_completeness"]["mock_noop_demo_inventory"]["reason"] = (
                "simulation source inventory unavailable or unclassified"
            )
    requirements_proof = None
    if verify_requirements_inventory:
        try:
            requirements_proof = verify_requirements_inventory_fn(
                repository=repository, assessed_commit=sha, github_get=github_get,
                criteria=manifest["criteria"],
            )
        except RequirementsInventoryBlocked as exc:
            code = str(exc)
            safe = (code if re.fullmatch(r"requirements_[a-z0-9_]{1,96}", code)
                    else "requirements_source_unavailable")
            manifest["criteria"]["functional_completeness"]["requirements_inventory"]["reason"] = (
                "independent requirements inventory blocked: " + safe
            )
        except (ValueError, RuntimeError, OSError, KeyError, TypeError, UnicodeError):
            manifest["criteria"]["functional_completeness"]["requirements_inventory"]["reason"] = (
                "independent requirements inventory source unavailable"
            )
        if requirements_proof is not None:
            item = manifest["criteria"]["functional_completeness"]["requirements_inventory"]
            item.update(status="passed", verification_state="reviewed",
                        reason="independently mapped 19 acceptance criteria, lifecycle stages and current gaps on exact Git tree",
                        evidence=list(requirements_proof.evidence))

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
        if (domain, criterion) == ("test_strategy", "regression_gates"):
            return regression_proof
        if (domain, criterion) == ("observability_operations", "recovery_alerting"):
            return recovery_proof
        if (domain, criterion) == ("documentation", "operations"):
            return operations_proof
        if (domain, criterion) == ("functional_completeness", "requirements_inventory"):
            return requirements_proof
        return None
    certification = certify_product_readiness(
        repository=repository, assessed_commit=sha,
        manifest=manifest, github_get=github_get,
        trusted_verifier=trusted if any(x is not None for x in
            (proof, health_proof, setup_proof, rollback_proof, security_proof, regression_proof, recovery_proof, operations_proof, requirements_proof)) else None,
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
        **({"authenticated_console_evidence": authenticated_console_proof.receipt()}
           if authenticated_console_proof is not None else {}),
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
    parser.add_argument("--verify-regression-gates", action="store_true")
    parser.add_argument("--verify-recovery-alerting", action="store_true")
    parser.add_argument("--verify-operations-runbook", action="store_true")
    parser.add_argument("--verify-requirements-inventory", action="store_true")
    parser.add_argument("--verify-static-simulation-inventory", action="store_true")
    parser.add_argument("--authenticated-console-run-id", type=int)
    parser.add_argument("--reuse-historical-authenticated-console-evidence", action="store_true")
    args = parser.parse_args(argv)
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if (not args.event_path.is_file()
            or not 0 < args.event_path.stat().st_size <= MAX_EVENT_BYTES):
        raise SystemExit("UNVERIFIABLE_CERTIFICATION_EVENT")
    event = json.loads(args.event_path.read_text(encoding="utf-8"))
    sha, _, _ = resolve_observer_event(event, repo)
    token = resolve_github_token(repo)
    github_get = lambda path: github_read(token, path)
    control_plane_get = (SupabaseAdmissionReader()._get
                         if args.reuse_historical_authenticated_console_evidence else None)
    report = build_verified_baseline(
        repository=repo, sha=sha, github_get=github_get,
        verify_native_v2=args.verify_native_v2_traceability,
        verify_health=args.verify_independent_health,
        verify_setup=args.verify_independent_setup,
        verify_rollback=args.verify_isolated_rollback,
        verify_secrets_dependencies=args.verify_secrets_dependencies,
        verify_regression_gates=args.verify_regression_gates,
        verify_recovery_alerting=args.verify_recovery_alerting,
        verify_operations_runbook=args.verify_operations_runbook,
        verify_requirements_inventory=args.verify_requirements_inventory,
        verify_static_simulation_inventory=args.verify_static_simulation_inventory,
        authenticated_console_run_id=args.authenticated_console_run_id,
        reuse_historical_authenticated_console_evidence=args.reuse_historical_authenticated_console_evidence,
        control_plane_get=control_plane_get,
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
