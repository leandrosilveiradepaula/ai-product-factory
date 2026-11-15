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
from ai_product_factory.independent_simulation_runtime_evidence import (
    verify_executed_simulation_inventory, RuntimeSimulationEvidenceBlocked,
)
from ai_product_factory.independent_complete_console_evidence import (
    ConsoleFullSurfaceEvidenceBlocked, read_verified_artifact_json,
    verify_complete_console_surface as verify_complete_console_surface_fn,
)
from ai_product_factory.independent_authenticated_console_evidence import (
    AuthenticatedConsoleEvidenceBlocked, verify_authenticated_console_evidence,
    verify_reusable_latest_authenticated_console_evidence,
)
from ai_product_factory.independent_console_accessibility_evidence import (
    verify_console_accessibility as verify_console_accessibility_fn, ConsoleAccessibilityBlocked,
)
from ai_product_factory.independent_live_console_boundary_evidence import (
    LiveConsoleBoundaryEvidenceBlocked, verify_live_console_boundaries as verify_live_console_boundaries_fn,
)
from ai_product_factory.independent_console_states_evidence import (
    ConsoleStatesEvidenceBlocked, verify_console_states as verify_console_states_fn,
)
from ai_product_factory.independent_real_journey_blocker_evidence import (
    RealJourneyBlockerEvidenceBlocked, verify_real_journey_blockers as verify_real_journey_blockers_fn,
)
from ai_product_factory.independent_isolated_console_auth_evidence import (
    IsolatedConsoleAuthEvidenceBlocked, verify_isolated_console_auth as verify_isolated_console_auth_fn,
)
from ai_product_factory.independent_b2_signed_security_evidence import (
    B2SignedSecurityBlocked, verify_independent_signed_b2,
)
from ai_product_factory.admission_diagnostics import SupabaseAdmissionReader
from trace_block1_requirements import (
    RequirementsInventoryBlocked, verify_requirements_inventory as verify_requirements_inventory_fn,
)
from inventory_block1_simulation_paths import inventory as scan_simulation_sources
from audit_block1_mock_runtime_reachability import audit as audit_simulation_reachability
from audit_global_readiness import resolve_observer_event, MAX_EVENT_BYTES
from ai_product_factory.visual_ci_source_bridge import bind_exact_ci_source
from ai_product_factory.bounded_github_evidence_read import bounded_github_evidence_read
from ai_product_factory.product_readiness_certification import _source_snapshot

# Checkout root is the script's location, never mutable working directory.
# Evidence collection can run after other verifiers and OIDC actions.
SOURCE_ROOT = Path(__file__).resolve().parents[1]


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
                            control_plane_get=None,
                            verify_complete_console_surface: bool = False,
                            verify_independent_accessibility: bool = False,
                            verify_live_console_boundaries: bool = False,
                            verify_independent_console_states: bool = False,
                            verify_real_journey_blockers: bool = False,
                            verify_isolated_console_auth: bool = False,
                            verify_independent_b2_security: bool = False,
                            artifact_reader=None,
                            source_event=None) -> dict:
    manifest = conservative_verified_manifest(
        repository=repository, assessed_commit=sha, github_get=github_get
    )
    verified_ci_event = bind_exact_ci_source(
        repository=repository, assessed_commit=sha, actual_event=source_event,
        validation_run_id=_source_snapshot(
            repository=repository, assessed_commit=sha, github_get=github_get
        )['validation_run_id'],
        github_get=github_get,
    ) if source_event is not None else None
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
                event_payload=verified_ci_event,
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
    isolated_auth_proof = None
    if verify_isolated_console_auth and regression_proof is not None:
        try:
            isolated_auth_proof = verify_isolated_console_auth_fn(
                repository=repository, assessed_commit=sha, regression_proof=regression_proof)
        except (IsolatedConsoleAuthEvidenceBlocked, ValueError, RuntimeError,
                OSError, KeyError, TypeError, UnicodeError):
            isolated_auth_proof = None
    if isolated_auth_proof is not None:
        for criterion in ("authn_authz", "data_access_boundaries"):
            manifest["criteria"]["security"][criterion].update(
                status="partial", verification_state="executed",
                reason="independent isolated PostgreSQL role, RLS and privileged-RPC negatives reverified",
                evidence=isolated_auth_proof.evidence())
    recovery_proof = None
    if verify_recovery_alerting:
        try:
            recovery_proof = verify_recovery_alerting_fn(
                repository=repository, assessed_commit=sha, github_get=github_get,
                event_payload=verified_ci_event,
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
                event_payload=verified_ci_event,
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
            authenticated_console_proof = verify_reusable_latest_authenticated_console_evidence(
                repository=repository, assessed_commit=sha, github_get=github_get,
                control_plane_get=control_plane_get,
            )
        except AuthenticatedConsoleEvidenceBlocked as exc:
            authenticated_console_blocker = "authenticated Console evidence blocked: " + str(exc)
        except (ValueError, RuntimeError, OSError, KeyError, TypeError, UnicodeError):
            authenticated_console_blocker = "authenticated Console evidence source unavailable"
    # Executed and sanitized full-surface evidence can pass ONLY two narrow
    # criteria. Browser metadata, synthetic states or expired artifacts alone
    # must never become positives. A failed optional proof retains PARTIAL.
    full_surface_proof = None
    if (verify_complete_console_surface and authenticated_console_proof is not None):
        try:
            if control_plane_get is None or artifact_reader is None:
                raise ConsoleFullSurfaceEvidenceBlocked("b3_source_readers_unavailable")
            full_surface_proof = verify_complete_console_surface_fn(
                repository=repository, assessed_commit=sha,
                authenticated_capture=authenticated_console_proof,
                github_get=github_get, control_plane_get=control_plane_get,
                artifact_reader=artifact_reader,
            )
        except (ConsoleFullSurfaceEvidenceBlocked, ValueError, RuntimeError,
                OSError, KeyError, TypeError, UnicodeError):
            full_surface_proof = None
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

    if full_surface_proof is not None:
        for criterion in ("surface_inventory", "responsive"):
            item = manifest["criteria"]["product_experience"][criterion]
            item.update(status="passed", verification_state="observed",
                        reason="independent complete authenticated browser audit reverified",
                        evidence=list(full_surface_proof.criterion(criterion).evidence))
        manifest["criteria"]["product_experience"]["accessibility"].update(
            status="partial", verification_state="observed",
            reason="independent exact-SHA authenticated browser keyboard and semantic audit is bounded",
            evidence=list(full_surface_proof.bounded_accessibility_evidence()))

    accessibility_proof = None
    if verify_independent_accessibility and full_surface_proof is not None:
        if artifact_reader is None:
            raise ConsoleAccessibilityBlocked("b3_a11y_reader_unavailable")
        # An absent historical witness remains PARTIAL. A present but malformed
        # artifact fails closed instead of silently downgrading a forgery.
        accessibility_proof = verify_console_accessibility_fn(
            repository=repository, assessed_commit=sha,
            surface=full_surface_proof, github_get=github_get,
            artifact_reader=artifact_reader,
        )
        if accessibility_proof is not None:
            claim = accessibility_proof.criterion()
            manifest["criteria"]["product_experience"]["accessibility"].update(
                status="passed", verification_state="observed",
                reason="independent authenticated Chromium WCAG A/AA, contrast and keyboard audit",
                evidence=list(claim.evidence),
            )

    # B2 and fixture-driven B3 observations are independently authenticated,
    # but intentionally remain PARTIAL.  They prove real negative ingress
    # behavior and bounded rendered transitions, never full JWT/tenant or
    # backend-state coverage.
    live_boundaries_proof = None
    if verify_live_console_boundaries and authenticated_console_proof is not None:
        try:
            if artifact_reader is None:
                raise LiveConsoleBoundaryEvidenceBlocked("live_source_reader_unavailable")
            live_boundaries_proof = verify_live_console_boundaries_fn(
                repository=repository, assessed_commit=sha,
                authenticated_capture=authenticated_console_proof,
                github_get=github_get, artifact_reader=artifact_reader,
                surface=full_surface_proof,
            )
        except (LiveConsoleBoundaryEvidenceBlocked, ValueError, RuntimeError,
                OSError, KeyError, TypeError, UnicodeError):
            live_boundaries_proof = None
    if live_boundaries_proof is not None:
        b2_evidence = ["https://github.com/" + repository + "/actions/runs/"
                       + str(live_boundaries_proof.run_id) + "#sha=" + sha]
        for criterion in ("authn_authz", "data_access_boundaries"):
            manifest["criteria"]["security"][criterion].update(
                status="partial", verification_state="executed",
                reason="independent exact-SHA live Console negative boundary witness is bounded",
                evidence=b2_evidence,
            )
        # A real backend observation and fixture transition suite are both
        # required for even bounded partial state evidence.  Either alone
        # remains useful diagnostics, but cannot be presented as state proof.
        if (live_boundaries_proof.b3_artifact_id is not None
                and live_boundaries_proof.b3_live_artifact_id is not None):
            manifest["criteria"]["product_experience"]["states"].update(
                status="partial", verification_state="observed",
                reason="independent exact-SHA authenticated UI fixture witness; real backend states remain required",
                evidence=b2_evidence,
            )

    # Complete B2 requires successful real Auth, PostgREST, PG and secrets
    # source-bound proofs. Historical captures without this witness stay partial.
    b2_security_proof = None
    if verify_independent_b2_security and authenticated_console_proof is not None:
        if (live_boundaries_proof is not None and isolated_auth_proof is not None
                and security_proof is not None and artifact_reader is not None):
            b2_security_proof = verify_independent_signed_b2(
                repository=repository, assessed_commit=sha,
                authenticated_capture=authenticated_console_proof,
                live_routes=live_boundaries_proof, isolated_pg=isolated_auth_proof,
                secrets_proof=security_proof, surface=full_surface_proof,
                github_get=github_get, artifact_reader=artifact_reader,
            )
            if b2_security_proof is not None:
                for criterion in ("authn_authz", "data_access_boundaries"):
                    claim = b2_security_proof.criterion(criterion)
                    manifest["criteria"]["security"][criterion].update(
                        status="passed", verification_state="executed",
                        reason="independent signed Supabase Auth and read-only PostgREST boundary audit",
                        evidence=list(claim.evidence),
                    )

    # B3 PASS requires complementary, independently verified LIVE Auth/CP,
    # full WCAG/browser, real gate transitions AND executed real Next/React
    # failure/empty/loading tests. A fixture-only witness never suffices.
    states_proof = None
    if (verify_independent_console_states
            and full_surface_proof is not None
            and accessibility_proof is not None
            and live_boundaries_proof is not None
            and b2_security_proof is not None
            and control_plane_get is not None):
        try:
            states_proof = verify_console_states_fn(
                repository=repository, assessed_commit=sha,
                surface=full_surface_proof, accessibility=accessibility_proof,
                live_boundaries=live_boundaries_proof, signed_b2=b2_security_proof,
                github_get=github_get, control_plane_get=control_plane_get,
            )
        except (ConsoleStatesEvidenceBlocked, ValueError, RuntimeError,
                OSError, KeyError, TypeError, UnicodeError):
            states_proof = None
    if states_proof is not None:
        claim = states_proof.criterion()
        manifest["criteria"]["product_experience"]["states"].update(
            status="passed", verification_state="observed",
            reason="independent live authenticated and executed Next/React state matrix",
            evidence=list(claim.evidence),
        )

    journey_blocker_proof = None
    if verify_real_journey_blockers:
        try:
            if control_plane_get is None:
                raise RealJourneyBlockerEvidenceBlocked("real_journey_source_reader_unavailable")
            journey_blocker_proof = verify_real_journey_blockers_fn(control_plane_get=control_plane_get)
        except (RealJourneyBlockerEvidenceBlocked, ValueError, RuntimeError,
                OSError, KeyError, TypeError, UnicodeError):
            journey_blocker_proof = None

    # This is a BOUNDED static inventory only. It never certifies runtime
    # reachability, authorization, E2E or release. The exact-SHA CI check is
    # retained while independent dynamic ingress proof remains missing.
    simulation_proof = None
    source_inventory = None
    reachable = None
    if verify_static_simulation_inventory:
        entry = manifest["criteria"]["functional_completeness"]["mock_noop_demo_inventory"]
        try:
            source_inventory = scan_simulation_sources(SOURCE_ROOT)
        except (ValueError, SyntaxError, OSError, KeyError, TypeError, UnicodeError):
            # Do not leak exception details: source may contain credentials.
            entry["reason"] = "simulation_source_scan_unavailable"
        else:
            try:
                reachable = audit_simulation_reachability(SOURCE_ROOT)
            except (ValueError, SyntaxError, OSError, KeyError, TypeError, UnicodeError):
                entry["reason"] = "simulation_reachability_scan_unavailable"
            else:
                if (source_inventory.get("scope") == "source_markers_not_runtime_reachability"
                        and type(source_inventory.get("source_files")) is int
                        and source_inventory["source_files"] > 0
                        and source_inventory.get("writes_to_production") == 0
                        and source_inventory.get("paid_calls") == 0
                        and reachable.get("scope") == "static-runtime-cli-import-closure-and-guard-classification-not-runtime-proof"
                        and isinstance(reachable.get("reachable_modules"), list)
                        and "runtime_cli" in reachable["reachable_modules"]
                        and isinstance(reachable.get("unclassified_runtime_markers"), list)
                        and reachable.get("independent_pass") is False):
                    entry.update(
                        status="partial", verification_state="reviewed",
                        reason=("complete local Python marker scan and bounded static import closure; "
                                + ("unclassified markers remain; " if reachable["unclassified_runtime_markers"] else "")
                                + "dynamic production entrypoints remain unverified"),
                        # The conservative manifest already bound this
                        # CI URL to the exact SHA. It has no source_snapshot
                        # key; that belongs to the final report envelope.
                        evidence=list(manifest["criteria"]["test_strategy"]["regression_gates"]["evidence"]),
                    )
                else:
                    entry["reason"] = "simulation_inventory_source_contract_unverified"
    # Positive B2 proof requires real executed entrypoints in exact-SHA CI,
    # a blob-pinned test source, the complete marker inventory and no
    # unclassified imports. Missing or modified tests remain partial.
    if verify_static_simulation_inventory and source_inventory and reachable:
        try:
            simulation_proof = verify_executed_simulation_inventory(
                repository=repository, assessed_commit=sha, github_get=github_get,
                source_inventory=source_inventory, runtime_reachability=reachable,
            )
        except (RuntimeSimulationEvidenceBlocked, ValueError, RuntimeError,
                OSError, KeyError, TypeError, UnicodeError):
            simulation_proof = None
        if simulation_proof is not None:
            manifest["criteria"]["functional_completeness"]["mock_noop_demo_inventory"].update(
                status="passed", verification_state="reviewed",
                reason="independently verified exact-SHA executed runtime denials and static import closure",
                evidence=list(simulation_proof.evidence),
            )

    requirements_proof = None
    if verify_requirements_inventory:
        try:
            requirements_proof = verify_requirements_inventory_fn(
                repository=repository, assessed_commit=sha, github_get=github_get,
                criteria=manifest["criteria"], event_payload=verified_ci_event,
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
        if domain == "security" and criterion in ("authn_authz", "data_access_boundaries"):
            return b2_security_proof.criterion(criterion) if b2_security_proof is not None else None
        if (domain, criterion) == ("test_strategy", "regression_gates"):
            return regression_proof
        if (domain, criterion) == ("observability_operations", "recovery_alerting"):
            return recovery_proof
        if (domain, criterion) == ("documentation", "operations"):
            return operations_proof
        if (domain, criterion) == ("functional_completeness", "requirements_inventory"):
            return requirements_proof
        if domain == "product_experience" and criterion in ("surface_inventory", "responsive"):
            return full_surface_proof.criterion(criterion) if full_surface_proof is not None else None
        if (domain, criterion) == ("product_experience", "accessibility"):
            return accessibility_proof.criterion() if accessibility_proof is not None else None
        if (domain, criterion) == ("product_experience", "states"):
            return states_proof.criterion() if states_proof is not None else None
        if (domain, criterion) == ("functional_completeness", "mock_noop_demo_inventory"):
            return simulation_proof
        return None
    certification = certify_product_readiness(
        repository=repository, assessed_commit=sha,
        manifest=manifest, github_get=github_get,
        trusted_verifier=trusted if any(x is not None for x in
            (proof, health_proof, setup_proof, rollback_proof, security_proof, regression_proof, recovery_proof, operations_proof, requirements_proof, simulation_proof, full_surface_proof, accessibility_proof, b2_security_proof, states_proof)) else None,
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
        **({"independent_accessibility_evidence": accessibility_proof.receipt()}
           if accessibility_proof is not None else {}),
        **({"live_console_boundary_evidence": live_boundaries_proof.receipt()}
           if live_boundaries_proof is not None else {}),
        **({"independent_console_states_evidence": states_proof.receipt()}
           if states_proof is not None else {}),
        **({"real_journey_blocker_evidence": journey_blocker_proof.receipt()}
           if journey_blocker_proof is not None else {}),
        **({"isolated_console_auth_evidence": isolated_auth_proof.receipt()}
           if isolated_auth_proof is not None else {}),
        **({"independent_b2_signed_security_evidence": b2_security_proof.receipt()}
           if b2_security_proof is not None else {}),
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
    parser.add_argument("--verify-complete-console-surface", action="store_true")
    parser.add_argument("--verify-independent-accessibility", action="store_true")
    parser.add_argument("--verify-live-console-boundaries", action="store_true")
    parser.add_argument("--verify-independent-console-states", action="store_true")
    parser.add_argument("--verify-real-journey-blockers", action="store_true")
    parser.add_argument("--verify-isolated-console-auth", action="store_true")
    parser.add_argument("--verify-independent-b2-security", action="store_true")
    parser.add_argument("--reuse-historical-authenticated-console-evidence", action="store_true")
    args = parser.parse_args(argv)
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if (not args.event_path.is_file()
            or not 0 < args.event_path.stat().st_size <= MAX_EVENT_BYTES):
        raise SystemExit("UNVERIFIABLE_CERTIFICATION_EVENT")
    event = json.loads(args.event_path.read_text(encoding="utf-8"))
    sha, _, _ = resolve_observer_event(event, repo)
    token = resolve_github_token(repo)
    github_get = bounded_github_evidence_read(lambda path: github_read(token, path))
    control_plane_get = (SupabaseAdmissionReader()._get
                         if (args.reuse_historical_authenticated_console_evidence
                             or args.verify_complete_console_surface
                             or args.verify_real_journey_blockers) else None)
    artifact_reader = (lambda repository, artifact_id, **kwargs: read_verified_artifact_json(
        repository=repository, artifact_id=artifact_id, token=token, **kwargs
    )) if (args.verify_complete_console_surface or args.verify_live_console_boundaries
           or args.verify_independent_accessibility or args.verify_independent_b2_security) else None
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
        verify_complete_console_surface=args.verify_complete_console_surface,
        verify_independent_accessibility=args.verify_independent_accessibility,
        verify_live_console_boundaries=args.verify_live_console_boundaries,
        verify_independent_console_states=args.verify_independent_console_states,
        verify_real_journey_blockers=args.verify_real_journey_blockers,
        verify_isolated_console_auth=args.verify_isolated_console_auth,
        verify_independent_b2_security=args.verify_independent_b2_security,
        artifact_reader=artifact_reader,
        source_event=event,
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
