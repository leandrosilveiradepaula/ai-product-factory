"""Trust-bound, read-only reuse of the independently executed CRM V2 lineage audit.

This verifier promotes *only* observability_operations/traceability. It never
claims a greenfield, production release, security audit or global readiness.

The proof source is a real OWNER-triggered Actions run and immutable artifact;
the archive digest, audited verifier code, nonproduction scope, and current
Control Plane terminal state are checked again on every exact-SHA assessment.
No cross-repository token or new privileged Control Plane API is introduced.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable

from .autonomy_journey_reader import SupabaseJourneyReader
from .product_readiness_certification import VerifiedCriterionEvidence

FACTORY = "leandrosilveiradepaula/ai-product-factory"
CRM = "leandrosilveiradepaula/crm-infodive"
SOURCE_SHA = "2fc03b19d72b76be55366f8d8fae940300640874"
SOURCE_RUN_ID = 42026802447
ARTIFACT_ID = 13414057651
ARTIFACT_NAME = "native-v2-readonly-42026802447"
JOURNEY_ID = "bb14e150-2c7e-423b-8e5d-e211dab6225c"
CHANGE_SET_ID = "3f09952e-0384-46ee-97aa-a46c89346678"
ROOT_TASK_ID = "50749027-26b0-4200-9c25-c1ed18548071"
RELEASE_RUN_ID = "606cdd39-cf6b-4515-9a68-3dd072f9609d"
CANDIDATE_SHA = "d0738ee3f3fbb6fb5100e09804e0e2a92c9da0c7"
PREVIEW_MERGE_SHA = "d84f41938a5e36b4b5f86133434c900c433bffc1"
BROWSER_RUN_ID = 41951864064
VERIFIER_JOB = "native-v2-journey-readonly"
TRUSTED_WORKFLOW = ".github/workflows/autonomous-runner.yml"
SHA = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)

# These are the exact bytes that produced the previous, positive CRM audit.
# Changes to any of them revoke reuse until a new real OWNER audit succeeds.
VERIFIER_FILES = (
    "src/ai_product_factory/native_v2_journey_audit.py",
    "src/ai_product_factory/autonomy_journey_reader.py",
    "src/ai_product_factory/github_rest.py",
    "src/ai_product_factory/github_auth.py",
    "src/ai_product_factory/github_owner_start.py",
    "src/ai_product_factory/journey_candidate_provenance.py",
    "scripts/audit_native_v2_journey.py",
)


class TraceabilityUnverified(RuntimeError):
    """A fixed-vocabulary failure; external payloads and secrets stay private."""


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise TraceabilityUnverified(reason)


def exactly_one(reader: SupabaseJourneyReader, table: str, select: str, where: str) -> dict:
    result = reader._get(table + "?select=" + select + "&" + where, limit=2)
    require(len(result) == 1, "control_plane_lineage_missing_or_ambiguous")
    return result[0]


def _verify_current_lineage(reader: SupabaseJourneyReader) -> None:
    journey = exactly_one(
        reader, "factory_journeys",
        "id,project_id,state,execution_generation,production_release_sha,candidate_commit",
        "id=eq." + JOURNEY_ID,
    )
    pid = journey.get("project_id")
    require(
        journey.get("id") == JOURNEY_ID
        and isinstance(pid, str)
        and journey.get("state") == "preview_verified"
        and journey.get("candidate_commit") == CANDIDATE_SHA
        and journey.get("production_release_sha") is None,
        "v2_live_journey_not_preview_only",
    )
    cs = exactly_one(
        reader, "factory_change_sets",
        "id,project_id,journey_id,root_task_id,release_run_id,status,candidate_commit",
        "id=eq." + CHANGE_SET_ID,
    )
    require(
        cs.get("id") == CHANGE_SET_ID and cs.get("project_id") == pid
        and cs.get("journey_id") == JOURNEY_ID
        and cs.get("root_task_id") == ROOT_TASK_ID
        and cs.get("release_run_id") == RELEASE_RUN_ID
        and cs.get("status") == "completed"
        and cs.get("candidate_commit") == CANDIDATE_SHA,
        "v2_live_change_set_drift",
    )
    task = exactly_one(
        reader, "factory_tasks", "id,project_id,journey_id,status",
        "id=eq." + ROOT_TASK_ID,
    )
    run = exactly_one(
        reader, "factory_runs", "id,task_id,status,candidate_commit",
        "id=eq." + RELEASE_RUN_ID,
    )
    require(
        task.get("id") == ROOT_TASK_ID and task.get("project_id") == pid
        and task.get("journey_id") == JOURNEY_ID
        and task.get("status") == "integrated"
        and run.get("id") == RELEASE_RUN_ID
        and run.get("task_id") == ROOT_TASK_ID
        and run.get("status") == "integrated"
        and run.get("candidate_commit") == CANDIDATE_SHA,
        "v2_live_run_or_root_drift",
    )
    control = exactly_one(
        reader, "factory_project_execution_controls", "project_id,state,generation",
        "project_id=eq." + pid,
    )
    require(
        control.get("project_id") == pid
        and control.get("state") == "running"
        and control.get("generation") == journey.get("execution_generation"),
        "v2_live_execution_epoch_revoked",
    )


def _workflow_v2_job(encoded: dict) -> bytes:
    require(
        encoded.get("encoding") == "base64"
        and isinstance(encoded.get("content"), str),
        "v2_workflow_content_unavailable",
    )
    try:
        raw = base64.b64decode(encoded["content"], validate=False).decode("utf-8")
    except (UnicodeError, ValueError) as exc:
        raise TraceabilityUnverified("v2_workflow_content_invalid") from exc
    begin = "\n  native-v2-journey-readonly:\n"
    end = "\n  continuation-offline-preflight:\n"
    require(raw.count(begin) == 1, "v2_workflow_job_not_unique")
    section = raw.split(begin, 1)[1]
    require(end in section, "v2_workflow_job_boundary_unavailable")
    return section.split(end, 1)[0].encode("utf-8")


def _verify_unchanged_verifier(
    github_get: Callable[[str], object], assessed_commit: str
) -> None:
    base = "/repos/" + FACTORY + "/contents/"
    for path in VERIFIER_FILES:
        from_ref = github_get(base + path + "?ref=" + SOURCE_SHA)
        to_ref = github_get(base + path + "?ref=" + assessed_commit)
        require(
            isinstance(from_ref, dict) and isinstance(to_ref, dict)
            and isinstance(from_ref.get("sha"), str)
            and from_ref["sha"] == to_ref.get("sha")
            and type(from_ref.get("size")) is int
            and from_ref["size"] > 0 and from_ref["size"] == to_ref.get("size"),
            "v2_verified_code_changed_since_source_audit",
        )
    wf_base = base + TRUSTED_WORKFLOW + "?ref="
    old = github_get(wf_base + SOURCE_SHA)
    current = github_get(wf_base + assessed_commit)
    require(
        isinstance(old, dict) and isinstance(current, dict)
        and _workflow_v2_job(old) == _workflow_v2_job(current),
        "v2_verifier_workflow_changed_since_source_audit",
    )


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _download_artifact(url: str, token: str) -> bytes:
    """Never forward a repository token to an Actions artifact CDN."""
    exact = (
        "https://api.github.com/repos/" + FACTORY
        + "/actions/artifacts/" + str(ARTIFACT_ID) + "/zip"
    )
    require(url == exact and bool(token), "v2_artifact_source_or_credential_invalid")
    req = urllib.request.Request(
        exact,
        headers={"Accept": "application/vnd.github+json", "Authorization": "Bearer " + token},
        method="GET",
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=25) as response:
            content = response.read(131073)
    except urllib.error.HTTPError as exc:
        require(exc.code in (301, 302, 303, 307, 308),
                "v2_artifact_download_denied")
        location = exc.headers.get("Location", "")
        target = urllib.parse.urlsplit(location)
        host = (target.hostname or "").lower()
        require(
            target.scheme == "https" and not target.username and not target.password
            and (host.endswith(".blob.core.windows.net")
                 or host.endswith(".actions.githubusercontent.com")
                 or host == "pipelines.actions.githubusercontent.com"),
            "v2_artifact_redirect_not_trusted",
        )
        # Only the short-lived signed URL from GitHub is sent to this host.
        with urllib.request.urlopen(
            urllib.request.Request(location, headers={"Accept": "application/zip"}),
            timeout=25,
        ) as response:
            content = response.read(131073)
    require(0 < len(content) <= 131072, "v2_artifact_zip_unbounded")
    return content


def _verify_archive(archive: bytes, *, digest: str) -> dict:
    require(
        isinstance(archive, bytes)
        and 0 < len(archive) <= 131072
        and digest == "sha256:" + hashlib.sha256(archive).hexdigest(),
        "v2_artifact_digest_mismatch",
    )
    try:
        with zipfile.ZipFile(io.BytesIO(archive), "r") as zf:
            files = zf.infolist()
            require(
                len(files) == 1
                and files[0].filename == "native-v2-journey-evidence.json"
                and 0 < files[0].file_size <= 131072
                and not files[0].is_dir(),
                "v2_artifact_content_unbounded",
            )
            data = json.loads(zf.read(files[0]).decode("utf-8"))
    except (zipfile.BadZipFile, UnicodeError, json.JSONDecodeError, OSError) as exc:
        raise TraceabilityUnverified("v2_artifact_content_invalid") from exc
    require(isinstance(data, dict), "v2_artifact_not_json_object")
    expected = {
        "schema_version": 1,
        "project_key": "crm-infodive",
        "journey_id": JOURNEY_ID,
        "change_set_id": CHANGE_SET_ID,
        "run_id": RELEASE_RUN_ID,
        "repository": CRM,
        "candidate_commit": CANDIDATE_SHA,
        "nonproduction_merge_sha": PREVIEW_MERGE_SHA,
        "pr_number": 212,
        "browser_verifier_run_id": BROWSER_RUN_ID,
        "verified_work_units": 5,
        "status": "integrated_nonproduction",
        "classification": "integrated_nonproduction",
        "requirement_met": True,
        "highest_verified": "awaiting_release",
        "human_release_observed": "not_reached",
        "operations": "not_reached",
        "nonproduction_integrated": True,
        "production_released": False,
        "product_ready": False,
        "paid_calls": 0,
        "writes": 0,
    }
    require(data == expected, "v2_artifact_scope_or_content_drift")
    return data


def verify_existing_crm_v2_traceability(
    *, repository: str, assessed_commit: str,
    github_get: Callable[[str], object],
    reader: SupabaseJourneyReader | None = None,
    archive_fetch: Callable[[str, str], bytes] = _download_artifact,
    environment: dict[str, str] | None = None,
) -> VerifiedCriterionEvidence:
    """Verify source bytes, provenance and live terminal state before one PASS.

    Fail-closed exceptions are acceptable: callers must keep this criterion
    missing, never borrow unit-integration/CI proof for another domain.
    """
    env = os.environ if environment is None else environment
    require(
        repository == FACTORY and isinstance(assessed_commit, str)
        and SHA.fullmatch(assessed_commit) is not None
        and env.get("GITHUB_ACTIONS") == "true"
        and env.get("GITHUB_REPOSITORY") == FACTORY
        and env.get("GITHUB_EVENT_NAME") == "workflow_run"
        and env.get("GITHUB_REF") == "refs/heads/main"
        and env.get("GITHUB_WORKFLOW_REF") == (
            FACTORY + "/" + TRUSTED_WORKFLOW + "@refs/heads/main"
        ),
        "v2_assessment_runner_identity_mismatch",
    )
    current_id = env.get("GITHUB_RUN_ID", "")
    require(
        isinstance(current_id, str) and current_id.isdecimal()
        and 0 < int(current_id) < 10**18,
        "v2_current_run_not_bound",
    )
    prefix = "/repos/" + FACTORY
    current = github_get(prefix + "/actions/runs/" + current_id)
    require(
        isinstance(current, dict)
        and current.get("id") == int(current_id)
        and current.get("name") == "Factory autonomous runner"
        and current.get("path") == TRUSTED_WORKFLOW
        and current.get("event") == "workflow_run"
        and current.get("head_branch") == "main"
        and current.get("head_sha") == assessed_commit
        and current.get("run_attempt") == 1
        and current.get("event") == "workflow_run",
        "v2_current_assessment_run_not_verified",
    )
    audited = github_get(prefix + "/actions/runs/" + str(SOURCE_RUN_ID))
    owner = audited.get("actor") if isinstance(audited, dict) else None
    require(
        isinstance(audited, dict) and audited.get("id") == SOURCE_RUN_ID
        and audited.get("path") == TRUSTED_WORKFLOW
        and audited.get("name") == "Factory autonomous runner"
        and audited.get("event") == "issue_comment"
        and audited.get("head_sha") == SOURCE_SHA
        and audited.get("head_branch") == "main"
        and audited.get("status") == "completed"
        and audited.get("conclusion") == "success"
        and audited.get("run_attempt") == 1
        and isinstance(owner, dict)
        and owner.get("id") == 256917842
        and owner.get("login") == "leandrosilveiradepaula",
        "v2_original_owner_run_not_verified",
    )
    jobs = github_get(prefix + "/actions/runs/" + str(SOURCE_RUN_ID) + "/jobs?per_page=100")
    found = jobs.get("jobs") if isinstance(jobs, dict) else None
    require(
        isinstance(found, list) and 0 < len(found) < 100
        and jobs.get("total_count") == len(found)
        and len([j for j in found if isinstance(j, dict)
                 and j.get("name") == VERIFIER_JOB]) == 1
        and all(
            isinstance(j, dict)
            and j.get("run_id") == SOURCE_RUN_ID
            and j.get("head_sha") == SOURCE_SHA
            and j.get("status") == "completed"
            and j.get("conclusion") == (
                "success" if j.get("name") == VERIFIER_JOB else "skipped"
            )
            for j in found
        ),
        "v2_original_runner_or_worker_conclusion_invalid",
    )
    artifact_result = github_get(
        prefix + "/actions/runs/" + str(SOURCE_RUN_ID) + "/artifacts?per_page=100"
    )
    artifacts = artifact_result.get("artifacts") if isinstance(artifact_result, dict) else None
    require(
        isinstance(artifacts, list)
        and artifact_result.get("total_count") == len(artifacts)
        and len(artifacts) == 1
        and isinstance(artifacts[0], dict),
        "v2_artifact_inventory_invalid",
    )
    artifact = artifacts[0]
    binding = artifact.get("workflow_run")
    require(
        artifact.get("id") == ARTIFACT_ID
        and artifact.get("name") == ARTIFACT_NAME
        and artifact.get("expired") is False
        and isinstance(artifact.get("digest"), str)
        and re.fullmatch(r"sha256:[0-9a-f]{64}", artifact["digest"])
        and isinstance(binding, dict)
        and binding.get("id") == SOURCE_RUN_ID
        and binding.get("head_sha") == SOURCE_SHA
        and binding.get("head_repository_id") == 1387883686,
        "v2_artifact_unbound_or_expired",
    )
    _verify_unchanged_verifier(github_get, assessed_commit)
    raw = archive_fetch(artifact.get("archive_download_url", ""), env.get("GITHUB_TOKEN", ""))
    _verify_archive(raw, digest=artifact["digest"])
    _verify_current_lineage(reader if reader is not None else SupabaseJourneyReader())
    return VerifiedCriterionEvidence(
        domain="observability_operations",
        criterion="traceability",
        repository=repository,
        assessed_commit=assessed_commit,
        verification_state="observed",
        source=(
            "source-verified-native-v2-existing-preview:"
            + str(SOURCE_RUN_ID) + "/" + str(ARTIFACT_ID) + ":"
            + artifact["digest"]
        ),
        evidence=(
            "https://github.com/" + repository + "/actions/runs/" + current_id
            + "#sha=" + assessed_commit,
        ),
    )
