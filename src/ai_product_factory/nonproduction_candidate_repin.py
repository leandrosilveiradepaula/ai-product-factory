"""Fail-closed GitHub-verified reconciliation of a nonproduction candidate SHA."""
from __future__ import annotations

import json
import re
from urllib import request
from .github_auth import resolve_github_token
from .github_rest import GitHubRestAdapter
from .supabase_server import resolve_supabase_server_config

_SHA = re.compile(r"^[a-f0-9]{40}$")


def verify_candidate(github, *, repository, branch, number, old_sha, new_sha):
    if not all(_SHA.fullmatch(x or "") for x in (old_sha, new_sha)) or old_sha == new_sha:
        raise PermissionError("invalid candidate transition")
    if github.repository != repository:
        raise PermissionError("candidate repository mismatch")
    if github.get_branch_sha(branch) != new_sha:
        raise PermissionError("candidate branch moved")
    pr = github.get_pull_request(number)
    if (pr.state != "open" or pr.merged or pr.head_sha != new_sha
        or pr.head_ref != branch or pr.head_repository != repository
        or pr.base_ref != "main" or pr.number != number):
        raise PermissionError("candidate PR not verified")
    comparison = github.compare_commits(old_sha, new_sha)
    if (comparison.get("status") != "ahead" or type(comparison.get("ahead_by")) is not int
        or not 1 <= comparison["ahead_by"] <= 10000 or comparison.get("behind_by") != 0):
        raise PermissionError("candidate SHA is not a strict descendant")
    # Do not use Vercel success or feedback checks as CI evidence.
    rows = github._call("GET", f"/repos/{repository}/actions/runs",
                        query={"head_sha":new_sha,"per_page":"100"})
    runs = rows.get("workflow_runs") if isinstance(rows, dict) else None
    eligible = [r for r in runs or [] if r.get("name") == "CRM validation"
        and r.get("head_sha") == new_sha and r.get("status") == "completed"
        and r.get("conclusion") == "success"
        and r.get("head_branch") == branch]
    if not eligible:
        raise PermissionError("required exact-SHA CI workflow is not successful")
    selected = max(eligible, key=lambda r: int(r.get("id") or 0))
    return {
        "source":"github_actions_exact_sha","repository":repository,"branch":branch,
        "pr_number":str(number),"pr_head_sha":new_sha,"branch_head_sha":new_sha,
        "expected_sha":old_sha,"new_sha":new_sha,"pr_base":"main","pr_state":"open",
        "compare_status":"ahead","ahead_by":comparison["ahead_by"],"behind_by":0,
        "ci_conclusion":"success","ci_sha":new_sha,"ci_run_id":selected["id"],
    }


def repin_one(project_key="crm-infodive", *, github_factory=None, rpc=None):
    if project_key != "crm-infodive":
        raise PermissionError("only the explicitly approved CRM pilot is eligible")
    cfg = resolve_supabase_server_config()
    def post(name, body):
        data = json.dumps(body).encode()
        req = request.Request(cfg.url+"/rest/v1/rpc/"+name, data=data, method="POST",
                              headers={**cfg.headers,"Content-Type":"application/json"})
        with request.urlopen(req, timeout=30) as response:
            return json.loads(response.read() or b"null")
    if rpc is None:
        rpc=post
    # A read-only database lookup never rewrites historical evidence.
    req=request.Request(
        cfg.url+"/rest/v1/factory_projects?select=id,project_key,repository,project_kind,is_active,manifest&project_key=eq.crm-infodive&limit=1",
        headers=cfg.headers)
    with request.urlopen(req, timeout=30) as response:
        rows=json.loads(response.read())
    if len(rows)!=1:
        raise PermissionError("CRM project not uniquely registered")
    project=rows[0]
    if project.get("project_kind")!="existing" or project.get("is_active") is not True:
        raise PermissionError("CRM project not active existing project")
    target=(project.get("manifest") or {}).get("delivery_target") or {}
    repository=project.get("repository")
    if (repository!="leandrosilveiradepaula/crm-infodive"
        or target.get("repository")!=repository
        or target.get("branch")!="preview/hardening-release-candidate"
        or target.get("candidate_pr_number")!=56
        or target.get("mode")!="open_pr_candidate"):
        raise PermissionError("CRM candidate policy not recognized")
    ctrl=request.Request(
        cfg.url+"/rest/v1/factory_project_execution_controls?select=state,generation,version&project_id=eq."+project["id"]+"&limit=1",
        headers=cfg.headers)
    with request.urlopen(ctrl,timeout=30) as response:
        controls=json.loads(response.read())
    if len(controls)!=1 or controls[0]["state"]!="running":
        raise PermissionError("CRM controller not running")
    g=github_factory(repository) if github_factory else GitHubRestAdapter(
        repository=repository,token=resolve_github_token(repository))
    new_sha=g.get_branch_sha(target["branch"])
    old_sha=target["sha"]
    if new_sha==old_sha:
        return {"status":"unchanged","project_key":project_key,"sha":new_sha}
    evidence=verify_candidate(
        g, repository=repository,branch=target["branch"],number=56,
        old_sha=old_sha,new_sha=new_sha)
    return rpc("factory_repin_nonproduction_target_v1",{
        "p_project_key":project_key,"p_expected_sha":old_sha,
        "p_new_sha":new_sha,"p_expected_generation":controls[0]["generation"],
        "p_expected_version":controls[0]["version"],
        "p_evidence":evidence,"p_actor_ref":"factory-candidate-reconciler"})
