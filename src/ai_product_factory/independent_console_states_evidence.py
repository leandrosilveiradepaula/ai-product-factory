"""Independent B3 full state matrix from genuinely executed, complementary sources.

Do not mislabel a fixture-only browser trace as live backend certification.
A PASS needs all of: a real authenticated whole-Console Chromium/WCAG
capture, signed B2 negative ingress, a real backend GET, durable human-gate
transitions, and real production Next/React state and error-path browser
execution in CI. Read-only; no production state injection or secret retention.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from .product_readiness_certification import VerifiedCriterionEvidence
from .independent_complete_console_evidence import VerifiedConsoleSurface
from .independent_console_accessibility_evidence import VerifiedConsoleAccessibility
from .independent_live_console_boundary_evidence import VerifiedLiveConsoleBoundaries
from .independent_b2_signed_security_evidence import VerifiedSignedB2

REPO = "leandrosilveiradepaula/ai-product-factory"
SHA_LEN = 40
REVIEWED_SOURCE_SHA = "8f1bf1c21e2b400c5de1c9cd6ac2b44a21e4c74e"
# Scripts that actually exercise error, retry, disabled, awaiting, human-gate
# and live browser scenarios. A later code-only merge may reuse them ONLY if
# the immutable blobs still equal both the originally executed source and the
# audited benchmark SHA. Never pin a moving branch.
EXECUTED_STATE_FILES = (
    ".github/workflows/console.yml",
    "scripts/test_console_hydration_production_browser.cjs",
    "scripts/test_console_migration_browser.cjs",
    "scripts/test_console_migration_interaction.cjs",
    "scripts/test_console_status_semantics.cjs",
    "scripts/test_console_accessibility_contract.mjs",
    "scripts/verify_block1_b3_live_console_state.mjs",
    "scripts/verify_block1_b3_live_console_states.mjs",
    "scripts/capture_authenticated_console.mjs",
    "scripts/console_wcag_audit.mjs",
    "tests/test_console_manual_execution_flow.py",
    "tests/test_console_gate_action_errors.py",
    "tests/test_console_queue_visibility.py",
)
REQUIRED_CI_STEPS = (
    "Test real Console status and accessibility semantics",
    "Verify actual migration feedback modules with offline delayed audit",
    "Verify migration pending success and failure in isolated Chromium",
    "Run npm run typecheck",
    "Run npm run build",
    "Exercise real authenticated configuration SSR and React hydration in isolated Chromium",
)


class ConsoleStatesEvidenceBlocked(RuntimeError):
    """Fixed source-only diagnostic; no provider content or operator PII."""


def require(ok: bool, why: str) -> None:
    if not ok:
        raise ConsoleStatesEvidenceBlocked(why)


def sha_ok(value: object) -> bool:
    return (isinstance(value, str) and len(value) == SHA_LEN
            and all(c in "0123456789abcdef" for c in value))


def _source_blobs(github_get: Callable[[str], object], sha: str) -> dict:
    prefix = "/repos/" + REPO
    commit = github_get(prefix + "/git/commits/" + sha)
    tree_sha = (commit.get("tree") or {}).get("sha") if isinstance(commit, dict) else None
    require(sha_ok(tree_sha), "b3_state_source_tree_absent")
    tree = github_get(prefix + "/git/trees/" + tree_sha + "?recursive=1")
    rows = tree.get("tree") if isinstance(tree, dict) else None
    require(isinstance(rows, list) and tree.get("truncated") is False
            and len(rows) <= 10000, "b3_state_tree_unverifiable")
    paths = {}
    for row in rows:
        if isinstance(row, dict) and row.get("path") in EXECUTED_STATE_FILES:
            name = row["path"]
            require(name not in paths and row.get("type") == "blob"
                    and row.get("mode") == "100644" and sha_ok(row.get("sha")),
                    "b3_state_test_source_untrusted")
            paths[name] = row["sha"]
    require(set(paths) == set(EXECUTED_STATE_FILES),
            "b3_state_test_inventory_incomplete")
    return paths


def _executed_console_ci(github_get, source_sha: str) -> int:
    prefix = "/repos/" + REPO
    runs = github_get(prefix + "/actions/runs?head_sha=" + source_sha
                      + "&event=push&per_page=100")
    rows = runs.get("workflow_runs") if isinstance(runs, dict) else None
    require(isinstance(rows, list) and len(rows) <= 100
            and type(runs.get("total_count")) is int
            and len(rows) == runs["total_count"],
            "b3_state_ci_inventory_unverifiable")
    matches = [r for r in rows if isinstance(r, dict)
               and r.get("name") == "Console validation"
               and r.get("path") == ".github/workflows/console.yml"
               and r.get("event") == "push"
               and r.get("head_sha") == source_sha
               and r.get("head_branch") == "main"
               and r.get("status") == "completed"
               and r.get("conclusion") == "success"
               and r.get("run_attempt") == 1
               and type(r.get("id")) is int and r["id"] > 0]
    require(len(matches) == 1, "b3_state_executed_console_ci_missing_or_ambiguous")
    run_id = matches[0]["id"]
    jobs = github_get(prefix + "/actions/runs/" + str(run_id) + "/jobs?per_page=100")
    items = jobs.get("jobs") if isinstance(jobs, dict) else None
    require(isinstance(items, list) and len(items) == 1
            and jobs.get("total_count") == 1, "b3_state_ci_job_unverifiable")
    job = items[0]
    require(isinstance(job, dict) and job.get("name") == "validate"
            and job.get("run_id") == run_id and job.get("head_sha") == source_sha
            and job.get("status") == "completed" and job.get("conclusion") == "success"
            and isinstance(job.get("steps"), list),
            "b3_state_ci_job_not_success")
    steps = job["steps"]
    for name in REQUIRED_CI_STEPS:
        found = [s for s in steps if isinstance(s, dict) and s.get("name") == name]
        require(len(found) == 1 and found[0].get("status") == "completed"
                and found[0].get("conclusion") == "success",
                "b3_state_ci_state_step_missing")
    return run_id


def _verified_gate_transitions(cp_get: Callable[[str], object]) -> tuple[int, int]:
    # Only allowlisted status and timestamps, no actor, note, id, token, reason,
    # project name, or personal data. Every resolved gate once was pending.
    rows = cp_get("factory_human_gates?select=status,requested_at,resolved_at"
                  "&order=requested_at.desc&limit=75")
    require(isinstance(rows, list) and 2 <= len(rows) < 75
            and all(isinstance(row, dict) and set(row)
                    == {"status", "requested_at", "resolved_at"} for row in rows),
            "b3_state_gate_history_unavailable")
    counts = {"approved": 0, "rejected": 0}
    for row in rows:
        status = row["status"]
        if status not in counts:
            # Open gates are legitimate and not a pass/failure transition.
            require(status == "pending" and row["resolved_at"] is None
                    and isinstance(row["requested_at"], str),
                    "b3_state_gate_status_invalid")
            continue
        try:
            request = datetime.fromisoformat(row["requested_at"].replace("Z", "+00:00"))
            resolved = datetime.fromisoformat(row["resolved_at"].replace("Z", "+00:00"))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ConsoleStatesEvidenceBlocked("b3_state_gate_time_invalid") from exc
        require(request.tzinfo is not None and resolved.tzinfo is not None
                and resolved >= request, "b3_state_gate_time_invalid")
        counts[status] += 1
    require(counts["approved"] >= 1 and counts["rejected"] >= 1,
            "b3_state_real_gate_outcomes_missing")
    return counts["approved"], counts["rejected"]


@dataclass(frozen=True)
class VerifiedConsoleStates:
    repository: str
    assessed_commit: str
    source_commit: str
    visual_run_id: int
    console_ci_run_id: int
    approved_transitions: int
    rejected_transitions: int

    def receipt(self) -> dict:
        return {
            "schema": "factory-b3-independent-real-and-isolated-state-matrix-v1",
            "repository": self.repository,
            "assessed_commit": self.assessed_commit,
            "browser_source_sha": self.source_commit,
            "visual_run_id": self.visual_run_id,
            "console_ci_run_id": self.console_ci_run_id,
            "approved_real_gate_transitions": self.approved_transitions,
            "rejected_real_gate_transitions": self.rejected_transitions,
            "authenticated_ui_full_surface_wcag": True,
            "real_backend_read_observed": True,
            "signed_auth_deny_observed": True,
            "next_react_loading_pending_retry_empty_error_isolated": True,
            "human_gate_success_failure_isolated": True,
            "offline_fault_injection_not_production_state": True,
            "production_writes": 0,
            "paid_calls": 0,
            "operator_or_response_data_retained": False,
            "critical_journeys_certified": False,
            "critical_e2e_certified": False,
            "product_ready": False,
        }

    def criterion(self) -> VerifiedCriterionEvidence:
        return VerifiedCriterionEvidence(
            domain="product_experience", criterion="states",
            repository=self.repository, assessed_commit=self.assessed_commit,
            verification_state="observed",
            source="independent_live_auth_wcg_real_gate_and_executed_next_react_state_matrix",
            evidence=(
                "https://github.com/" + self.repository + "/actions/runs/"
                + str(self.visual_run_id) + "#sha=" + self.assessed_commit,
                "https://github.com/" + self.repository + "/actions/runs/"
                + str(self.console_ci_run_id) + "#sha=" + self.assessed_commit,
            ),
            retained_receipt=self.receipt(),
        )


def verify_console_states(*, repository: str, assessed_commit: str,
                          surface: VerifiedConsoleSurface,
                          accessibility: VerifiedConsoleAccessibility,
                          live_boundaries: VerifiedLiveConsoleBoundaries,
                          signed_b2: VerifiedSignedB2,
                          github_get, control_plane_get) -> VerifiedConsoleStates:
    require(repository == REPO and sha_ok(assessed_commit)
            and type(surface) is VerifiedConsoleSurface
            and type(accessibility) is VerifiedConsoleAccessibility
            and type(live_boundaries) is VerifiedLiveConsoleBoundaries
            and type(signed_b2) is VerifiedSignedB2,
            "b3_state_prerequisites_invalid")
    source_sha = surface.source_commit or assessed_commit
    require(sha_ok(source_sha) and all(
        proof.repository == repository and proof.assessed_commit == assessed_commit
        and proof.run_id == surface.run_id
        for proof in (surface, accessibility, live_boundaries, signed_b2)),
        "b3_state_source_identity_mismatch")
    require(live_boundaries.b3_artifact_id is not None
            and live_boundaries.b3_live_artifact_id is not None
            and accessibility.artifact_id > 0 and surface.artifact_id > 0
            and signed_b2.artifact_id > 0, "b3_state_missing_live_and_isolated_witness")
    # The full-surface verifier separately proved HTTPS deployment, Vercel,
    # exact CI/ancestry, and the same source Console subtree. Independently
    # forbid replacement of real browser/Next/WCAG test scripts by no-ops.
    reviewed = _source_blobs(github_get, REVIEWED_SOURCE_SHA)
    source = _source_blobs(github_get, source_sha)
    current = _source_blobs(github_get, assessed_commit)
    require(source == reviewed and current == reviewed,
            "b3_state_executed_test_source_changed")
    ci_run = _executed_console_ci(github_get, source_sha)
    approved, rejected = _verified_gate_transitions(control_plane_get)
    return VerifiedConsoleStates(
        repository=repository, assessed_commit=assessed_commit,
        source_commit=source_sha, visual_run_id=surface.run_id,
        console_ci_run_id=ci_run,
        approved_transitions=approved, rejected_transitions=rejected,
    )
