"""Current-merge, independently executed documentation proofs.

The two isolated pull_request jobs are deliberately separate from the post-CI
certifier. On *each* human merge we bind their receipts to the exact PR head,
require the merge and PR Git trees to be identical, verify jobs and artifact
bytes, and recheck main. Historical expiring artifact IDs are never reused.
No additional workflow dispatch, credentials to generated code, or production
write is performed here.
"""
from __future__ import annotations

import hashlib
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping

from .independent_setup_evidence import (
    ARTIFACT_NAME as SETUP_ARTIFACT, SETUP_WORKFLOW,
    _verify_archive as verify_setup_zip,
)
from .independent_rollback_evidence import (
    ARTIFACT_NAME as ROLLBACK_ARTIFACT,
    WORKFLOW as ROLLBACK_WORKFLOW,
    _receipt as verify_rollback_zip,
    _verify_current_runbook as verify_current_rollback_runbook,
)
from .product_readiness_certification import VerifiedCriterionEvidence

REPO = "leandrosilveiradepaula/ai-product-factory"
OWNER_WORKFLOW = ".github/workflows/autonomous-runner.yml"
REPOSITORY_ID = 1387883686
SHA = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z", re.ASCII)

PROOFS = {
    "setup": {
        "name": "Block 1 credential-free clean setup evidence",
        "workflow": SETUP_WORKFLOW,
        "job": "nonroot-setup",
        "step": "Reproduce README without root, inherited credentials or install",
        "artifact": SETUP_ARTIFACT,
        "domain": "documentation",
        "criterion": "setup_configuration",
    },
    "rollback": {
        "name": "Block 1 isolated rollback rehearsal",
        "workflow": ROLLBACK_WORKFLOW,
        "job": "isolated-git-revert",
        "step": "Reproduce offline Git revert and enforce production human gate",
        "artifact": ROLLBACK_ARTIFACT,
        "domain": "documentation",
        "criterion": "release_rollback",
    },
}


class CurrentDocumentationBlocked(RuntimeError):
    """Only fixed, non-secret error codes may escape this verifier."""


def require(ok: bool, code: str) -> None:
    if not ok:
        raise CurrentDocumentationBlocked(code)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def download_artifact(url: str, token: str) -> bytes:
    """Download a bounded GitHub artifact without forwarding tokens to storage."""
    prefix = "https://api.github.com/repos/" + REPO + "/actions/artifacts/"
    require(isinstance(url, str) and url.startswith(prefix) and url.endswith("/zip"),
            "documentation_artifact_url_invalid")
    artifact_id = url[len(prefix):-4]
    require(artifact_id.isdecimal() and 0 < int(artifact_id) < 10**18
            and bool(token), "documentation_artifact_auth_invalid")
    req = urllib.request.Request(url, method="GET", headers={
        "Accept": "application/vnd.github+json", "Authorization": "Bearer " + token,
    })
    try:
        with urllib.request.build_opener(_NoRedirect).open(req, timeout=25) as response:
            raw = response.read(16385)
    except urllib.error.HTTPError as exc:
        require(exc.code in (301, 302, 303, 307, 308),
                "documentation_artifact_download_denied")
        target = urllib.parse.urlsplit(exc.headers.get("Location", ""))
        host = (target.hostname or "").lower()
        require(target.scheme == "https" and target.port in (None, 443)
                and not target.username and not target.password
                and (host.endswith(".blob.core.windows.net")
                     or host.endswith(".actions.githubusercontent.com")
                     or host == "pipelines.actions.githubusercontent.com"),
                "documentation_artifact_redirect_untrusted")
        with urllib.request.urlopen(
            urllib.request.Request(target.geturl(), headers={"Accept": "application/zip"}),
            timeout=25,
        ) as response:
            raw = response.read(16385)
    require(0 < len(raw) <= 16384, "documentation_artifact_size_invalid")
    return raw


def _main_binding(*, repository: str, sha: str, get, env):
    require(repository == REPO and isinstance(sha, str)
            and SHA.fullmatch(sha) is not None
            and env.get("GITHUB_ACTIONS") == "true"
            and env.get("GITHUB_REPOSITORY") == REPO
            and env.get("GITHUB_REF") == "refs/heads/main"
            and env.get("GITHUB_EVENT_NAME") == "workflow_run"
            and env.get("GITHUB_WORKFLOW_REF") ==
                REPO + "/" + OWNER_WORKFLOW + "@refs/heads/main",
            "documentation_runner_identity_invalid")
    run_id = env.get("GITHUB_RUN_ID", "")
    require(isinstance(run_id, str) and run_id.isdecimal()
            and 0 < int(run_id) < 10**18, "documentation_runner_id_invalid")
    prefix = "/repos/" + REPO
    run = get(prefix + "/actions/runs/" + run_id)
    require(isinstance(run, dict)
            and run.get("id") == int(run_id)
            and run.get("name") == "Factory autonomous runner"
            and run.get("path") == OWNER_WORKFLOW
            and run.get("event") == "workflow_run"
            and run.get("head_branch") == "main"
            and run.get("head_sha") == sha
            and run.get("run_attempt") == 1,
            "documentation_runner_unbound")
    current = get(prefix + "/git/ref/heads/main")
    require(isinstance(current, dict)
            and isinstance(current.get("object"), dict)
            and current["object"].get("sha") == sha,
            "documentation_main_changed")
    merge = get(prefix + "/commits/" + sha)
    require(isinstance(merge, dict) and merge.get("sha") == sha
            and isinstance(merge.get("parents"), list)
            and len(merge["parents"]) == 2
            and isinstance(merge.get("commit"), dict)
            and isinstance(merge["commit"].get("tree"), dict),
            "documentation_not_human_merge")
    head = merge["parents"][1].get("sha")
    require(isinstance(head, str) and SHA.fullmatch(head) is not None
            and isinstance(merge["parents"][0].get("sha"), str),
            "documentation_merge_parent_invalid")
    # A conflict resolution changing source bytes invalidates PR-based QA.
    pr_head = get(prefix + "/commits/" + head)
    require(isinstance(pr_head, dict) and pr_head.get("sha") == head
            and isinstance(pr_head.get("commit"), dict)
            and isinstance(pr_head["commit"].get("tree"), dict)
            and pr_head["commit"]["tree"].get("sha") == merge["commit"]["tree"].get("sha"),
            "documentation_merged_tree_differs_from_tested_tree")
    pulls = get(prefix + "/commits/" + head + "/pulls?per_page=100")
    require(isinstance(pulls, list) and len(pulls) <= 100, "documentation_pr_lookup_invalid")
    matching = [p for p in pulls if isinstance(p, dict)
                and p.get("state") == "closed" and p.get("merged_at")
                and p.get("merge_commit_sha") == sha
                and isinstance(p.get("head"), dict) and p["head"].get("sha") == head
                and isinstance(p.get("base"), dict) and p["base"].get("ref") == "main"
                and (p["base"].get("repo") or {}).get("full_name") == REPO]
    require(len(matching) == 1, "documentation_human_pr_not_unique")
    return prefix, head, run_id


def _verify(*, kind: str, repository: str, assessed_commit: str, github_get,
            archive_fetch: Callable[[str, str], bytes] | None = None,
            environment: Mapping[str, str] | None = None) -> VerifiedCriterionEvidence:
    require(kind in PROOFS, "documentation_kind_invalid")
    cfg = PROOFS[kind]
    env = os.environ if environment is None else environment
    prefix, head, current_id = _main_binding(
        repository=repository, sha=assessed_commit, get=github_get, env=env)
    listing = github_get(prefix + "/actions/runs?head_sha=" + head
                         + "&event=pull_request&per_page=100")
    rows = listing.get("workflow_runs") if isinstance(listing, dict) else None
    require(isinstance(rows, list) and len(rows) <= 100
            and type(listing.get("total_count")) is int
            and listing["total_count"] <= 100, "documentation_source_runs_incomplete")
    matches = [r for r in rows if isinstance(r, dict)
               and r.get("name") == cfg["name"]
               and r.get("path") == cfg["workflow"]
               and r.get("event") == "pull_request"
               and r.get("head_sha") == head
               and r.get("run_attempt") == 1
               and r.get("status") == "completed"
               and r.get("conclusion") == "success"
               and type(r.get("id")) is int and r["id"] > 0]
    require(len(matches) == 1, "documentation_source_run_not_unique")
    source_run_id = matches[0]["id"]
    jobs = github_get(prefix + "/actions/runs/" + str(source_run_id) + "/jobs?per_page=100")
    job_rows = jobs.get("jobs") if isinstance(jobs, dict) else None
    require(isinstance(job_rows, list) and len(job_rows) == 1
            and jobs.get("total_count") == 1, "documentation_source_jobs_invalid")
    job = job_rows[0]
    require(isinstance(job, dict) and job.get("name") == cfg["job"]
            and job.get("run_id") == source_run_id and job.get("head_sha") == head
            and job.get("status") == "completed" and job.get("conclusion") == "success"
            and isinstance(job.get("steps"), list)
            and any(isinstance(s, dict) and s.get("name") == cfg["step"]
                    and s.get("status") == "completed"
                    and s.get("conclusion") == "success" for s in job["steps"]),
            "documentation_source_job_not_executed")
    inventory = github_get(prefix + "/actions/runs/" + str(source_run_id)
                           + "/artifacts?per_page=100")
    items = inventory.get("artifacts") if isinstance(inventory, dict) else None
    require(isinstance(items, list) and inventory.get("total_count") == 1
            and len(items) == 1 and isinstance(items[0], dict),
            "documentation_artifact_inventory_invalid")
    item = items[0]
    aid = item.get("id")
    binding = item.get("workflow_run")
    url = "https://api.github.com" + prefix + "/actions/artifacts/" + str(aid) + "/zip"
    require(type(aid) is int and aid > 0
            and item.get("name") == cfg["artifact"]
            and item.get("expired") is False
            and isinstance(item.get("digest"), str)
            and DIGEST.fullmatch(item["digest"]) is not None
            and type(item.get("size_in_bytes")) is int
            and 0 < item["size_in_bytes"] <= 16384
            and item.get("archive_download_url") == url
            and isinstance(binding, dict)
            and binding.get("id") == source_run_id
            and binding.get("head_sha") == head
            and binding.get("head_repository_id") == REPOSITORY_ID,
            "documentation_artifact_provenance_invalid")
    fetch = download_artifact if archive_fetch is None else archive_fetch
    raw = fetch(url, env.get("GITHUB_TOKEN", ""))
    require(isinstance(raw, bytes) and len(raw) == item["size_in_bytes"],
            "documentation_artifact_bytes_changed")
    require(hashlib.sha256(raw).hexdigest() == item["digest"][7:],
            "documentation_artifact_digest_changed")
    if kind == "setup":
        receipt = verify_setup_zip(raw, digest=item["digest"])
    else:
        receipt = verify_rollback_zip(raw, item["digest"])
        verify_current_rollback_runbook(github_get, prefix, assessed_commit)
    current = github_get(prefix + "/git/ref/heads/main")
    require(isinstance(current, dict)
            and (current.get("object") or {}).get("sha") == assessed_commit,
            "documentation_main_changed_while_verifying")
    return VerifiedCriterionEvidence(
        domain=cfg["domain"], criterion=cfg["criterion"], repository=repository,
        assessed_commit=assessed_commit, verification_state="reviewed",
        source="source-verified-current-pr-" + kind + ":" + str(source_run_id)
               + "/" + str(aid) + ":" + item["digest"],
        evidence=("https://github.com/" + REPO + "/actions/runs/" + str(source_run_id)
                  + "#sha=" + assessed_commit,
                  "https://github.com/" + REPO + "/actions/runs/" + current_id
                  + "#sha=" + assessed_commit),
        retained_receipt=receipt,
    )


def verify_current_clean_setup(**kwargs) -> VerifiedCriterionEvidence:
    return _verify(kind="setup", **kwargs)


def verify_current_isolated_rollback(**kwargs) -> VerifiedCriterionEvidence:
    return _verify(kind="rollback", **kwargs)
