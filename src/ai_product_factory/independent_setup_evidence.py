"""Revalidate a real non-root README setup exercise before one documentation PASS.

The historical exercise is never enough on its own: check the original
pull-request run, merged ancestry, exact unchanged source blobs, completed
job, artifact provenance AND downloaded artifact bytes on every assessment.
No setup command is run on the production host; no credentials are created.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable, Mapping

from .product_readiness_certification import VerifiedCriterionEvidence

REPO = "leandrosilveiradepaula/ai-product-factory"
SOURCE_SHA = "0a78ba0c72dfb803eb0b9019787fd77e1d5e537b"
MERGE_SHA = "9129f4db6cec6fc936f219f7c34cb1c928457a9d"
SOURCE_PR = 1255
SOURCE_RUN = 42160722506
SOURCE_VALIDATE_RUN = 42160722518
SOURCE_JOB = "nonroot-setup"
ARTIFACT_ID = 13475949818
ARTIFACT_NAME = "block1-clean-setup-receipt"
ARTIFACT_FILE = "block1-clean-setup-receipt.json"
SETUP_WORKFLOW = ".github/workflows/block1-clean-setup.yml"
OWNER_WORKFLOW = ".github/workflows/autonomous-runner.yml"
SHA = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z", re.ASCII)
# These are the actual code/configuration paths exercised by this test.
# A change revokes historical reuse; unrelated changes to the certifier do not.
SOURCE_FILES = (
    "README.md",
    "pyproject.toml",
    "config/factory.example.json",
    "scripts/exercise_block1_clean_setup.py",
    "scripts/check_test_collection.py",
    "src/ai_product_factory/cli.py",
    "src/ai_product_factory/codex_policy.py",
    "src/ai_product_factory/models.py",
    "src/ai_product_factory/manifest.py",
    SETUP_WORKFLOW,
)
REQUIRED_STEPS = (
    "Reproduce README without root, inherited credentials or install",
    "Preserve credential-free setup result",
)
REQUIRED_VALIDATE_STEPS = {
    "test": "Unit tests",
    "factory-acceptance": "Factory acceptance gate",
}


class SetupEvidenceBlocked(RuntimeError):
    """Fixed-vocabulary fail-closed evidence error; no external body is logged."""


def require(value: bool, code: str) -> None:
    if not value:
        raise SetupEvidenceBlocked(code)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _download_artifact(url: str, token: str) -> bytes:
    expected = (
        "https://api.github.com/repos/" + REPO
        + "/actions/artifacts/" + str(ARTIFACT_ID) + "/zip"
    )
    require(url == expected and bool(token), "setup_artifact_source_invalid")
    req = urllib.request.Request(expected, method="GET", headers={
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
    })
    try:
        with urllib.request.build_opener(_NoRedirect).open(req, timeout=25) as response:
            raw = response.read(16385)
    except urllib.error.HTTPError as exc:
        require(exc.code in (301, 302, 303, 307, 308),
                "setup_artifact_download_denied")
        target = exc.headers.get("Location", "")
        parsed = urllib.parse.urlsplit(target)
        host = (parsed.hostname or "").lower()
        require(
            parsed.scheme == "https" and parsed.username is None
            and parsed.password is None
            and (
                host.endswith(".blob.core.windows.net")
                or host.endswith(".actions.githubusercontent.com")
                or host == "pipelines.actions.githubusercontent.com"
            ),
            "setup_artifact_redirect_untrusted",
        )
        # Signed URL goes to GitHub-approved artifact storage WITHOUT GH token.
        with urllib.request.urlopen(
            urllib.request.Request(target, headers={"Accept": "application/zip"}),
            timeout=25,
        ) as response:
            raw = response.read(16385)
    require(0 < len(raw) <= 16384, "setup_artifact_size_invalid")
    return raw


def _verify_archive(raw: bytes, *, digest: str) -> dict:
    require(
        isinstance(raw, bytes) and 0 < len(raw) <= 16384
        and digest == "sha256:" + hashlib.sha256(raw).hexdigest(),
        "setup_zip_integrity_failed",
    )
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
            require(
                len(members) == 1 and members[0].filename == ARTIFACT_FILE
                and not members[0].is_dir()
                and 0 < members[0].file_size <= 8192,
                "setup_zip_contents_invalid",
            )
            receipt = json.loads(archive.read(members[0]).decode("utf-8"))
    except (zipfile.BadZipFile, UnicodeError, ValueError, OSError) as exc:
        raise SetupEvidenceBlocked("setup_zip_unreadable") from exc
    require(isinstance(receipt, dict), "setup_receipt_not_object")
    require(
        receipt.get("schema") == "factory-block1-clean-setup-v1"
        and receipt.get("setup_commands_passed") is True
        and receipt.get("allowlisted_environment_only") is True
        and receipt.get("non_root_identity") is True
        and receipt.get("source_path_exact") is True
        and receipt.get("readme_commands_present") is True
        and receipt.get("paid_model_calls") == 0
        and receipt.get("release_authorized") is False
        and receipt.get("block1_certified") is False
        and receipt.get("documentation_setup_configuration_certified") is False,
        "setup_receipt_scope_invalid",
    )
    commands = receipt.get("commands")
    require(
        isinstance(commands, list) and len(commands) == 3
        and [c.get("command") for c in commands if isinstance(c, dict)] == [
            "ai_product_factory.cli",
            "ai_product_factory.cli",
            "scripts/check_test_collection.py",
        ] and all(
            type(c.get("exit_code")) is int
            and c["exit_code"] == 0 and c.get("timed_out") is False
            for c in commands if isinstance(c, dict)
        ),
        "setup_three_commands_not_verified",
    )
    return receipt


def _verify_source(github_get: Callable[[str], object], assessed_commit: str) -> str:
    prefix = "/repos/" + REPO
    current = github_get(prefix + "/git/ref/heads/main")
    require(
        isinstance(current, dict) and isinstance(current.get("object"), dict)
        and current["object"].get("sha") == assessed_commit,
        "setup_assessment_no_longer_main",
    )
    pr = github_get(prefix + "/pulls/" + str(SOURCE_PR))
    require(
        isinstance(pr, dict) and pr.get("number") == SOURCE_PR
        and isinstance(pr.get("merged_at"), str) and bool(pr["merged_at"])
        and pr.get("merge_commit_sha") == MERGE_SHA
        and isinstance(pr.get("head"), dict)
        and pr["head"].get("sha") == SOURCE_SHA,
        "setup_original_pr_not_human_merged",
    )
    if assessed_commit != MERGE_SHA:
        compare = github_get(prefix + "/compare/" + MERGE_SHA + "..." + assessed_commit)
        require(
            isinstance(compare, dict) and compare.get("status") == "ahead"
            and compare.get("behind_by") == 0
            and isinstance(compare.get("merge_base_commit"), dict)
            and compare["merge_base_commit"].get("sha") == MERGE_SHA,
            "setup_original_merge_not_in_main_ancestry",
        )
    for path in SOURCE_FILES:
        before = github_get(prefix + "/contents/" + path + "?ref=" + SOURCE_SHA)
        after = github_get(prefix + "/contents/" + path + "?ref=" + assessed_commit)
        require(
            isinstance(before, dict) and isinstance(after, dict)
            and isinstance(before.get("sha"), str)
            and SHA.fullmatch(before["sha"]) is not None
            and before["sha"] == after.get("sha")
            and type(before.get("size")) is int and before["size"] > 0
            and before["size"] == after.get("size"),
            "setup_exercised_code_drift",
        )
    return MERGE_SHA


def verify_existing_clean_setup(
    *, repository: str, assessed_commit: str,
    github_get: Callable[[str], object],
    archive_fetch: Callable[[str, str], bytes] = _download_artifact,
    environment: Mapping[str, str] | None = None,
) -> VerifiedCriterionEvidence:
    env = os.environ if environment is None else environment
    require(
        repository == REPO and isinstance(assessed_commit, str)
        and SHA.fullmatch(assessed_commit) is not None
        and env.get("GITHUB_ACTIONS") == "true"
        and env.get("GITHUB_REPOSITORY") == REPO
        and env.get("GITHUB_EVENT_NAME") == "workflow_run"
        and env.get("GITHUB_REF") == "refs/heads/main"
        and env.get("GITHUB_WORKFLOW_REF")
        == REPO + "/" + OWNER_WORKFLOW + "@refs/heads/main",
        "setup_trusted_runner_identity_invalid",
    )
    current_id = env.get("GITHUB_RUN_ID", "")
    require(isinstance(current_id, str) and current_id.isdecimal()
            and 0 < int(current_id) < 10**18,
            "setup_current_runner_id_invalid")
    prefix = "/repos/" + REPO
    current = github_get(prefix + "/actions/runs/" + current_id)
    require(
        isinstance(current, dict) and current.get("id") == int(current_id)
        and current.get("name") == "Factory autonomous runner"
        and current.get("path") == OWNER_WORKFLOW
        and current.get("event") == "workflow_run"
        and current.get("head_sha") == assessed_commit
        and current.get("head_branch") == "main"
        and current.get("run_attempt") == 1,
        "setup_current_runner_not_bound",
    )
    source = github_get(prefix + "/actions/runs/" + str(SOURCE_RUN))
    require(
        isinstance(source, dict) and source.get("id") == SOURCE_RUN
        and source.get("name") == "Block 1 credential-free clean setup evidence"
        and source.get("path") == SETUP_WORKFLOW
        and source.get("event") == "pull_request"
        and source.get("head_sha") == SOURCE_SHA
        and source.get("run_attempt") == 1
        and source.get("status") == "completed"
        and source.get("conclusion") == "success",
        "setup_source_run_invalid",
    )
    jobs = github_get(prefix + "/actions/runs/" + str(SOURCE_RUN) + "/jobs?per_page=100")
    rows = jobs.get("jobs") if isinstance(jobs, dict) else None
    require(
        isinstance(rows, list) and len(rows) == 1
        and jobs.get("total_count") == 1
        and isinstance(rows[0], dict)
        and rows[0].get("name") == SOURCE_JOB
        and rows[0].get("run_id") == SOURCE_RUN
        and rows[0].get("head_sha") == SOURCE_SHA
        and rows[0].get("status") == "completed"
        and rows[0].get("conclusion") == "success",
        "setup_source_job_invalid",
    )
    steps = rows[0].get("steps")
    require(
        isinstance(steps, list)
        and all(
            sum(
                isinstance(step, dict)
                and step.get("name") == required
                and step.get("status") == "completed"
                and step.get("conclusion") == "success"
                for step in steps
            ) == 1
            for required in REQUIRED_STEPS
        ),
        "setup_source_steps_invalid",
    )
    # README includes a fourth command: full unittest discovery. The
    # independent exact-source validate job executed that suite and the
    # acceptance suite; checking only the three non-root commands is partial.
    validated = github_get(prefix + "/actions/runs/" + str(SOURCE_VALIDATE_RUN))
    require(
        isinstance(validated, dict) and validated.get("id") == SOURCE_VALIDATE_RUN
        and validated.get("name") == "validate"
        and validated.get("path") == ".github/workflows/validate.yml"
        and validated.get("event") == "pull_request"
        and validated.get("head_sha") == SOURCE_SHA
        and validated.get("run_attempt") == 1
        and validated.get("status") == "completed"
        and validated.get("conclusion") == "success",
        "setup_full_unittest_run_invalid",
    )
    validation_jobs = github_get(
        prefix + "/actions/runs/" + str(SOURCE_VALIDATE_RUN) + "/jobs?per_page=100"
    )
    all_jobs = validation_jobs.get("jobs") if isinstance(validation_jobs, dict) else None
    require(
        isinstance(all_jobs, list) and len(all_jobs) == 2
        and validation_jobs.get("total_count") == 2
        and {j.get("name") for j in all_jobs if isinstance(j, dict)}
            == {"test", "factory-acceptance"}
        and all(
            isinstance(j, dict) and j.get("run_id") == SOURCE_VALIDATE_RUN
            and j.get("head_sha") == SOURCE_SHA
            and j.get("status") == "completed"
            and j.get("conclusion") == "success"
            for j in all_jobs
        ),
        "setup_full_unittest_or_acceptance_not_executed",
    )
    for job in all_jobs:
        expected_step = REQUIRED_VALIDATE_STEPS[job["name"]]
        steps = job.get("steps")
        require(
            isinstance(steps, list)
            and sum(
                isinstance(step, dict)
                and step.get("name") == expected_step
                and step.get("status") == "completed"
                and step.get("conclusion") == "success"
                for step in steps
            ) == 1,
            "setup_full_unittest_or_acceptance_step_not_executed",
        )
    artifacts = github_get(prefix + "/actions/runs/" + str(SOURCE_RUN)
                           + "/artifacts?per_page=100")
    records = artifacts.get("artifacts") if isinstance(artifacts, dict) else None
    require(isinstance(records, list) and len(records) == 1
            and artifacts.get("total_count") == 1
            and isinstance(records[0], dict),
            "setup_artifact_list_incomplete")
    record = records[0]
    binding = record.get("workflow_run")
    require(
        record.get("id") == ARTIFACT_ID
        and record.get("name") == ARTIFACT_NAME
        and record.get("expired") is False
        and isinstance(record.get("digest"), str)
        and DIGEST.fullmatch(record["digest"]) is not None
        and type(record.get("size_in_bytes")) is int
        and 0 < record["size_in_bytes"] <= 16384
        and isinstance(binding, dict)
        and binding.get("id") == SOURCE_RUN
        and binding.get("head_sha") == SOURCE_SHA
        and binding.get("head_repository_id") == 1387883686,
        "setup_artifact_provenance_invalid",
    )
    _verify_source(github_get, assessed_commit)
    archive = archive_fetch(record.get("archive_download_url", ""), env.get("GITHUB_TOKEN", ""))
    receipt = _verify_archive(archive, digest=record["digest"])
    # A second identity check closes the time-of-check / time-of-use gap.
    after = github_get(prefix + "/git/ref/heads/main")
    require(isinstance(after, dict) and isinstance(after.get("object"), dict)
            and after["object"].get("sha") == assessed_commit,
            "setup_main_changed_while_verifying")
    return VerifiedCriterionEvidence(
        domain="documentation", criterion="setup_configuration",
        repository=repository, assessed_commit=assessed_commit,
        verification_state="reviewed",
        source=(
            "source-verified-credential-free-setup:" + str(SOURCE_RUN)
            + "/" + str(ARTIFACT_ID) + ":validate/" + str(SOURCE_VALIDATE_RUN)
            + ":" + record["digest"]
        ),
        evidence=(
            "https://github.com/" + repository + "/actions/runs/"
            + current_id + "#sha=" + assessed_commit,
        ),
        retained_receipt=receipt,
    )
