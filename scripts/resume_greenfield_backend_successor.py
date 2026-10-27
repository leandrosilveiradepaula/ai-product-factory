#!/usr/bin/env python3
"""Read-only exact-SHA preflight for a failed greenfield Preview after a new commit.

The optional effectful RPC is restricted to a separately approved Control
Plane migration, explicit operator acknowledgement and a fresh 200/401 JSON
session probe. Never copy staging credentials into Factory or GitHub.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

from ai_product_factory.github_auth import resolve_github_token
from ai_product_factory.supabase_server import resolve_supabase_server_config
from ai_product_factory.preview_session_probe import (
    PreviewEnvironmentNotReady, probe_session, preview_origin,
)

SHA = re.compile(r"^[0-9a-f]{40}$")
REPO = re.compile(r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$")
VERCEL = re.compile(
    r"^https://vercel\.com/[a-zA-Z0-9-]+/[a-zA-Z0-9-]+/([a-zA-Z0-9]{20,40})$"
)
EXPECTED_WORKFLOW = ".github/workflows/service-desk-ci.yml"


def one(rows, label: str) -> dict:
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise PreviewEnvironmentNotReady(label + "_not_unique")
    return rows[0]


def prepare_successor(*, run_id: str, project_key: str, preview_url: str,
                      cp_get: Callable, github_get: Callable,
                      session_probe: Callable) -> dict:
    """Refuse any drift BEFORE the outbound session GET."""
    if project_key != "infodive-service-desk":
        raise PreviewEnvironmentNotReady("unknown_greenfield_project")
    from uuid import UUID
    try:
        if str(UUID(run_id)) != run_id:
            raise ValueError()
    except (ValueError, TypeError) as exc:
        raise PreviewEnvironmentNotReady("invalid_run_id") from exc
    url = preview_origin(preview_url)
    if url != preview_url:
        raise PreviewEnvironmentNotReady("preview_url_not_canonical")

    run = one(cp_get("factory_runs", {
        "select": "id,task_id,status,candidate_commit,branch_name,metadata",
        "id": "eq." + run_id, "limit": "2",
    }), "run")
    previous = run.get("candidate_commit")
    branch = run.get("branch_name")
    if (run.get("id") != run_id or run.get("status") != "failed"
        or not isinstance(previous, str) or not SHA.fullmatch(previous)
        or not isinstance(branch, str) or not branch.startswith("factory/change-set-")):
        raise PreviewEnvironmentNotReady("original_failed_run_drift")
    task = one(cp_get("factory_tasks", {
        "select": "id,project_id,status", "id": "eq." + str(run["task_id"]),
        "limit": "2",
    }), "task")
    if task.get("status") != "failed":
        raise PreviewEnvironmentNotReady("failed_task_drift")
    project = one(cp_get("factory_projects", {
        "select": "id,project_key,project_kind,is_active,repository,manifest",
        "id": "eq." + str(task["project_id"]), "limit": "2",
    }), "project")
    repository = project.get("repository")
    if (project.get("project_key") != project_key
        or project.get("project_kind") != "greenfield" or project.get("is_active") is not True
        or not isinstance(repository, str) or not REPO.fullmatch(repository)
        or ((project.get("manifest") or {}).get("preview") or {}).get("required") is not True):
        raise PreviewEnvironmentNotReady("project_preview_policy_drift")
    cs = one(cp_get("factory_change_sets", {
        "select": "id,status,release_run_id,integration_branch,candidate_commit,metadata",
        "release_run_id": "eq." + run_id,"limit":"2",
    }), "change_set")
    meta = cs.get("metadata") or {}
    request = meta.get("integration_release_request") or {}
    epoch = meta.get("integration_epoch_receipt") or {}
    pr_number = request.get("pr_number")
    if (cs.get("status") != "ci_pending" or cs.get("candidate_commit") != previous
        or cs.get("integration_branch") != branch or cs.get("release_run_id") != run_id
        or request.get("candidate_commit") != previous
        or request.get("branch") != branch
        or epoch.get("candidate_commit") != previous
        or run.get("metadata", {}).get("change_set_id") != cs.get("id")
        or type(pr_number) is not int or pr_number < 1):
        raise PreviewEnvironmentNotReady("change_set_sha_or_epoch_drift")

    evaluation = one(cp_get("factory_evaluations", {
        "select": "status,baseline_ref,result",
        "run_id": "eq."+run_id,"eval_type":"eq.browser_e2e",
        "order":"created_at.desc,id.desc","limit":"1",
    }), "browser")
    old_url = evaluation.get("baseline_ref")
    if (evaluation.get("status") != "failure"
        or "http_503: fetch /api/session" not in str((evaluation.get("result") or {}).get("detail") or "")
        or (evaluation.get("result") or {}).get("preview_url") != old_url):
        raise PreviewEnvironmentNotReady("not_a_verified_environmental_503")
    deployment = one(cp_get("factory_deployments", {
        "select":"status,metadata","run_id":"eq."+run_id,
        "environment":"eq.preview","status":"eq.success",
        "order":"created_at.desc","limit":"1",
    }), "old_preview")
    if (deployment.get("status") != "success"
        or (deployment.get("metadata") or {}).get("candidate_commit") != previous
        or (deployment.get("metadata") or {}).get("preview_url") != old_url):
        raise PreviewEnvironmentNotReady("historical_preview_sha_drift")

    pull = github_get(repository,f"pulls/{pr_number}")
    new = ((pull.get("head") or {}).get("sha") if isinstance(pull, dict) else None)
    if (not isinstance(pull, dict) or pull.get("number") != pr_number
        or pull.get("state") != "open" or pull.get("merged_at") is not None
        or pull.get("draft") is not False
        or not isinstance(new,str) or not SHA.fullmatch(new) or new == previous
        or (pull.get("head") or {}).get("ref") != branch
        or ((pull.get("head") or {}).get("repo") or {}).get("full_name") != repository
        or (pull.get("base") or {}).get("ref") != "main"):
        raise PreviewEnvironmentNotReady("live_pr_sha_drift")
    branch_state = github_get(repository, "branches/" + urllib.parse.quote(branch,safe=""))
    if ((branch_state.get("commit") or {}).get("sha") != new):
        raise PreviewEnvironmentNotReady("branch_sha_drift")
    comparison = github_get(repository,f"compare/{previous}...{new}")
    ahead = comparison.get("ahead_by")
    if (comparison.get("status") != "ahead" or type(ahead) is not int or not 1 <= ahead <= 999999
        or comparison.get("behind_by") != 0):
        raise PreviewEnvironmentNotReady("not_a_strict_github_successor")

    actions = github_get(repository,"actions/runs?head_sha="+new+"&per_page=100")
    runs = actions.get("workflow_runs") if isinstance(actions,dict) else None
    if (not isinstance(runs,list) or type(actions.get("total_count")) is not int
        or actions["total_count"] != len(runs) or len(runs) > 100):
        raise PreviewEnvironmentNotReady("native_ci_inventory_ambiguous")
    matches=[x for x in runs if isinstance(x,dict)
        and x.get("path") == EXPECTED_WORKFLOW
        and x.get("head_sha") == new and x.get("event") == "pull_request"]
    if not matches or any(type(x.get("run_number")) is not int
                          or type(x.get("run_attempt")) is not int for x in matches):
        raise PreviewEnvironmentNotReady("exact_native_ci_absent")
    matches.sort(key=lambda x:(x["run_number"],x["run_attempt"]),reverse=True)
    ci=matches[0]
    if (ci.get("status") != "completed" or ci.get("conclusion") != "success"
        or type(ci.get("id")) is not int or ci["id"] < 1):
        raise PreviewEnvironmentNotReady("latest_native_ci_not_green")

    statuses=github_get(repository,f"commits/{new}/status")
    if statuses.get("sha") != new:
        raise PreviewEnvironmentNotReady("provider_status_wrong_sha")
    matching=[s for s in statuses.get("statuses",[]) if isinstance(s,dict)
              and s.get("context") == "Vercel" and s.get("state") == "success"
              and isinstance(s.get("target_url"),str)
              and VERCEL.fullmatch(s["target_url"])]
    if len(matching) != 1:
        raise PreviewEnvironmentNotReady("vercel_exact_provider_status_missing")
    deployment_id="dpl_"+VERCEL.fullmatch(matching[0]["target_url"]).group(1)

    # Only after all identities match: non-mutating no-redirect/no-cookie probe.
    probe=session_probe(url)
    if (not isinstance(probe,dict) or probe.get("kind") != "unauthenticated_json_session_probe"
        or probe.get("url") != url+"/api/session"
        or probe.get("http_status") not in ("200","401")
        or not isinstance(probe.get("content_type"),str)
        or not probe["content_type"].startswith("application/json")
        or not isinstance(probe.get("checked_at"),str)):
        raise PreviewEnvironmentNotReady("new_preview_backend_not_ready")
    probe["candidate_commit"]=new
    return {
        "p_run_id":run_id,"p_previous_commit":previous,"p_new_commit":new,
        "p_pr_number":pr_number,
        "p_verified_github":{
            "source":"github_actions_exact_sha","repository":repository,
            "old_sha":previous,"new_sha":new,"head_sha":new,
            "head_ref":branch,"pr_number":str(pr_number),"pr_state":"open",
            "merged":False,"draft":False,"base_ref":"main","compare_status":"ahead",
            "ahead_by":str(ahead),"behind_by":"0",
            "ci_run_id":str(ci["id"]),"ci_conclusion":"success",
            "vercel_state":"success","vercel_deployment_id":deployment_id,
            "preview_url":url,
        },
        "p_environment_probe":probe,
    }


def main() -> int:
    parser=argparse.ArgumentParser(description="Fail-closed F6 successor preflight, no paid calls")
    parser.add_argument("--project-key",required=True)
    parser.add_argument("--run-id",required=True)
    parser.add_argument("--preview-url",required=True)
    parser.add_argument("--execute",action="store_true")
    parser.add_argument("--ack-environment-authorized",action="store_true")
    args=parser.parse_args()
    if args.execute and not args.ack_environment_authorized:
        print(json.dumps({"status":"blocked","reason":"explicit_environment_authorization_required"}))
        return 2
    try:
        cfg=resolve_supabase_server_config()
        def cp_get(table,params):
            query=urllib.parse.urlencode(params)
            req=urllib.request.Request(cfg.url+"/rest/v1/"+table+"?"+query,
                headers=cfg.headers,method="GET")
            with urllib.request.urlopen(req,timeout=15) as res:
                return json.load(res)
        def github_get(repository,path):
            token=resolve_github_token(repository)
            req=urllib.request.Request(
                f"https://api.github.com/repos/{repository}/{path}",
                headers={"Authorization":"Bearer "+token,
                         "Accept":"application/vnd.github+json",
                         "X-GitHub-Api-Version":"2022-11-28"},method="GET")
            with urllib.request.urlopen(req,timeout=15) as res:
                return json.load(res)
        payload=prepare_successor(run_id=args.run_id,project_key=args.project_key,
            preview_url=args.preview_url,cp_get=cp_get,
            github_get=github_get,session_probe=probe_session)
        if not args.execute:
            print(json.dumps({"status":"preflight_passed","new_sha":payload["p_new_commit"],
                "old_sha":payload["p_previous_commit"],"browser_verified":False,
                "paid_calls":0,"writes":0,"next_step":"separate_migration_and_operator_gate"}))
            return 0
        req=urllib.request.Request(
            cfg.url+"/rest/v1/rpc/factory_recover_greenfield_backend_successor_v1",
            headers={**cfg.headers,"Content-Type":"application/json"},
            data=json.dumps(payload).encode(),method="POST")
        with urllib.request.urlopen(req,timeout=20) as response:
            result=json.load(response)
        if not isinstance(result,dict) or result.get("status")!="ci_pending":
            raise PreviewEnvironmentNotReady("invalid_requeue_receipt")
        print(json.dumps({"status":"ci_pending","run_id":args.run_id,
            "new_sha":payload["p_new_commit"],"old_failure_preserved":True,
            "browser_verified":False,"release_authorized":False,"paid_calls":0}))
        return 0
    except (RuntimeError,ValueError,KeyError,OSError,urllib.error.URLError) as exc:
        reason=str(exc) if isinstance(exc,PreviewEnvironmentNotReady) else "successor_preflight_or_rpc_unavailable"
        print(json.dumps({"status":"blocked","reason":reason,
            "browser_verified":False,"release_authorized":False,"paid_calls":0}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
