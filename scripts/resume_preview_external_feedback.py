#!/usr/bin/env python3
"""Bounded real-browser-only recovery. Read-only unless explicitly --execute.

For the already authorized candidate, the trusted cross-repo workflow first
stores a SHA-bound independent browser success snapshot. Only then can this
status-only RPC requeue the original run for another normal Preview evaluation.
No models, merge, release, deployment, or historical-evidence rewriting.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
from urllib import parse, request

from ai_product_factory.github_auth import resolve_github_token
from ai_product_factory.supabase_server import resolve_supabase_server_config

_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_URL = re.compile(r"https://[a-z0-9][a-z0-9-]*[.]vercel[.]app\Z")


class RecoveryBlocked(ValueError):
    pass


def prepare_recovery(*, repository: str, candidate_sha: str, preview_url: str,
                     verifier_factory_sha: str, cp_get, github_get) -> dict | None:
    if not all((isinstance(repository, str), isinstance(candidate_sha, str),
                isinstance(preview_url, str), isinstance(verifier_factory_sha, str))):
        raise RecoveryBlocked("invalid_identity_type")
    if (not _REPO.fullmatch(repository) or not _SHA.fullmatch(candidate_sha)
        or not _URL.fullmatch(preview_url) or not _SHA.fullmatch(verifier_factory_sha)):
        raise RecoveryBlocked("invalid_identity")
    projects = cp_get("factory_projects", {
        "select": "id,repository,is_active", "repository": "eq."+repository,
        "is_active": "eq.true", "limit": "2",
    })
    if not isinstance(projects, list) or len(projects) != 1 or projects[0].get("repository") != repository:
        raise RecoveryBlocked("active_project_not_unique")
    sets = cp_get("factory_change_sets", {
        "select": "id,status,release_run_id,candidate_commit,integration_branch,metadata",
        "project_id": "eq."+str(projects[0]["id"]), "status": "eq.ci_pending",
        "candidate_commit": "eq."+candidate_sha, "limit": "2",
    })
    if not isinstance(sets, list) or len(sets) > 1:
        raise RecoveryBlocked("change_set_not_unique")
    if not sets:
        return None
    cs = sets[0]
    release = (cs.get("metadata") or {}).get("integration_release_request") or {}
    number = release.get("pr_number")
    if type(number) is not int or number < 1 or release.get("candidate_commit") != candidate_sha:
        raise RecoveryBlocked("change_set_release_identity_invalid")
    run_id = str(cs.get("release_run_id") or "")
    runs = cp_get("factory_runs", {
        "select": "id,status,candidate_commit,branch_name",
        "id": "eq."+run_id, "limit": "2",
    })
    if not isinstance(runs, list) or len(runs) != 1:
        raise RecoveryBlocked("release_run_not_unique")
    if runs[0].get("status") != "failed":
        return None
    if (runs[0].get("candidate_commit") != candidate_sha
        or runs[0].get("branch_name") != cs.get("integration_branch")):
        raise RecoveryBlocked("terminal_candidate_drift")

    pr = github_get(repository, "pulls/"+str(number))
    if (not isinstance(pr, dict) or pr.get("number") != number
        or pr.get("state") != "open" or pr.get("draft") is not False
        or pr.get("merged_at") is not None
        or (pr.get("head") or {}).get("sha") != candidate_sha
        or (pr.get("head") or {}).get("ref") != cs.get("integration_branch")
        or ((pr.get("head") or {}).get("repo") or {}).get("full_name") != repository
        or (pr.get("base") or {}).get("ref") != "main"):
        raise RecoveryBlocked("github_pr_changed")
    statuses = github_get(repository, "commits/"+candidate_sha+"/status")
    if (not isinstance(statuses, dict) or statuses.get("sha") != candidate_sha
        or not any(isinstance(s, dict) and s.get("state") == "success"
                   and str(s.get("context") or "").lower() == "vercel"
                   for s in statuses.get("statuses") or [])):
        raise RecoveryBlocked("exact_vercel_status_unverified")

    return {
        "p_run_id": run_id, "p_candidate_commit": candidate_sha, "p_pr_number": number,
        "p_verified_github": {
            "repository": repository, "pr_number": str(number), "head_sha": candidate_sha,
            "head_ref": cs["integration_branch"], "pr_state": "open", "draft": False,
            "merged": False, "vercel_state": "success",
            "preview_url": preview_url, "factory_sha": verifier_factory_sha,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--preview-url", required=True)
    parser.add_argument("--verifier-factory-sha", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        cfg = resolve_supabase_server_config()

        def cp_get(table, params):
            if table not in ("factory_projects", "factory_change_sets", "factory_runs"):
                raise RecoveryBlocked("untrusted_table")
            path = "/rest/v1/"+table+"?"+parse.urlencode(params)
            req = request.Request(cfg.url.rstrip("/")+path,headers=cfg.headers,method="GET")
            with request.urlopen(req,timeout=20) as response:
                data = json.load(response)
            if not isinstance(data,list):
                raise RecoveryBlocked("invalid_cp_response")
            return data

        def github_get(repo, endpoint):
            token = resolve_github_token(repo)
            req = request.Request("https://api.github.com/repos/"+repo+"/"+endpoint,
                headers={"Authorization":"Bearer "+token,
                         "Accept":"application/vnd.github+json",
                         "X-GitHub-Api-Version":"2026-03-10"},method="GET")
            with request.urlopen(req,timeout=20) as response:
                return json.load(response)

        payload = prepare_recovery(
            repository=args.repository,candidate_sha=args.candidate_sha,
            preview_url=args.preview_url,verifier_factory_sha=args.verifier_factory_sha,
            cp_get=cp_get,github_get=github_get)
        if payload is None:
            print(json.dumps({"status":"not_applicable","release_authorized":False}))
            return 0
        if not args.execute:
            print(json.dumps({"status":"eligible_pending_independent_snapshot",
                              "browser_verified":False,"release_authorized":False}))
            return 0
        req = request.Request(cfg.url.rstrip("/")+
            "/rest/v1/rpc/factory_resume_preview_external_feedback_once_v1",
            data=json.dumps(payload,separators=(",",":")).encode(),
            headers={**cfg.headers,"Content-Type":"application/json"},method="POST")
        with request.urlopen(req,timeout=30) as response:
            receipt=json.load(response)
        if not isinstance(receipt,dict) or receipt.get("status")!="preview_ready" \
            or receipt.get("run_id")!=payload["p_run_id"] \
            or receipt.get("release_authorized") is not False \
            or receipt.get("original_browser_failure_preserved") is not True:
            raise RecoveryBlocked("unexpected_rpc_receipt")
        print(json.dumps({"status":"preview_ready",
            "candidate_sha":payload["p_candidate_commit"],
            "run_id":payload["p_run_id"],"release_authorized":False,
            "original_browser_failure_preserved":True,"paid_calls":0}))
        return 0
    except (RecoveryBlocked, OSError, RuntimeError, ValueError, urllib.error.URLError):
        # Do not print provider response bodies, URL query strings or tokens.
        print(json.dumps({"status":"blocked","release_authorized":False,
                          "reason":"exact_preview_recovery_preflight_or_rpc_blocked"}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
