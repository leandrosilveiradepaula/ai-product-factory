"""Create/recover one independent durable product-readiness certification."""
from __future__ import annotations
import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

from ai_product_factory.product_readiness_certification import certify_product_readiness, CertificationEvidenceError
from ai_product_factory.supabase_delivery_store import SupabaseDeliveryStore
from ai_product_factory.native_v2_traceability_certification import (
    verify_existing_crm_v2_traceability,
)
from ai_product_factory.independent_health_evidence import verify_health_for_certification
from ai_product_factory.independent_setup_evidence import verify_existing_clean_setup
from ai_product_factory.independent_rollback_evidence import verify_existing_isolated_rollback
from ai_product_factory.independent_security_evidence import verify_existing_secrets_dependencies
from ai_product_factory.independent_regression_evidence import verify_regression_gates
from ai_product_factory.independent_recovery_evidence import verify_recovery_alerting
from ai_product_factory.independent_operations_evidence import verify_operations_runbook
from ai_product_factory.independent_simulation_runtime_evidence import (
    verify_executed_simulation_inventory,
)
from inventory_block1_simulation_paths import inventory as simulation_inventory
from audit_block1_mock_runtime_reachability import audit as simulation_reachability
from ai_product_factory.independent_complete_console_evidence import (
    ConsoleFullSurfaceEvidenceBlocked, read_verified_artifact_json,
    verify_complete_console_surface,
)
from ai_product_factory.independent_authenticated_console_evidence import (
    AuthenticatedConsoleEvidenceBlocked, verify_authenticated_console_evidence,
    verify_reusable_historical_authenticated_console_evidence,
)
from ai_product_factory.admission_diagnostics import SupabaseAdmissionReader
from trace_block1_requirements import verify_requirements_inventory
from ai_product_factory.readiness_prewrite_guard import require_monotonic_before_write
from ai_product_factory.visual_ci_source_bridge import bind_exact_ci_source


def _github_get(token: str):
    def get(path: str):
        request = urllib.request.Request("https://api.github.com" + path,
            headers={"Accept": "application/vnd.github+json", "Authorization": "Bearer " + token,
                     "X-GitHub-Api-Version": "2022-11-28"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode())
    return get



def require_verified_baseline(value: object, *, repository: str, assessed_commit: str) -> dict:
    """Accept only a same-repository, same-SHA conservative CI evidence envelope.

    The whole envelope is revalidated after the certifier independently fetches
    live GitHub HEAD, exact push validation run and two successful CI jobs.
    Never trust a file alone to confer product readiness.
    """
    if not isinstance(value, dict):
        raise CertificationEvidenceError("verified baseline must be a JSON object")
    if (value.get("schema_version") != 1
            or value.get("scope") != "read_only_independent_source_verified_baseline"
            or value.get("repository") != repository
            or value.get("assessed_commit") != assessed_commit
            or value.get("writes") != 0 or value.get("paid_calls") != 0
            or value.get("start_authorized") is not False
            or type(value.get("product_ready")) is not bool
            or value.get("product_ready") is not value.get("assessment", {}).get("ready")
            or not isinstance(value.get("manifest"), dict)
            or not isinstance(value.get("source_snapshot"), dict)
            or not isinstance(value.get("evidence_digest"), str)
            or not isinstance(value.get("assessment"), dict)):
        raise CertificationEvidenceError("untrusted or inconsistent readiness baseline")
    return value["manifest"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Independent deterministic product-readiness certification")
    parser.add_argument("--project-key", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--assessed-commit", required=True)
    parser.add_argument("--evidence-file", type=Path, required=True)
    parser.add_argument("--verify-native-v2-traceability", action="store_true")
    parser.add_argument("--verify-independent-health", action="store_true")
    parser.add_argument("--verify-independent-setup", action="store_true")
    parser.add_argument("--verify-isolated-rollback", action="store_true")
    parser.add_argument("--verify-secrets-dependencies", action="store_true")
    parser.add_argument("--verify-regression-gates", action="store_true")
    parser.add_argument("--verify-recovery-alerting", action="store_true")
    parser.add_argument("--verify-operations-runbook", action="store_true")
    parser.add_argument("--verify-requirements-inventory", action="store_true")
    parser.add_argument("--verify-executed-simulation-inventory", action="store_true")
    parser.add_argument("--authenticated-console-run-id", type=int)
    parser.add_argument("--verify-complete-console-surface", action="store_true")
    parser.add_argument("--reuse-historical-authenticated-console-evidence", action="store_true")
    parser.add_argument("--require-verified-baseline", action="store_true",
                        help="only accept the independently verified conservative CI envelope")
    args = parser.parse_args(argv)
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise SystemExit("GITHUB_TOKEN is required for exact-SHA GitHub evidence")
    evidence = json.loads(args.evidence_file.read_text(encoding="utf-8"))
    manifest = (require_verified_baseline(
        evidence, repository=args.repository, assessed_commit=args.assessed_commit
    ) if args.require_verified_baseline else evidence)
    github_get = _github_get(token)
    event_path = os.environ.get('GITHUB_EVENT_PATH')
    verified_ci_event = None
    if args.authenticated_console_run_id is not None:
        if not event_path:
            raise CertificationEvidenceError('ci_bridge_event_path_missing')
        event_payload = json.loads(Path(event_path).read_text(encoding='utf-8'))
        verified_ci_event = bind_exact_ci_source(
            repository=args.repository, assessed_commit=args.assessed_commit,
            actual_event=event_payload,
            validation_run_id=evidence['source_snapshot']['validation_run_id'],
            github_get=github_get,
        )
    if args.authenticated_console_run_id is not None:
        proof = verify_authenticated_console_evidence(
            repository=args.repository, assessed_commit=args.assessed_commit,
            workflow_run_id=args.authenticated_console_run_id,
            github_get=_github_get(token),
        )
    elif args.reuse_historical_authenticated_console_evidence and "authenticated_console_evidence" in evidence:
        proof = verify_reusable_historical_authenticated_console_evidence(
            repository=args.repository, assessed_commit=args.assessed_commit,
            github_get=_github_get(token), control_plane_get=SupabaseAdmissionReader()._get,
        )
    else:
        proof = None
    if proof is not None:
        if evidence.get("authenticated_console_evidence") != proof.receipt():
            raise CertificationEvidenceError("authenticated Console receipt changed before persistence")
        for criterion in ("surface_inventory", "responsive", "accessibility"):
            row = manifest.get("criteria", {}).get("product_experience", {}).get(criterion)
            status = row.get("status") if isinstance(row, dict) else None
            allowed = ({"passed", "partial"} if args.verify_complete_console_surface
                       and args.authenticated_console_run_id is not None
                       and criterion in ("surface_inventory", "responsive")
                       else {"partial"})
            if status not in allowed or row.get("evidence") != list(proof.evidence):
                raise CertificationEvidenceError("authenticated Console partial evidence is incomplete")
    full_surface_proof = None
    if args.verify_complete_console_surface and args.authenticated_console_run_id is not None:
        if not args.require_verified_baseline:
            raise CertificationEvidenceError("complete Console proof requires verified baseline")
        if proof is None:
            raise CertificationEvidenceError("complete Console proof requires successful exact-run evidence")
        claimed_complete = all(
            manifest.get("criteria", {}).get("product_experience", {}).get(k, {}).get("status") == "passed"
            for k in ("surface_inventory", "responsive")
        )
        if claimed_complete:
            full_surface_proof = verify_complete_console_surface(
            repository=args.repository, assessed_commit=args.assessed_commit,
            authenticated_capture=proof, github_get=_github_get(token),
            control_plane_get=SupabaseAdmissionReader()._get,
            artifact_reader=lambda repository, artifact_id: read_verified_artifact_json(
                repository=repository, artifact_id=artifact_id, token=token
            ),
        )
            for criterion in ("surface_inventory", "responsive"):
                item = manifest.get("criteria", {}).get("product_experience", {}).get(criterion)
                verified = full_surface_proof.criterion(criterion)
                if not isinstance(item, dict) or item.get("status") != "passed" or item.get("evidence") != list(verified.evidence):
                    raise CertificationEvidenceError("complete Console baseline proof inconsistent")
        elif any(
            manifest.get("criteria", {}).get("product_experience", {}).get(k, {}).get("status") == "passed"
            for k in ("surface_inventory", "responsive")
        ):
            raise CertificationEvidenceError("complete Console proof cannot be partial positive")

    if args.verify_native_v2_traceability and not args.require_verified_baseline:
        raise CertificationEvidenceError("native V2 proof requires independent conservative baseline")
    github_get = _github_get(token)
    proof = None
    if args.verify_native_v2_traceability:
        trace = manifest.get("criteria", {}).get("observability_operations", {}).get("traceability")
        if isinstance(trace, dict) and trace.get("status") == "passed":
            # This independently re-fetches and verifies the historical OWNER
            # run, artifact bytes, current code identity and live Control Plane.
            # A missing/altered source fails before begin/persist RPC.
            proof = verify_existing_crm_v2_traceability(
                repository=args.repository,
                assessed_commit=args.assessed_commit,
                github_get=github_get,
            )
        else:
            # The baseline builder may have failed closed. Persist only the
            # conservative one-cell state; do not retroactively claim success.
            proof = None
    if args.verify_independent_health and not args.require_verified_baseline:
        raise CertificationEvidenceError("health proof requires independent conservative baseline")
    health_proof = None
    if args.verify_independent_health:
        health = manifest.get("criteria", {}).get("observability_operations", {}).get("health")
        if isinstance(health, dict) and health.get("status") == "passed":
            # A positive claim MUST re-fetch live sources before begin/persist.
            # A lost deployment/probe/source invalidates the entire write.
            health_proof = verify_health_for_certification(
                repository=args.repository, assessed_commit=args.assessed_commit,
                github_get=github_get,
            )
    setup_proof = None
    if args.verify_independent_setup:
        if not args.require_verified_baseline:
            raise CertificationEvidenceError(
                "setup proof requires independent verified baseline"
            )
        setup = manifest.get("criteria", {}).get("documentation", {}).get(
            "setup_configuration"
        )
        if isinstance(setup, dict) and setup.get("status") == "passed":
            # Re-open real GitHub run/artifact, confirm immutable source,
            # and validate receipt bytes before any database reservation.
            setup_proof = verify_existing_clean_setup(
                repository=args.repository,
                assessed_commit=args.assessed_commit,
                github_get=github_get,
            )
    rollback_proof = None
    if args.verify_isolated_rollback:
        if not args.require_verified_baseline:
            raise CertificationEvidenceError("rollback proof requires independent verified baseline")
        rollback = manifest.get("criteria", {}).get("documentation", {}).get("release_rollback")
        if isinstance(rollback, dict) and rollback.get("status") == "passed":
            rollback_proof = verify_existing_isolated_rollback(
                repository=args.repository, assessed_commit=args.assessed_commit,
                github_get=github_get,
            )
    security_proof = None
    if args.verify_secrets_dependencies:
        if not args.require_verified_baseline:
            raise CertificationEvidenceError("security proof requires independent verified baseline")
        security = manifest.get("criteria", {}).get("security", {}).get("secrets_dependencies")
        if isinstance(security, dict) and security.get("status") == "passed":
            security_proof = verify_existing_secrets_dependencies(
                repository=args.repository, assessed_commit=args.assessed_commit,
                github_get=github_get,
            )
    regression_proof = None
    if args.verify_regression_gates:
        if not args.require_verified_baseline:
            raise CertificationEvidenceError("regression gates proof requires independent verified baseline")
        regression = manifest.get("criteria", {}).get("test_strategy", {}).get("regression_gates")
        if isinstance(regression, dict) and regression.get("status") == "passed":
            regression_proof = verify_regression_gates(
                repository=args.repository, assessed_commit=args.assessed_commit,
                github_get=github_get, event_payload=verified_ci_event,
            )
    recovery_proof = None
    if args.verify_recovery_alerting:
        if not args.require_verified_baseline:
            raise CertificationEvidenceError("recovery proof requires independent verified baseline")
        recovery = manifest.get("criteria", {}).get("observability_operations", {}).get("recovery_alerting")
        if isinstance(recovery, dict) and recovery.get("status") == "passed":
            recovery_proof = verify_recovery_alerting(
                repository=args.repository, assessed_commit=args.assessed_commit,
                github_get=github_get, event_payload=verified_ci_event,
            )
    operations_proof = None
    if args.verify_operations_runbook:
        if not args.require_verified_baseline:
            raise CertificationEvidenceError("operations proof requires independent verified baseline")
        operations = manifest.get("criteria", {}).get("documentation", {}).get("operations")
        if isinstance(operations, dict) and operations.get("status") == "passed":
            operations_proof = verify_operations_runbook(
                repository=args.repository, assessed_commit=args.assessed_commit,
                github_get=github_get, event_payload=verified_ci_event,
            )
    requirements_proof = None
    if args.verify_requirements_inventory:
        if not args.require_verified_baseline:
            raise CertificationEvidenceError("requirements proof requires independent verified baseline")
        row = manifest.get("criteria", {}).get("functional_completeness", {}).get("requirements_inventory")
        if isinstance(row, dict) and row.get("status") == "passed":
            # Recalculate exact same Git tree, source bytes, 19 stages and all
            # OTHER criterion states. No JSON-provided proof is trusted.
            requirements_proof = verify_requirements_inventory(
                repository=args.repository, assessed_commit=args.assessed_commit,
                github_get=github_get, criteria=manifest["criteria"],
                event_payload=verified_ci_event,
            )

    simulation_proof = None
    if args.verify_executed_simulation_inventory:
        if not args.require_verified_baseline:
            raise CertificationEvidenceError("simulation evidence requires independent verified baseline")
        row = manifest.get("criteria", {}).get("functional_completeness", {}).get("mock_noop_demo_inventory")
        if isinstance(row, dict) and row.get("status") == "passed":
            root = Path(__file__).resolve().parents[1]
            simulation_proof = verify_executed_simulation_inventory(
                repository=args.repository, assessed_commit=args.assessed_commit,
                github_get=github_get, source_inventory=simulation_inventory(root),
                runtime_reachability=simulation_reachability(root),
            )

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
        if domain == "product_experience" and criterion in ("surface_inventory", "responsive"):
            return full_surface_proof.criterion(criterion) if full_surface_proof is not None else None
        if (domain, criterion) == ("functional_completeness", "mock_noop_demo_inventory"):
            return simulation_proof
        return None
    certification = certify_product_readiness(
        repository=args.repository, assessed_commit=args.assessed_commit,
        manifest=manifest, github_get=github_get,
        trusted_verifier=trusted if any(x is not None for x in
            (proof, health_proof, setup_proof, rollback_proof, security_proof, regression_proof, recovery_proof, operations_proof, requirements_proof, simulation_proof, full_surface_proof)) else None,
    )
    if args.require_verified_baseline:
        if (certification.report["source_snapshot"] != evidence["source_snapshot"]
                or certification.evidence_digest != evidence["evidence_digest"]
                or certification.assessment.as_result() != evidence["assessment"]
                or evidence["product_ready"] is not certification.assessment.ready):
            raise CertificationEvidenceError("readiness evidence changed before persistence")
    # Block an evidence-source regression before the irreversible certificate write.
    require_monotonic_before_write(
        repository=args.repository, assessed_commit=args.assessed_commit,
        new_report=certification.report, get=SupabaseAdmissionReader()._get,
    )
    # In the protected workflow, the same pinned control-plane-oidc action is
    # run immediately before this command. Keeping token acquisition there
    # avoids a second, differently implemented OIDC client at the write
    # boundary. This process only receives its short-lived broker token via
    # the runner environment and never records it.
    store = SupabaseDeliveryStore()
    begun = store.begin_product_readiness_certification(project_key=args.project_key,
        repository=args.repository, assessed_commit=args.assessed_commit,
        evidence_digest=certification.evidence_digest)
    try:
        saved = store.persist_product_readiness_certification(certification_id=begun["certification_id"],
            run_id=begun["run_id"], assessment=certification.assessment, report=certification.report,
            evidence_digest=certification.evidence_digest)
    except RuntimeError as exc:
        # Keep the receipt bounded to immutable identifiers and a sanitized
        # provider code; never persist broker/SQL/credential response bodies.
        print(json.dumps({"certification": begun,
                          "persistence": {"status": "blocked", "diagnostic": str(exc)},
                          "product_ready": certification.assessment.ready,
                          "status": certification.assessment.status}, sort_keys=True))
        raise
    print(json.dumps({"certification": begun, "evaluation": saved,
                      "product_ready": certification.assessment.ready,
                      "status": certification.assessment.status}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
