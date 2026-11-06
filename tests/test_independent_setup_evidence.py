"""Independent, source-bound setup certification acceptance and adversarial tests."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import zipfile

from ai_product_factory.independent_setup_evidence import (
    REPO, SOURCE_SHA, MERGE_SHA, SOURCE_PR, SOURCE_RUN, SOURCE_VALIDATE_RUN,
    ARTIFACT_ID, ARTIFACT_NAME, ARTIFACT_FILE, SOURCE_FILES,
    SETUP_WORKFLOW, OWNER_WORKFLOW, _verify_archive,
    _verify_source, verify_existing_clean_setup, SetupEvidenceBlocked,
)
from ai_product_factory.product_readiness_certification import (
    VerifiedCriterionEvidence, certify_product_readiness, conservative_verified_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_readiness_evidence_manifest import build_verified_baseline
from tests.test_product_readiness_certification import github, SHA as TEST_SHA, REPO as TEST_REPO


def receipt_zip(overrides=None):
    receipt = {
        "schema": "factory-block1-clean-setup-v1",
        "setup_commands_passed": True,
        "allowlisted_environment_only": True,
        "non_root_identity": True,
        "source_path_exact": True,
        "readme_commands_present": True,
        "paid_model_calls": 0,
        "release_authorized": False,
        "block1_certified": False,
        "documentation_setup_configuration_certified": False,
        "commands": [
            {"command": "ai_product_factory.cli", "exit_code": 0, "timed_out": False},
            {"command": "ai_product_factory.cli", "exit_code": 0, "timed_out": False},
            {"command": "scripts/check_test_collection.py", "exit_code": 0, "timed_out": False},
        ],
    }
    receipt.update(overrides or {})
    zipped = io.BytesIO()
    with zipfile.ZipFile(zipped, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(ARTIFACT_FILE, json.dumps(receipt, sort_keys=True))
    return zipped.getvalue()


def env():
    return {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": REPO,
        "GITHUB_EVENT_NAME": "workflow_run",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_WORKFLOW_REF": REPO + "/" + OWNER_WORKFLOW + "@refs/heads/main",
        "GITHUB_RUN_ID": "123456789",
        "GITHUB_TOKEN": "offline-test-fixture",
    }


def fixture(*, assessed_commit=None, archive=None):
    sha = assessed_commit or "f" * 40
    zipped = receipt_zip() if archive is None else archive
    prefix = "/repos/" + REPO
    contents = {
        prefix + "/git/ref/heads/main": {"object": {"sha": sha}},
        prefix + "/actions/runs/123456789": {
            "id": 123456789, "name": "Factory autonomous runner",
            "path": OWNER_WORKFLOW, "event": "workflow_run",
            "head_sha": sha, "head_branch": "main", "run_attempt": 1,
        },
        prefix + "/pulls/" + str(SOURCE_PR): {
            "number": SOURCE_PR, "merged_at": "2026-11-06T04:11:38Z",
            "merge_commit_sha": MERGE_SHA, "head": {"sha": SOURCE_SHA},
        },
        prefix + "/actions/runs/" + str(SOURCE_RUN): {
            "id": SOURCE_RUN, "name": "Block 1 credential-free clean setup evidence",
            "path": SETUP_WORKFLOW, "event": "pull_request",
            "head_sha": SOURCE_SHA, "run_attempt": 1,
            "status": "completed", "conclusion": "success",
        },
        prefix + "/actions/runs/" + str(SOURCE_RUN) + "/jobs?per_page=100": {
            "total_count": 1,
            "jobs": [{
                "name": "nonroot-setup", "run_id": SOURCE_RUN,
                "head_sha": SOURCE_SHA, "status": "completed",
                "conclusion": "success", "steps": [{
                    "name": "Reproduce README without root, inherited credentials or install",
                    "status": "completed", "conclusion": "success",
                }, {
                    "name": "Preserve credential-free setup result",
                    "status": "completed", "conclusion": "success",
                }],
            }],
        },
        prefix + "/actions/runs/" + str(SOURCE_RUN) + "/artifacts?per_page=100": {
            "total_count": 1,
            "artifacts": [{
                "id": ARTIFACT_ID, "name": ARTIFACT_NAME, "expired": False,
                "digest": "sha256:" + hashlib.sha256(zipped).hexdigest(),
                "archive_download_url": (
                    "https://api.github.com" + prefix
                    + "/actions/artifacts/" + str(ARTIFACT_ID) + "/zip"
                ),
                "size_in_bytes": len(zipped),
                "workflow_run": {
                    "id": SOURCE_RUN, "head_sha": SOURCE_SHA,
                    "head_repository_id": 1387883686,
                },
            }],
        },
        prefix + "/actions/runs/" + str(SOURCE_VALIDATE_RUN): {
            "id": SOURCE_VALIDATE_RUN, "name": "validate",
            "path": ".github/workflows/validate.yml", "event": "pull_request",
            "head_sha": SOURCE_SHA, "run_attempt": 1,
            "status": "completed", "conclusion": "success",
        },
        prefix + "/actions/runs/" + str(SOURCE_VALIDATE_RUN) + "/jobs?per_page=100": {
            "total_count": 2,
            "jobs": [
                {"name": "test", "run_id": SOURCE_VALIDATE_RUN,
                 "head_sha": SOURCE_SHA, "status": "completed", "conclusion": "success",
                 "steps": [{"name": "Unit tests", "status": "completed", "conclusion": "success"}]},
                {"name": "factory-acceptance", "run_id": SOURCE_VALIDATE_RUN,
                 "head_sha": SOURCE_SHA, "status": "completed", "conclusion": "success",
                 "steps": [{"name": "Factory acceptance gate", "status": "completed", "conclusion": "success"}]},
            ],
        },
        prefix + "/compare/" + MERGE_SHA + "..." + sha: {
            "status": "ahead", "behind_by": 0,
            "merge_base_commit": {"sha": MERGE_SHA},
        },
    }
    for path in SOURCE_FILES:
        stub = {"sha": "a" * 40, "size": 250}
        contents[prefix + "/contents/" + path + "?ref=" + SOURCE_SHA] = dict(stub)
        contents[prefix + "/contents/" + path + "?ref=" + sha] = dict(stub)
    return contents, zipped, sha


class IndependentSetupEvidenceTests(unittest.TestCase):
    def proof(self, *, data=None, zipped=None, assessed_commit=None):
        if data is None:
            data, zipped, sha = fixture(assessed_commit=assessed_commit)
        else:
            sha = assessed_commit or "f" * 40
        return verify_existing_clean_setup(
            repository=REPO, assessed_commit=sha,
            github_get=lambda path: data[path],
            archive_fetch=lambda url, token: zipped,
            environment=env(),
        )

    def test_real_run_job_archive_and_unchanged_source_produce_one_scoped_claim(self):
        proof = self.proof()
        self.assertIs(type(proof), VerifiedCriterionEvidence)
        self.assertEqual((proof.domain, proof.criterion),
                         ("documentation", "setup_configuration"))
        self.assertEqual(proof.verification_state, "reviewed")
        self.assertIn("f" * 40, proof.evidence[0])
        self.assertIn(str(ARTIFACT_ID), proof.source)
        self.assertEqual(proof.retained_receipt["schema"], "factory-block1-clean-setup-v1")

    def test_no_artifact_or_changed_source_or_foreign_sha_can_pass(self):
        for mutation in ("expired", "wrong_sha", "bad_digest", "bad_job", "bad_validate",
                         "unmerged_pr", "changed_blob", "wrong_ancestry"):
            data, archive, sha = fixture()
            prefix = "/repos/" + REPO
            source = data[prefix + "/actions/runs/" + str(SOURCE_RUN)]
            record = data[prefix + "/actions/runs/" + str(SOURCE_RUN)
                          + "/artifacts?per_page=100"]["artifacts"][0]
            if mutation == "expired":
                record["expired"] = True
            elif mutation == "wrong_sha":
                source["head_sha"] = "b" * 40
            elif mutation == "bad_digest":
                record["digest"] = "sha256:" + "0" * 64
            elif mutation == "bad_job":
                data[prefix + "/actions/runs/" + str(SOURCE_RUN)
                     + "/jobs?per_page=100"]["jobs"][0]["conclusion"] = "failure"
            elif mutation == "bad_validate":
                data[prefix + "/actions/runs/" + str(SOURCE_VALIDATE_RUN)
                     + "/jobs?per_page=100"]["jobs"][0]["conclusion"] = "failure"
            elif mutation == "unmerged_pr":
                data[prefix + "/pulls/" + str(SOURCE_PR)]["merged_at"] = None
            elif mutation == "changed_blob":
                p = SOURCE_FILES[0]
                data[prefix + "/contents/" + p + "?ref=" + sha]["sha"] = "b" * 40
            elif mutation == "wrong_ancestry":
                data[prefix + "/compare/" + MERGE_SHA + "..." + sha]["behind_by"] = 1
            with self.subTest(mutation=mutation):
                with self.assertRaises(SetupEvidenceBlocked):
                    self.proof(data=data, zipped=archive, assessed_commit=sha)

    def test_missing_or_failed_full_suite_steps_cannot_pass(self):
        for job_index, mutation in ((0, "missing"), (1, "failed")):
            data, archive, sha = fixture()
            jobs = data["/repos/" + REPO + "/actions/runs/" + str(SOURCE_VALIDATE_RUN)
                        + "/jobs?per_page=100"]["jobs"]
            if mutation == "missing":
                jobs[job_index]["steps"] = []
            else:
                jobs[job_index]["steps"][0]["conclusion"] = "failure"
            with self.subTest(job_index=job_index, mutation=mutation), self.assertRaises(SetupEvidenceBlocked):
                self.proof(data=data, zipped=archive, assessed_commit=sha)

    def test_cannot_reuse_unauthorized_runtime_or_wrong_repository(self):
        data, zipped, sha = fixture()
        for variation in ("wrong_workflow", "wrong_event", "wrong_run"):
            environ = env()
            if variation == "wrong_workflow":
                environ["GITHUB_WORKFLOW_REF"] = "other/other/.github/workflows/a.yml@main"
            elif variation == "wrong_event":
                environ["GITHUB_EVENT_NAME"] = "pull_request"
            else:
                environ["GITHUB_RUN_ID"] = "wrong"
            with self.subTest(variation=variation), self.assertRaises(SetupEvidenceBlocked):
                verify_existing_clean_setup(
                    repository=REPO, assessed_commit=sha,
                    github_get=lambda p: data[p],
                    archive_fetch=lambda url, token: zipped,
                    environment=environ,
                )
        with self.assertRaises(SetupEvidenceBlocked):
            verify_existing_clean_setup(
                repository="attacker/repository", assessed_commit=sha,
                github_get=lambda p: data[p],
                archive_fetch=lambda url, token: zipped,
                environment=env(),
            )

    def test_modified_bytes_failed_setup_and_extra_zip_member_fail_closed(self):
        raw = receipt_zip()
        digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        self.assertTrue(_verify_archive(raw, digest=digest)["setup_commands_passed"])
        for overrides in ({"non_root_identity": False},
                          {"setup_commands_passed": False},
                          {"paid_model_calls": 1},
                          {"commands": []},
                          {"documentation_setup_configuration_certified": True}):
            changed = receipt_zip(overrides)
            with self.subTest(overrides=overrides), self.assertRaises(SetupEvidenceBlocked):
                _verify_archive(changed, digest="sha256:" + hashlib.sha256(changed).hexdigest())
        with self.assertRaises(SetupEvidenceBlocked):
            _verify_archive(raw, digest="sha256:" + "0" * 64)
        bad = io.BytesIO()
        with zipfile.ZipFile(bad, "w") as zf:
            zf.writestr(ARTIFACT_FILE, "{}")
            zf.writestr("../escape.txt", "danger")
        with self.assertRaises(SetupEvidenceBlocked):
            _verify_archive(bad.getvalue(), digest="sha256:" + hashlib.sha256(bad.getvalue()).hexdigest())

    def test_builder_trust_boundary_does_not_accept_claim_without_trusted_verifier(self):
        data = github()
        proof = VerifiedCriterionEvidence(
            domain="documentation", criterion="setup_configuration",
            repository=TEST_REPO, assessed_commit=TEST_SHA,
            verification_state="reviewed", source="offline-source-verifier",
            evidence=("proof@sha:" + TEST_SHA,),
        )
        with patch("build_readiness_evidence_manifest.verify_existing_clean_setup",
                   return_value=proof):
            report = build_verified_baseline(
                repository=TEST_REPO, sha=TEST_SHA,
                github_get=lambda p: data[p], verify_setup=True,
            )
        self.assertFalse(report["assessment"]["ready"])
        self.assertEqual(report["manifest"]["criteria"]["documentation"]
                         ["setup_configuration"]["status"], "passed")
        self.assertEqual([x["status"] for x in report["criteria"] if
                          x["domain"] == "documentation" and
                          x["criterion"] == "setup_configuration"], ["passed"])
        # The same caller-provided manifest MUST fail when the trusted verifier
        # is absent (this is not a data-driven PASS switch).
        without = certify_product_readiness(
            repository=TEST_REPO, assessed_commit=TEST_SHA,
            manifest=report["manifest"], github_get=lambda p: data[p],
        )
        self.assertEqual(without.report["criteria"]["documentation"]
                         ["setup_configuration"]["status"], "failed")
        with patch("build_readiness_evidence_manifest.verify_existing_clean_setup",
                   side_effect=SetupEvidenceBlocked("expired")):
            blocked = build_verified_baseline(
                repository=TEST_REPO, sha=TEST_SHA,
                github_get=lambda p: data[p], verify_setup=True,
            )
        self.assertEqual(blocked["manifest"]["criteria"]["documentation"]
                         ["setup_configuration"]["status"], "missing")

    def test_persisted_attestation_retains_sanitized_verified_receipt(self):
        data = github()
        receipt = {"schema": "factory-block1-clean-setup-v1", "paid_model_calls": 0}
        proof = VerifiedCriterionEvidence(
            domain="documentation", criterion="setup_configuration",
            repository=TEST_REPO, assessed_commit=TEST_SHA,
            verification_state="reviewed", source="durable-source",
            evidence=("proof@sha:" + TEST_SHA,), retained_receipt=receipt,
        )
        manifest = conservative_verified_manifest(
            repository=TEST_REPO, assessed_commit=TEST_SHA, github_get=lambda p: data[p]
        )
        manifest["criteria"]["documentation"]["setup_configuration"].update(
            status="passed", verification_state="reviewed"
        )
        report = certify_product_readiness(
            repository=TEST_REPO, assessed_commit=TEST_SHA, manifest=manifest,
            github_get=lambda p: data[p],
            trusted_verifier=lambda domain, criterion, snapshot: proof
            if (domain, criterion) == ("documentation", "setup_configuration") else None,
        )
        item = report.report["criteria"]["documentation"]["setup_configuration"]
        self.assertEqual(item["attestation"]["retained_receipt"], receipt)


if __name__ == "__main__":
    unittest.main()
