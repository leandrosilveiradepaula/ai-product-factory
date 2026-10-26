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
COMMIT_PAGE_SIZE = 100  # GitHub REST hard max for commit files per page.
MAX_COMMIT_PAGES = 30  # 3000-file upper bound; full last page is ambiguous.
# Same Vercel status identity required by scripts/console_visual_origin.mjs.
# A successful GitHub status for an unrelated tenant is not Factory evidence.
OWNED_VERCEL_STATUS = re.compile(
    r"https://vercel\.com/leandros-projects-102e32ab/ai-product-factory-console/[A-Za-z0-9]{20,40}\Z",
    re.ASCII,
)
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


def _validated_workflow_jobs(payload: object, sha: str, run_id: int) -> dict:
    """Validate the ACTUAL completed validate jobs, never arbitrary check names.

    Check-runs for the same commit can contain historical retries or the
    currently running observer itself; those do not replace the trusted CI run.
    """
    if (not isinstance(payload,dict) or type(payload.get("total_count")) is not int
            or payload["total_count"] < 1 or payload["total_count"] > MAX_CHECKS
            or not isinstance(payload.get("jobs"),list)
            or len(payload["jobs"]) != payload["total_count"]):
        raise GlobalReadinessEvidenceError("missing or incomplete validation jobs")
    actual = set()
    for row in payload["jobs"]:
        if (not isinstance(row,dict) or row.get("head_sha") != sha
                or row.get("run_id") != run_id or type(row.get("id")) is not int
                or row["id"] <= 0 or not isinstance(row.get("name"),str)
                or not re.fullmatch(r"[a-zA-Z0-9_. -]{1,80}",row["name"],re.ASCII)):
            raise GlobalReadinessEvidenceError("validation job identity mismatch")
        name = row["name"]
        if name in actual or row.get("status") != "completed" or row.get("conclusion") != "success":
            raise GlobalReadinessEvidenceError("duplicate, failing or unfinished validation job")
        actual.add(name)
    # Only this repository's validate workflow is observed by this trusted
    # workflow-run lane. Its declared job names are mandatory, not advisory.
    if not {"test","factory-acceptance"}.issubset(actual):
        raise GlobalReadinessEvidenceError("required Factory validation jobs missing")
    return {"validated_run_id":run_id,"jobs":sorted(actual),
            "verification_state":"executed_same_SHA",
            "required_gates":["test","factory-acceptance"]}


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



MAX_SHA_WORKFLOW_RUNS = 100
MAX_VISUAL_ARTIFACTS = 10
VISUAL_WORKFLOW = "Authenticated Console visual evidence"
VISUAL_WORKFLOW_PATH = ".github/workflows/authenticated-visual-evidence.yml"


def _same_sha_runs(repository: str, sha: str, github_get) -> list[dict]:
    """Read only same-SHA *push* workflows, not all comment/schedule runs.

    GitHub issue comments and scheduled workflows reuse the current main
    SHA. Their count is unbounded while that SHA stays unchanged. Those
    unrelated runs must never exhaust the 100-run verification window and
    permanently block an otherwise valid product audit.
    """
    payload = github_get("/repos/"+repository+"/actions/runs?head_sha="+sha+"&event=push&per_page=100")
    if (not isinstance(payload, dict)
            or type(payload.get("total_count")) is not int
            or payload["total_count"] > MAX_SHA_WORKFLOW_RUNS
            or payload["total_count"] < 1
            or not isinstance(payload.get("workflow_runs"),list)
            or len(payload["workflow_runs"]) != payload["total_count"]):
        raise GlobalReadinessEvidenceError("unverifiable same-SHA workflow inventory")
    runs = payload["workflow_runs"]
    if any(not isinstance(row,dict) or row.get("head_sha") != sha
           or row.get("event") != "push"
           or (row.get("repository") or {}).get("full_name") != repository
           or type(row.get("id")) is not int or row["id"] <= 0 for row in runs):
        raise GlobalReadinessEvidenceError("cross-SHA/repository workflow inventory")
    if len({row["id"] for row in runs}) != len(runs):
        raise GlobalReadinessEvidenceError("duplicate workflow run identity")
    return runs


def find_current_validation_run(*,repository: str,sha: str,branch: str,github_get) -> int:
    """An authenticated visual event cannot substitute itself for validate."""
    candidates = [x for x in _same_sha_runs(_repo(repository),_sha(sha),github_get)
                  if x.get("name") == "validate" and x.get("event") == "push"
                  and x.get("path") == ".github/workflows/validate.yml"
                  and x.get("head_branch") == branch]
    if len(candidates) != 1 or candidates[0].get("status") != "completed" or candidates[0].get("conclusion") != "success":
        raise GlobalReadinessEvidenceError("exact successful main validate run missing or ambiguous")
    return candidates[0]["id"]


def _workflow_jobs(github_get, prefix: str, run_id: int, sha: str, expected: set[str]) -> list[str]:
    payload = github_get(prefix+"/actions/runs/"+str(run_id)+"/jobs?per_page=100")
    if (not isinstance(payload,dict) or type(payload.get("total_count")) is not int
            or not 1 <= payload["total_count"] <= MAX_CHECKS
            or not isinstance(payload.get("jobs"),list)
            or len(payload["jobs"]) != payload["total_count"]):
        raise GlobalReadinessEvidenceError("incomplete executed workflow jobs")
    names = []
    for job in payload["jobs"]:
        if (not isinstance(job,dict) or job.get("run_id") != run_id
                or job.get("head_sha") != sha or type(job.get("id")) is not int
                or job["id"] <= 0 or not isinstance(job.get("name"),str)
                or job.get("status") != "completed" or job.get("conclusion") != "success"):
            raise GlobalReadinessEvidenceError("job identity or execution not verified")
        names.append(job["name"])
    if len(set(names)) != len(names) or not expected.issubset(set(names)):
        raise GlobalReadinessEvidenceError("expected executed jobs missing or duplicated")
    return sorted(names)


def _authenticated_visual_receipt(runs: list[dict],*,repo: str,sha: str,
                                  branch: str,prefix: str,github_get,
                                  expected_run_id: int | None = None) -> dict:
    relevant = [x for x in runs if x.get("name") == VISUAL_WORKFLOW and x.get("event") == "push"
                and x.get("head_branch") == branch]
    if len(relevant) > 1:
        raise GlobalReadinessEvidenceError("ambiguous authenticated visual workflow")
    if not relevant:
        if expected_run_id is not None:
            raise GlobalReadinessEvidenceError("visual trigger has no matching exact-SHA run")
        return {"status":"not_observed","scope":"not_an_executed_browser_audit"}
    row = relevant[0]
    rid = row["id"]
    if (row.get("path") != VISUAL_WORKFLOW_PATH or row.get("run_attempt") != 1
            or (expected_run_id is not None and expected_run_id != rid)):
        raise GlobalReadinessEvidenceError("untrusted or replayed authenticated visual provenance")
    if row.get("status") != "completed":
        if expected_run_id is not None:
            raise GlobalReadinessEvidenceError("visual completion event references unfinished run")
        return {"status":"pending","workflow_run_id":rid,"source":"github_exact_sha_workflow"}
    if row.get("conclusion") != "success":
        return {"status":"failed","workflow_run_id":rid,
                "reason_code":"authenticated_browser_audit_not_successful",
                "source":"github_exact_sha_workflow"}
    jobs = _workflow_jobs(github_get,prefix,rid,sha,{"capture"})
    artifacts = github_get(prefix+"/actions/runs/"+str(rid)+"/artifacts?per_page=100")
    if (not isinstance(artifacts,dict) or type(artifacts.get("total_count")) is not int
            or not 1 <= artifacts["total_count"] <= MAX_VISUAL_ARTIFACTS
            or not isinstance(artifacts.get("artifacts"),list)
            or len(artifacts["artifacts"]) != artifacts["total_count"]):
        raise GlobalReadinessEvidenceError("missing or incomplete encrypted browser receipt")
    matches = [a for a in artifacts["artifacts"] if isinstance(a,dict)
               and a.get("name") == "authenticated-console-"+str(rid)]
    if len(matches) != 1:
        raise GlobalReadinessEvidenceError("missing or duplicate authenticated visual artifact")
    a = matches[0]
    provenance = a.get("workflow_run")
    if (type(a.get("id")) is not int or a["id"] <= 0 or a.get("expired") is not False
            or type(a.get("size_in_bytes")) is not int or a["size_in_bytes"] < 1
            or not isinstance(provenance,dict)
            or provenance.get("id") != rid or provenance.get("head_sha") != sha
            or provenance.get("head_branch") != branch):
        raise GlobalReadinessEvidenceError("encrypted visual artifact identity mismatch")
    # The encrypted payload is never read or decrypted here. A completed
    # trusted workflow + successful capture job + same-SHA artifact is
    # operational evidence, not an independent full UI accessibility audit.
    return {"status":"verified","workflow_run_id":rid,"artifact_id":a["id"],
            "executed_jobs":jobs,"scope":"trusted_authenticated_browser_suite",
            "source":"github_exact_sha_workflow_and_encrypted_artifact"}


def _verified_console_change_scope(prefix: str, sha: str, git_commit: dict,
                                   github_get) -> dict:
    """Prove Console file impact using the entire paged first-parent commit diff.

    GitHub silently caps per_page at 100 even when asked for 300. Each page
    repeats the immutable commit SHA and parents; verify every page. Never
    infer Preview N/A from an incomplete page or an exhausted 3000-file cap.
    """
    git_parents = git_commit.get("parents")
    if (not isinstance(git_parents,list) or not 1 <= len(git_parents) <= 8
            or any(not isinstance(x,dict) or not isinstance(x.get("sha"),str)
                   or SHA.fullmatch(x["sha"]) is None for x in git_parents)):
        raise GlobalReadinessEvidenceError("exact commit has invalid parent provenance")
    expected_parents = [x["sha"] for x in git_parents]
    seen: set[str] = set()
    console_changed = False
    allowed = {"added","modified","removed","renamed","copied","changed"}

    def safe_path(value: object) -> bool:
        return (isinstance(value,str) and 0 < len(value) <= 1024
                and not value.startswith("/") and ".." not in value.split("/")
                and "\x00" not in value and "\n" not in value)

    for page in range(1,MAX_COMMIT_PAGES+1):
        info = github_get(prefix+"/commits/"+sha+f"?per_page={COMMIT_PAGE_SIZE}&page={page}")
        if (not isinstance(info,dict) or info.get("sha") != sha
                or not isinstance(info.get("parents"),list)
                or len(info["parents"]) != len(expected_parents)
                or [x.get("sha") for x in info["parents"] if isinstance(x,dict)]
                != expected_parents):
            raise GlobalReadinessEvidenceError("GitHub commit changed-file identity mismatch")
        rows = info.get("files")
        if (not isinstance(rows,list) or len(rows)>COMMIT_PAGE_SIZE
                or (page == 1 and not rows)):
            raise GlobalReadinessEvidenceError("commit file inventory missing or malformed")
        for row in rows:
            if not isinstance(row,dict) or row.get("status") not in allowed:
                raise GlobalReadinessEvidenceError("commit file has unverifiable change status")
            name, previous = row.get("filename"), row.get("previous_filename")
            if not safe_path(name) or name in seen:
                raise GlobalReadinessEvidenceError("commit file inventory has invalid or duplicate path")
            seen.add(name)
            if row["status"] in {"renamed","copied"}:
                if not safe_path(previous):
                    raise GlobalReadinessEvidenceError("rename missing trusted previous path")
            elif previous is not None:
                raise GlobalReadinessEvidenceError("unexpected previous path on commit file")
            if name.startswith("apps/console/") or (
                    isinstance(previous,str) and previous.startswith("apps/console/")):
                console_changed = True
        if len(rows) < COMMIT_PAGE_SIZE:
            return {"console_changed": console_changed, "changed_files":len(seen),
                    "pages_verified":page, "source":"github_exact_sha_first_parent_diff",
                    "scope":"preview_applicability_only_not_deployment_state"}
    raise GlobalReadinessEvidenceError("commit file inventory exceeds verified pagination bound")


def _same_sha_provider_status(prefix: str,sha: str,github_get,*,console_changed: bool) -> dict:
    payload = github_get(prefix+"/commits/"+sha+"/status")
    if (not isinstance(payload,dict) or payload.get("sha") != sha
            or not isinstance(payload.get("statuses"),list)):
        raise GlobalReadinessEvidenceError("same-SHA deployment status unavailable")
    matches = [x for x in payload["statuses"] if isinstance(x,dict)
               and x.get("context") == "Vercel"]
    if len(matches) > 1:
        raise GlobalReadinessEvidenceError("ambiguous same-SHA Vercel commit status")
    if not matches:
        return {"status":"not_applicable" if not console_changed else "not_reported",
                "reason_code":"no_console_change_exact_commit" if not console_changed else "provider_status_absent",
                "deployment_verified":False,"scope":"provider_status_only"}
    status = matches[0].get("state")
    if status not in ("success","pending","error","failure"):
        raise GlobalReadinessEvidenceError("unexpected provider commit status")
    # A generic "Vercel" context is attacker-controllable across other
    # deployments. Health JSON alone and provider context name are NOT tenant
    # identity; never promote an unrelated project to operational evidence.
    target = matches[0].get("target_url")
    if (not isinstance(target,str) or len(target) > 250
            or OWNED_VERCEL_STATUS.fullmatch(target) is None):
        raise GlobalReadinessEvidenceError("Vercel status outside owned Console project")
    # Vercel can emit GitHub status=success even for a CANCELED deployment
    # whose build was intentionally ignored (verified live for #1107).
    # Do not translate that provider-only signal into deployed/READY.
    # For exact commits with no apps/console changes, Preview is N/A.
    return {"status": ("not_applicable" if not console_changed else {
                "success":"provider_status_success_unverified",
                "pending":"pending","error":"failed","failure":"failed"}[status]),
            "reason_code":"no_console_change_exact_commit" if not console_changed else "provider_status_only",
            "provider_reported_state":status,"deployment_verified":False,
            "provider":"Vercel","project_identity":"pinned_team_and_project",
            "scope":"github_commit_status_not_live_deployment"}


def observe_current_product(*, repository: str, sha: str, validation_run_id: int,
                            github_get, cp_get, visual_trigger_run_id: int | None = None) -> dict:
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
            or run.get("path") != ".github/workflows/validate.yml"
            or run.get("head_branch") != branch or run.get("head_sha") != sha
            or run.get("conclusion") != "success" or run.get("status") != "completed"
            or (run.get("repository") or {}).get("full_name") != repository):
        raise GlobalReadinessEvidenceError("validation workflow is not completed for exact HEAD")
    commit = github_get(prefix+"/git/commits/"+sha)
    tree_sha = (commit.get("tree") or {}).get("sha") if isinstance(commit,dict) else None
    if not isinstance(commit,dict) or commit.get("sha") != sha or not isinstance(tree_sha,str) or SHA.fullmatch(tree_sha) is None:
        raise GlobalReadinessEvidenceError("immutable Git commit/tree proof missing")
    inventory = _inventory(_paths(github_get(prefix+"/git/trees/"+tree_sha+"?recursive=1"),tree_sha))
    console_scope = _verified_console_change_scope(prefix,sha,commit,github_get)
    checks = _check_runs(github_get(prefix+"/commits/"+sha+"/check-runs?per_page=100"),sha)
    validated_jobs = _validated_workflow_jobs(
        github_get(prefix+"/actions/runs/"+str(validation_run_id)+"/jobs?per_page=100"),
        sha,validation_run_id,
    )
    live_runs = _same_sha_runs(repository,sha,github_get)
    visual = _authenticated_visual_receipt(
        live_runs,repo=repository,sha=sha,branch=branch,prefix=prefix,
        github_get=github_get,expected_run_id=visual_trigger_run_id,
    )
    production = _same_sha_provider_status(prefix,sha,github_get,
                                           console_changed=console_scope["console_changed"])
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
    # A recorded pass cannot defeat a contradictory, newer same-SHA visual
    # or deployment failure. A non-passing visual run is not a certification.
    if passed and (visual["status"] in ("failed","pending")
                   or production["status"] in ("failed","pending")):
        passed = False
        summary = {**summary,"ready":False,"status":"not_ready",
                   "reason":"current SHA has contradictory or unfinished operational evidence"}
    unverified = [
        d for d in REQUIRED_DOMAINS
        if not passed or summary.get("domains",{}).get(d,{}).get("status") not in ("passed","not_applicable")
    ]
    next_actions = dict(NEXT_ACTION)
    if visual["status"] == "verified":
        next_actions["product_experience"] = "review_full_product_surface_inventory_and_accessibility_gaps"
        next_actions["test_strategy"] = "verify_other_critical_journeys_and_cross_project_regressions"
    if production["status"] == "provider_status_success_unverified":
        next_actions["observability_operations"] = "verify_live_deployment_incidents_recovery_and_rollback"
    work_plan = [{
        "domain": d, "required_coverage": list(REQUIRED_COVERAGE_BY_DOMAIN[d]),
        "next_step": next_actions[d], "work_type":"independent_verification",
        "observed_evidence": (
            (["exact_sha_ci"] if d == "test_strategy" else []) +
            (["authenticated_console_browser"] if visual["status"] == "verified"
             and d in ("test_strategy","product_experience") else []) +
            (["vercel_provider_status_unverified"] if production["status"] == "provider_status_success_unverified"
             and d == "observability_operations" else [])
        ),
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
        "source_inventory":inventory, "ci_evidence":{**checks,"validation_jobs":validated_jobs},
        "current_sha_operational_evidence":{
            "console_change_scope":console_scope,
            "ci":{"status":"verified","validated_run_id":validation_run_id,
                  "source":"completed_validate_jobs"},
            "authenticated_console":visual,
            "production_deployment":production,
            "scope":"executed_signals_not_product_readiness_attestation",
        },
        "evidence_scope":"independent_github_and_control_plane_read_only",
        "work_proposals":work_plan,"writes":0,"paid_calls":0,
    }
