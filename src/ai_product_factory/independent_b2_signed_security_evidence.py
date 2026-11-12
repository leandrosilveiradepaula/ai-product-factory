"""Independent B2 source verifier: real provider-signed JWT and live RLS denials.

A browser fixture or isolated SQL test alone NEVER grants security PASS.
Evidence requires three independent sources on the exact Git SHA:
  * completed trusted ephemeral-operator Console capture + real Auth/PostgREST,
  * verified live HTTP routes/role denials, and
  * exact-tree isolated PostgreSQL RLS/privileged-RPC negatives.
No secrets, JWTs, user IDs, response bodies or raw providers are persisted.
"""
from __future__ import annotations

from dataclasses import dataclass

from .independent_authenticated_console_evidence import AuthenticatedConsoleEvidence
from .independent_live_console_boundary_evidence import VerifiedLiveConsoleBoundaries
from .independent_isolated_console_auth_evidence import IsolatedConsoleAuthEvidence
from .independent_complete_console_evidence import SHA, VerifiedConsoleSurface
REPO = "leandrosilveiradepaula/ai-product-factory"
from .product_readiness_certification import VerifiedCriterionEvidence

FILE = "block1-b2-supabase-security.json"
PREFIX = "block1-b2-supabase-security-"
TABLES = (
    "factory_agent_concurrency_decisions",
    "factory_agent_scope_locks",
    "factory_agents",
    "factory_audit_events",
    "factory_change_set_work_units",
    "factory_change_sets",
    "factory_ci_repair_requests",
    "factory_codex_usage",
    "factory_decisions",
    "factory_definition_of_done_evidence",
    "factory_definitions_of_done",
    "factory_deployments",
    "factory_evaluations",
    "factory_execution_team_plans",
    "factory_external_webhook_wakes",
    "factory_github_app_config",
    "factory_human_gates",
    "factory_impact_analyses",
    "factory_improvement_proposals",
    "factory_incidents",
    "factory_journey_source_evidence_v2",
    "factory_journey_supersessions_v2",
    "factory_journeys",
    "factory_policy_decisions",
    "factory_portfolio_decisions",
    "factory_primary_cost_policy",
    "factory_product_readiness_certifications",
    "factory_product_specs",
    "factory_project_attachments",
    "factory_project_brain_edges",
    "factory_project_brain_nodes",
    "factory_project_brain_snapshots",
    "factory_project_control_wakes",
    "factory_project_database_oauth",
    "factory_project_databases",
    "factory_project_execution_commands",
    "factory_project_execution_controls",
    "factory_project_github_access",
    "factory_project_scheduling",
    "factory_project_state_snapshots",
    "factory_projects",
    "factory_release_reports",
    "factory_repair_jobs",
    "factory_replay_requests",
    "factory_requirement_evidence",
    "factory_requirement_task_links",
    "factory_requirements",
    "factory_resource_limit_snapshots",
    "factory_run_agent_assignments",
    "factory_run_provenance",
    "factory_runs",
    "factory_shadow_decisions",
    "factory_specialist_lane_jobs",
    "factory_tasks",
    "factory_tool_usage",
    "factory_visual_evidence_runs",
    "factory_work_unit_context_packets",
)
CHECKS = frozenset({
    "providerSignedUserVerified",
    "providerActorBoundToEphemeralOperator",
    "forgedSignatureRejected",
    "forgedRoleRejected",
    "forgedSubjectRejected",
    "activeOperatorOwnRowOnly",
    "anonymousOperatorDirectoryDenied",
    "anonymousProjectDataDenied",
    "untrustedControlPlaneTablesDenied",
})
FIELDS = frozenset({
    "schema", "runId", "sourceCommit", "targetCommit", "scope",
    "checks", "checkedTables", "privilegedRpcDenialSource",
    "independentTenantModelClaimed", "productionWrites", "mutatingRequests",
    "paidCalls", "personalDataRetained",
})
SCHEMA = "factory-b2-live-supabase-auth-data-v1"
SCOPE = "signed_supabase_auth_operator_and_unprivileged_control_plane_boundary"


class B2SignedSecurityBlocked(RuntimeError):
    """Fixed code only, never an external response or private security detail."""


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise B2SignedSecurityBlocked(reason)


def validate_real_b2_receipt(value: object, *, run_id: int,
                             source_sha: str, served_sha: str | None = None) -> None:
    require(isinstance(value, dict) and set(value) == FIELDS,
            "b2_live_receipt_shape_invalid")
    require(
        value.get("schema") == SCHEMA
        and type(value.get("runId")) is int and value["runId"] == run_id
        and value.get("sourceCommit") == source_sha
        and value.get("targetCommit") == (source_sha if served_sha is None else served_sha)
        and value.get("scope") == SCOPE
        and value.get("checkedTables") == list(TABLES)
        and value.get("privilegedRpcDenialSource")
        == "independent_exact_tree_isolated_postgres",
        "b2_live_receipt_source_mismatch",
    )
    checks = value.get("checks")
    require(
        isinstance(checks, dict) and set(checks) == CHECKS
        and all(checks[k] is True for k in CHECKS - {
            "untrustedControlPlaneTablesDenied"})
        and type(checks.get("untrustedControlPlaneTablesDenied")) is int
        and checks["untrustedControlPlaneTablesDenied"] == len(TABLES),
        "b2_live_checks_invalid",
    )
    require(
        value.get("independentTenantModelClaimed") is False
        and value.get("personalDataRetained") is False
        and all(type(value.get(k)) is int and value[k] == 0
                for k in ("productionWrites", "mutatingRequests", "paidCalls")),
        "b2_live_safety_or_tenant_overclaim",
    )


@dataclass(frozen=True)
class VerifiedSignedB2:
    repository: str
    assessed_commit: str
    run_id: int
    artifact_id: int
    role_boundary_artifact_id: int
    isolated_pg_run_id: int

    def receipt(self) -> dict:
        return {
            "schema": "factory-b2-independent-signed-provider-boundaries-v1",
            "repository": self.repository,
            "assessed_commit": self.assessed_commit,
            "workflow_run_id": self.run_id,
            "artifact_id": self.artifact_id,
            "role_boundary_artifact_id": self.role_boundary_artifact_id,
            "isolated_postgres_run_id": self.isolated_pg_run_id,
            "real_provider_signature_rejection": True,
            "live_unprivileged_data_plane_denials": list(TABLES),
            "cross_operator_rls_self_only": True,
            "privileged_rpc_denials_isolated": True,
            "single_organization_portfolio_scope": True,
            "independent_multi_tenant_operator_partition_claimed": False,
            "writes": 0,
            "paid_calls": 0,
        }

    def criterion(self, name: str) -> VerifiedCriterionEvidence:
        require(name in ("authn_authz", "data_access_boundaries"),
                "b2_criterion_not_authorized")
        return VerifiedCriterionEvidence(
            domain="security", criterion=name,
            repository=self.repository, assessed_commit=self.assessed_commit,
            verification_state="executed",
            source="independent_real_supabase_signed_jwt_roles_rls_and_postgrest_denials",
            evidence=("https://github.com/" + self.repository + "/actions/runs/"
                      + str(self.run_id) + "#sha=" + self.assessed_commit,
                      "https://github.com/" + self.repository + "/actions/runs/"
                      + str(self.isolated_pg_run_id) + "#sha=" + self.assessed_commit),
            retained_receipt={**self.receipt(), "criterion": name},
        )


def verify_independent_signed_b2(*, repository: str, assessed_commit: str,
                                 authenticated_capture: AuthenticatedConsoleEvidence,
                                 live_routes: VerifiedLiveConsoleBoundaries,
                                 isolated_pg: IsolatedConsoleAuthEvidence,
                                 secrets_proof: VerifiedCriterionEvidence,
                                 surface: VerifiedConsoleSurface,
                                 github_get, artifact_reader) -> VerifiedSignedB2 | None:
    require(repository == REPO and isinstance(assessed_commit, str)
            and SHA.fullmatch(assessed_commit) is not None,
            "b2_source_repository_or_sha_invalid")
    require(
        isinstance(authenticated_capture, AuthenticatedConsoleEvidence)
        and authenticated_capture.repository == repository
        and authenticated_capture.assessed_commit == assessed_commit
        and authenticated_capture.source_commit in (None, assessed_commit)
        and type(authenticated_capture.artifact_id) is int
        and authenticated_capture.artifact_id > 0
        and isinstance(live_routes, VerifiedLiveConsoleBoundaries)
        and live_routes.repository == repository
        and live_routes.assessed_commit == assessed_commit
        and live_routes.run_id == authenticated_capture.workflow_run_id
        and type(live_routes.b2_artifact_id) is int
        and live_routes.b2_artifact_id > 0,
        "b2_real_captured_routes_not_verified",
    )
    require(
        isinstance(isolated_pg, IsolatedConsoleAuthEvidence)
        and isolated_pg.repository == repository
        and isolated_pg.assessed_commit == assessed_commit
        and type(isolated_pg.run_id) is int and isolated_pg.run_id > 0
        and isinstance(secrets_proof, VerifiedCriterionEvidence)
        and secrets_proof.domain == "security"
        and secrets_proof.criterion == "secrets_dependencies"
        and secrets_proof.repository == repository
        and secrets_proof.assessed_commit == assessed_commit
        and secrets_proof.verification_state in ("executed", "reviewed"),
        "b2_isolated_sql_or_secret_exposure_not_verified",
    )
    run_id = authenticated_capture.workflow_run_id
    require(type(surface) is VerifiedConsoleSurface
            and surface.repository == repository
            and surface.assessed_commit == assessed_commit
            and surface.run_id == run_id
            and surface.source_commit in (None, assessed_commit)
            and isinstance(surface.target_commit, str)
            and SHA.fullmatch(surface.target_commit) is not None,
            "b2_verified_served_console_mismatch")
    inventory = github_get("/repos/" + repository + "/actions/runs/"
                           + str(run_id) + "/artifacts?per_page=100")
    artifacts = inventory.get("artifacts") if isinstance(inventory, dict) else None
    require(isinstance(artifacts, list)
            and type(inventory.get("total_count")) is int
            and inventory["total_count"] == len(artifacts)
            and 0 <= len(artifacts) <= 100,
            "b2_artifact_inventory_invalid")
    candidates = [x for x in artifacts if isinstance(x, dict)
                  and x.get("name") == PREFIX + str(run_id)]
    if not candidates:
        return None  # Old runs cannot gain a new B2 PASS by missing data.
    require(len(candidates) == 1, "b2_artifact_duplicated")
    row = candidates[0]
    binding = row.get("workflow_run")
    require(
        type(row.get("id")) is int and row["id"] > 0
        and row.get("expired") is False
        and type(row.get("size_in_bytes")) is int
        and 200 <= row["size_in_bytes"] <= 8192
        and isinstance(binding, dict)
        and binding.get("id") == run_id
        and binding.get("head_branch") == "main"
        and binding.get("head_sha") == assessed_commit,
        "b2_artifact_provenance_invalid",
    )
    try:
        payload = artifact_reader(
            repository=repository, artifact_id=row["id"], artifact_file=FILE,
        )
    except (OSError, ValueError, RuntimeError, UnicodeError, KeyError, TypeError) as exc:
        raise B2SignedSecurityBlocked("b2_artifact_read_unavailable") from exc
    validate_real_b2_receipt(payload, run_id=run_id, source_sha=assessed_commit,
                             served_sha=surface.target_commit)
    return VerifiedSignedB2(
        repository=repository, assessed_commit=assessed_commit,
        run_id=run_id, artifact_id=row["id"],
        role_boundary_artifact_id=live_routes.b2_artifact_id,
        isolated_pg_run_id=isolated_pg.run_id,
    )
