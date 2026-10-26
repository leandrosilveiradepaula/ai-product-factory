#!/usr/bin/env python3
"""Explicit, fail-closed Preview backend recovery after environment remediation.

Read-only checks first. With --execute and explicit acknowledgement only, call
the privileged status-only RPC. Never install credentials, deploy, merge,
replay implementation/Product Stage or treat a READY deployment as browser PASS.
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
import uuid

from ai_product_factory.github_auth import resolve_github_token
from ai_product_factory.supabase_server import resolve_supabase_server_config

SHA = re.compile(r"^[0-9a-f]{40}$")
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
VERCEL_TARGET = re.compile(
    r"^https://vercel[.]com/[a-zA-Z0-9-]+/[a-zA-Z0-9-]+/[a-zA-Z0-9]{20,40}$"
)


class PreviewEnvironmentNotReady(RuntimeError):
    pass


def preview_origin(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise PreviewEnvironmentNotReady("invalid_preview_origin")
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError as exc:
        raise PreviewEnvironmentNotReady("invalid_preview_origin") from exc
    hostname = parsed.hostname or ""
    if (parsed.scheme != "https" or not re.fullmatch(
        r"[a-z0-9][a-z0-9-]*[.]vercel[.]app", hostname)
        or parsed.netloc != hostname or parsed.path not in ("", "/")
        or parsed.query or parsed.fragment or parsed.username or parsed.password):
        raise PreviewEnvironmentNotReady("untrusted_preview_origin")
    return "https://" + hostname


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Reject redirects *before* urllib contacts an untrusted Location target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def probe_session(url: str) -> dict:
    """Credentialless JSON readiness check; never follow an HTTP redirect."""
    origin = preview_origin(url)
    request = urllib.request.Request(
        origin + "/api/session",
        headers={"Accept": "application/json", "User-Agent": "Factory-Preview-Readiness/1"},
        method="GET",
    )
    try:
        try:
            with urllib.request.build_opener(_NoRedirect).open(request, timeout=12) as response:
                status = response.status
                content_type = response.headers.get("Content-Type", "").lower().strip()
                returned_url = response.geturl()
        except urllib.error.HTTPError as exc:
            status = exc.code
            content_type = exc.headers.get("Content-Type", "").lower().strip()
            returned_url = exc.geturl()
            exc.close()
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        raise PreviewEnvironmentNotReady("preview_session_unreachable") from exc
    if returned_url != origin + "/api/session" or 300 <= status < 400:
        raise PreviewEnvironmentNotReady("preview_session_redirected")
    if status not in (200, 401) or not re.fullmatch(r"application/json(?:;.*)?", content_type):
        raise PreviewEnvironmentNotReady("preview_backend_still_unverified")
    return {
        "kind": "unauthenticated_json_session_probe",
        "url": origin + "/api/session",
        "http_status": str(status),
        "content_type": content_type,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def require_github_pr(*, pull: dict, statuses: dict, repository: str,
                      branch: str, candidate: str, number: int) -> dict:
    if (not isinstance(pull, dict) or not isinstance(statuses, dict)
        or pull.get("number") != number
        or pull.get("state") != "open" or pull.get("merged_at") is not None
        or pull.get("draft") is not False
        or not isinstance(pull.get("head"), dict)
        or pull["head"].get("sha") != candidate
        or pull["head"].get("ref") != branch
        or (pull["head"].get("repo") or {}).get("full_name") != repository
        or statuses.get("sha") != candidate):
        raise PreviewEnvironmentNotReady("github_pr_changed")
    owned = [
        x for x in statuses.get("statuses", [])
        if isinstance(x, dict)
        and x.get("context") == "Vercel"
        and x.get("state") == "success"
        and isinstance(x.get("target_url"), str)
        and VERCEL_TARGET.fullmatch(x["target_url"])
    ]
    if not owned:
        raise PreviewEnvironmentNotReady("vercel_provider_status_unverified")
    return {"pr_number": str(number), "head_sha": candidate, "pr_state": "open",
            "merged": False, "vercel_state": "success", "repository": repository,
            "head_ref": branch}


def _one(rows: object, label: str) -> dict:
    if (not isinstance(rows, list) or len(rows) != 1
        or not isinstance(rows[0], dict)):
        raise PreviewEnvironmentNotReady(label + "_not_unique")
    return rows[0]


def prepare_recovery(*, run_id: str, project_key: str, cp_get, github_get, session_probe):
    """All reads/GET probes; injectable for offline negative and success testing."""
    try:
        if str(uuid.UUID(run_id)) != run_id:
            raise ValueError()
    except (ValueError, TypeError) as exc:
        raise PreviewEnvironmentNotReady("invalid_run_identity") from exc
    run = _one(cp_get("factory_runs", {
        "select": "id,task_id,status,candidate_commit,branch_name,metadata",
        "id": "eq." + run_id, "limit": "2",
    }), "run")
    candidate = run.get("candidate_commit")
    branch = run.get("branch_name")
    if (run.get("id") != run_id or run.get("status") != "failed"
        or not isinstance(candidate, str) or not SHA.fullmatch(candidate)
        or not isinstance(branch, str) or not branch.startswith("factory/")):
        raise PreviewEnvironmentNotReady("run_not_failed_exact_candidate")
    task = _one(cp_get("factory_tasks", {
        "select": "id,project_id,status", "id": "eq." + str(run["task_id"]), "limit": "2",
    }), "task")
    project = _one(cp_get("factory_projects", {
        "select": "id,project_key,repository,manifest", "id": "eq." + str(task["project_id"]),
        "limit": "2",
    }), "project")
    repository = project.get("repository")
    if (project.get("project_key") != project_key or not isinstance(repository, str)
        or not REPO.fullmatch(repository)
        or ((project.get("manifest") or {}).get("preview") or {}).get("required") is not True):
        raise PreviewEnvironmentNotReady("project_or_preview_policy_mismatch")
    cs = _one(cp_get("factory_change_sets", {
        "select": "id,release_run_id,status,candidate_commit,integration_branch,metadata",
        "release_run_id": "eq." + run_id, "limit": "2",
    }), "change_set")
    meta = (cs.get("metadata") or {}).get("integration_release_request") or {}
    pr_number = meta.get("pr_number")
    if (cs.get("status") != "ci_pending" or cs.get("candidate_commit") != candidate
        or cs.get("integration_branch") != branch
        or (run.get("metadata") or {}).get("change_set_id") != cs.get("id")
        or type(pr_number) is not int or pr_number < 1):
        raise PreviewEnvironmentNotReady("change_set_drift")
    evaluation = _one(cp_get("factory_evaluations", {
        "select": "status,baseline_ref,result", "run_id": "eq." + run_id,
        "eval_type": "eq.browser_e2e", "order": "created_at.desc", "limit": "1",
    }), "browser_evidence")
    detail = (evaluation.get("result") or {}).get("detail")
    url = preview_origin(evaluation.get("baseline_ref"))
    if (evaluation.get("status") != "failure"
        or not isinstance(detail, str)
        or "http_503: fetch /api/session" not in detail
        or (evaluation.get("result") or {}).get("preview_url") != url):
        raise PreviewEnvironmentNotReady("not_backend_503_browser_failure")
    deploy = _one(cp_get("factory_deployments", {
        "select": "status,metadata", "run_id": "eq." + run_id,
        "environment": "eq.preview", "status": "eq.success",
        "order": "created_at.desc", "limit": "1",
    }), "deployment")
    if ((deploy.get("metadata") or {}).get("candidate_commit") != candidate
        or (deploy.get("metadata") or {}).get("preview_url") != url):
        raise PreviewEnvironmentNotReady("deployment_sha_or_url_drift")
    pull = github_get(repository, f"pulls/{pr_number}")
    statuses = github_get(repository, f"commits/{candidate}/status")
    github = require_github_pr(
        pull=pull, statuses=statuses, repository=repository,
        branch=branch, candidate=candidate, number=pr_number,
    )
    probe = session_probe(url)
    if (not isinstance(probe, dict) or probe.get("url") != url + "/api/session"
        or probe.get("http_status") not in ("200", "401")
        or probe.get("kind") != "unauthenticated_json_session_probe"
        or not isinstance(probe.get("content_type"), str)
        or not probe["content_type"].startswith("application/json")
        or not isinstance(probe.get("checked_at"), str)):
        raise PreviewEnvironmentNotReady("environment_health_unverified")
    probe["candidate_commit"] = candidate
    github["preview_url"] = url
    return {
        "p_run_id": run_id,
        "p_candidate_commit": candidate,
        "p_pr_number": pr_number,
        "p_verified_github": github,
        "p_environment_probe": probe,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover a failed 503 Preview after authorized backend remediation")
    parser.add_argument("--project-key", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--execute", action="store_true",
                        help="Call one privileged recovery RPC, never trigger CI, deploy or release")
    parser.add_argument("--ack-environment-authorized", action="store_true",
                        help="Attest that backend configuration/access was separately authorized")
    args = parser.parse_args()
    if args.execute and not args.ack_environment_authorized:
        print(json.dumps({"status": "blocked", "reason": "environment_authorization_required"}))
        return 2

    try:
        cfg = resolve_supabase_server_config()

        def cp_get(table, params):
            query = urllib.parse.urlencode(params)
            req = urllib.request.Request(
                cfg.url + "/rest/v1/" + table + "?" + query,
                headers=cfg.headers, method="GET",
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                return json.load(response)

        def github_get(repository, path):
            token = resolve_github_token(repository)
            req = urllib.request.Request(
                f"https://api.github.com/repos/{repository}/{path}",
                headers={"Authorization": "Bearer " + token,
                         "Accept": "application/vnd.github+json",
                         "X-GitHub-Api-Version": "2022-11-28"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                return json.load(response)

        receipt = prepare_recovery(
            run_id=args.run_id, project_key=args.project_key,
            cp_get=cp_get, github_get=github_get, session_probe=probe_session,
        )
        if not args.execute:
            print(json.dumps({
                "status": "preflight_passed", "candidate_commit": receipt["p_candidate_commit"],
                "pr_number": receipt["p_pr_number"],
                "browser_verified": False, "production_writes": 0, "paid_calls": 0,
                "next_step": "human_authorized_execute_after_migration_gate",
            }))
            return 0
        req = urllib.request.Request(
            cfg.url + "/rest/v1/rpc/factory_resume_preview_backend_unavailable_v1",
            headers={**cfg.headers, "Content-Type": "application/json"},
            data=json.dumps(receipt).encode(), method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            outcome = json.load(response)
        if not isinstance(outcome, dict) or outcome.get("status") != "preview_ready":
            raise PreviewEnvironmentNotReady("unexpected_recovery_receipt")
        print(json.dumps({
            "status": "preview_ready", "run_id": args.run_id,
            "candidate_commit": receipt["p_candidate_commit"],
            "original_failure_preserved": True, "browser_verified": False,
            "release_authorized": False, "paid_calls": 0,
        }))
        return 0
    except (RuntimeError, ValueError, KeyError, urllib.error.URLError, OSError) as exc:
        reason = str(exc) if isinstance(exc, PreviewEnvironmentNotReady) else "recovery_preflight_or_rpc_unavailable"
        print(json.dumps({"status": "blocked", "reason": reason,
                          "browser_verified": False, "release_authorized": False,
                          "paid_calls": 0}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
