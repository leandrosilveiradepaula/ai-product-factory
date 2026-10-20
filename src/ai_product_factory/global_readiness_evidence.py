"""Current-HEAD global product evidence, independent of candidate release readiness.

Read-only observer. It never creates a product audit or promotes artifact
inventory to a passed six-domain assessment. A promotion requires an independent
durable evaluation bound to this project and SHA and the existing strict
release-intelligence policy.
"""
from __future__ import annotations

import re
from urllib.parse import quote

from .product_readiness import REQUIRED_DOMAINS, REQUIRED_COVERAGE_BY_DOMAIN
from .release_intelligence import _verified_product_assessment

SHA = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
UUID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\Z", re.ASCII)
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z", re.ASCII)
MAX_FILES = 100000
MAX_CHECKS = 100
MAX_EVALUATIONS = 2
# These *domain questions* are generic. No client/schema names or mock passes.
NEXT_ACTION = {
    "security": "verify_auth_authorization_tenant_rls_and_secrets",
    "observability_operations": "execute_health_recovery_alerting_and_rollback_checks",
    "test_strategy": "verify_unit_integration_regressions_and_authenticated_e2e",
    "product_experience": "verify_ui_inventory_mobile_accessibility_and_states",
    "documentation": "review_setup_operations_and_release_rollback_runbooks",
    "functional_completeness": "verify_requirements_inherited_debt_and_critical_journeys",
}


class GlobalReadinessEvidenceError(RuntimeError):
    """Unverifiable remote provenance; details intentionally non-sensitive."""


def _one(rows: object, kind: str, *, optional: bool = False) -> dict | None:
    if not isinstance(rows, list) or len(rows) > 1 or any(not isinstance(x, dict) for x in rows):
        raise GlobalReadinessEvidenceError("incomplete or ambiguous " + kind)
    if not rows:
        if optional:
            return None
        raise GlobalReadinessEvidenceError("missing " + kind)
    return rows[0]


def _repo(repository: object) -> str:
    if (not isinstance(repository, str) or not REPO.fullmatch(repository)
            or any(s in {".", ".."} for s in repository.split("/"))):
        raise ValueError("invalid repository")
    return repository


def _sha(value: object) -> str:
    if not isinstance(value, str) or SHA.fullmatch(value) is None:
        raise ValueError("invalid 40-character candidate SHA")
    return value


def _uuid(value: object) -> str:
    if not isinstance(value, str) or UUID.fullmatch(value) is None:
        raise GlobalReadinessEvidenceError("invalid Control Plane identity")
    return value


def _paths(tree: object, expected_tree: str) -> tuple[str, ...]:
    if (not isinstance(tree, dict) or tree.get("sha") != expected_tree
            or tree.get("truncated") is not False or not isinstance(tree.get("tree"), list)):
        raise GlobalReadinessEvidenceError("Git tree is missing, truncated or changed")
    paths = []
    for node in tree["tree"]:
        if not isinstance(node, dict):
            raise GlobalReadinessEvidenceError("invalid Git tree node")
        if node.get("type") == "tree" and node.get("mode") == "040000":
            continue
        if node.get("type") != "blob" or node.get("mode") not in ("100644", "100755"):
            raise GlobalReadinessEvidenceError("symlink or submodule not inventoried")
        name = node.get("path")
        if (not isinstance(name, str) or not name or name.startswith("/")
                or ".." in name.split("/") or "\x00" in name or "\n" in name
                or len(name) > 1024):
            raise GlobalReadinessEvidenceError("unsafe Git tree path")
        paths.append(name)
    if not paths or len(paths) > MAX_FILES or len(set(paths)) != len(paths):
        raise GlobalReadinessEvidenceError("empty, duplicate or oversized Git tree")
    return tuple(paths)


def _inventory(paths: tuple[str, ...]) -> dict:
    low = tuple(x.lower() for x in paths)
    return {
        "tracked_files": len(low),
        "source_files": sum(x.startswith(("src/","app/","apps/","pages/","lib/","packages/")) for x in low),
        "test_files": sum(x.startswith(("tests/","test/","e2e/","scripts/tests/"))
                          or x.endswith((".test.ts",".test.tsx",".test.js",".spec.ts",".spec.tsx",".spec.js")) for x in low),
        "route_files": sum(x.endswith(("/page.tsx","/page.ts","/route.ts","/route.tsx")) for x in low),
        "workflow_files": sum(x.startswith(".github/workflows/") and x.endswith((".yml",".yaml")) for x in low),
        "migration_files": sum(x.startswith(("supabase/migrations/","migrations/","db/migrations/","prisma/migrations/")) for x in low),
        "documents_present": {
            "operations": "docs/operations.md" in low,
            "readiness_contract": "docs/product_readiness.md" in low,
            "project_plan": "project_plan.md" in low,
        },
        "verification_scope": "file_inventory_not_executed_domain_audit",
    }


def _check_runs(payload: object, sha: str) -> dict:
    if (not isinstance(payload, dict) or type(payload.get("total_count")) is not int
            or payload["total_count"] < 1 or payload["total_count"] > MAX_CHECKS
            or not isinstance(payload.get("check_runs"), list)
            or len(payload["check_runs"]) != payload["total_count"]):
        raise GlobalReadinessEvidenceError("incomplete GitHub check-run evidence")
    successful = []
    incomplete = 0
    failures = 0
    for row in payload["check_runs"]:
        if not isinstance(row, dict) or row.get("head_sha") != sha:
            raise GlobalReadinessEvidenceError("check-run SHA mismatch")
        status, conclusion = row.get("status"), row.get("conclusion")
        if status != "completed":
            incomplete += 1
        elif conclusion != "success":
            failures += 1
        else:
            name = row.get("name")
            if isinstance(name, str) and re.fullmatch(r"[a-zA-Z0-9_. -]{1,80}", name, re.ASCII):
                successful.append(name)
    return {"successful_check_names": sorted(set(successful))[:MAX_CHECKS],
            "incomplete": incomplete, "non_success": failures,
            "checks_observed": payload["total_count"], "source":"github_exact_commit_checks"}


def _valid_linked_evaluation(*, project_id: str, sha: str,
                             kind: str, cp_get) -> dict | None:
    # Evaluation status and baseline_ref are authoritative *columns*, never
    # copied from the evaluation's untrusted JSON result.
    rows = cp_get(
        "factory_evaluations?select=id,run_id,status,baseline_ref,result"
        + "&eval_type=eq." + quote(kind, safe="")
        + "&baseline_ref=eq." + sha + "&order=created_at.desc&limit=2"
    )
    row = _one(rows, kind, optional=True)
    if row is None:
        return None
    rid = _uuid(row.get("run_id"))
    run = _one(cp_get("factory_runs?select=id,task_id&id=eq."+rid+"&limit=2"),"evaluation run")
    task_id = _uuid(run.get("task_id"))
    task = _one(cp_get("factory_tasks?select=id,project_id&id=eq."+task_id+"&limit=2"),"evaluation task")
    if task.get("project_id") != project_id:
        raise GlobalReadinessEvidenceError("cross-project evaluation")
    if row.get("baseline_ref") != sha:
        raise GlobalReadinessEvidenceError("evaluation SHA drift")
    return {"evaluation_status":row.get("status"),"baseline_ref":row.get("baseline_ref"),
            "result":row.get("result")}


def observe_current_product(*, repository: str, sha: str, validation_run_id: int,
                            github_get, cp_get) -> dict:
    """Correlate production HEAD, exact CI, Control Plane owner and independent eval."""
    repository = _repo(repository)
    sha = _sha(sha)
    if type(validation_run_id) is not int or validation_run_id < 1:
        raise ValueError("invalid completed validation workflow run ID")
    project = _one(cp_get(
        "factory_projects?select=id,project_key,repository,project_kind,lifecycle_stage,is_active"
        "&repository=eq."+quote(repository,safe="")+"&limit=2"
    ),"Control Plane project")
    pid = _uuid(project.get("id"))
    if project.get("repository") != repository or not isinstance(project.get("project_key"), str):
        raise GlobalReadinessEvidenceError("Control Plane project/repository mismatch")
    kind = project.get("project_kind")
    if not isinstance(kind, str) or not kind:
        raise GlobalReadinessEvidenceError("project kind unknown")
    prefix = "/repos/"+repository
    remote = github_get(prefix)
    branch = remote.get("default_branch") if isinstance(remote,dict) else None
    if (not isinstance(remote,dict) or remote.get("full_name") != repository
            or not isinstance(branch,str) or not re.fullmatch(r"[a-zA-Z0-9._/-]{1,100}",branch)):
        raise GlobalReadinessEvidenceError("GitHub repository identity not verified")
    head = github_get(prefix+"/git/ref/heads/"+quote(branch,safe=""))
    if not isinstance(head,dict) or (head.get("object") or {}).get("sha") != sha:
        raise GlobalReadinessEvidenceError("audited branch moved or SHA mismatch")
    run = github_get(prefix+"/actions/runs/"+str(validation_run_id))
    if (not isinstance(run,dict) or run.get("id") != validation_run_id
            or run.get("name") != "validate" or run.get("event") != "push"
            or run.get("head_branch") != branch or run.get("head_sha") != sha
            or run.get("conclusion") != "success" or run.get("status") != "completed"
            or (run.get("repository") or {}).get("full_name") != repository):
        raise GlobalReadinessEvidenceError("validation workflow is not completed for exact HEAD")
    commit = github_get(prefix+"/git/commits/"+sha)
    tree_sha = (commit.get("tree") or {}).get("sha") if isinstance(commit,dict) else None
    if not isinstance(commit,dict) or commit.get("sha") != sha or not isinstance(tree_sha,str) or SHA.fullmatch(tree_sha) is None:
        raise GlobalReadinessEvidenceError("immutable Git commit/tree proof missing")
    inventory = _inventory(_paths(github_get(prefix+"/git/trees/"+tree_sha+"?recursive=1"),tree_sha))
    checks = _check_runs(github_get(prefix+"/commits/"+sha+"/check-runs?per_page=100"),sha)
    evaluation = _valid_linked_evaluation(project_id=pid,sha=sha,
                                         kind="product_readiness",cp_get=cp_get)
    baseline = (_valid_linked_evaluation(project_id=pid,sha=sha,
        kind="existing_project_baseline",cp_get=cp_get) if kind=="existing" else None)
    # Existing policy remains the single readiness contract. This read-only
    # observer does not persist evaluation rows or generate missing attestation.
    summary, passed = _verified_product_assessment(
        {**(evaluation["result"] if evaluation and isinstance(evaluation.get("result"),dict) else {}),
         "evaluation_status":evaluation.get("evaluation_status") if evaluation else None,
         "baseline_ref":evaluation.get("baseline_ref") if evaluation else None},
        sha,project_kind=kind,existing_baseline=baseline
    ) if evaluation else ({"status":"not_assessed","ready":False},False)
    unverified = [
        d for d in REQUIRED_DOMAINS
        if not passed or summary.get("domains",{}).get(d,{}).get("status") not in ("passed","not_applicable")
    ]
    work_plan = [{
        "domain": d, "required_coverage": list(REQUIRED_COVERAGE_BY_DOMAIN[d]),
        "next_step": NEXT_ACTION[d], "work_type":"independent_verification",
        "start_authorized": False, "paid_calls_authorized": False,
    } for d in unverified]
    if kind=="existing" and not passed:
        work_plan.append({
            "domain":"existing_project_baseline",
            "required_coverage":["repository_inventory","inherited_debt","critical_journeys"],
            "next_step":"verify_existing_repository_and_target_data_boundaries",
            "work_type":"independent_verification","start_authorized":False,
            "paid_calls_authorized":False,
        })
    # A passing evaluation is still bounded by current SHA + CI and accepted
    # only through the existing exact-sha six-domain assessment.
    return {
        "schema_version": 1, "project_key": project["project_key"],"project_kind":kind,
        "repository":repository,"branch":branch,"assessed_commit":sha,
        "validation_workflow_run_id":validation_run_id,
        "global_readiness": {
            "status":"passed" if passed else "not_assessed" if evaluation is None else "not_ready",
            "product_ready": bool(passed),
            "independent_evaluation_recorded": evaluation is not None,
            "missing_or_unverified_domains":unverified,
            "blockers": len(work_plan),
            "scope":"entire_product_at_exact_current_head",
        },
        "source_inventory":inventory, "ci_evidence":checks,
        "evidence_scope":"independent_github_and_control_plane_read_only",
        "work_proposals":work_plan,"writes":0,"paid_calls":0,
    }
