"""Offline evidence verification: never convert a historical green CI into release."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import unittest
import zipfile
from unittest.mock import patch

from ai_product_factory.native_v2_traceability_certification import (
    FACTORY, SOURCE_SHA, SOURCE_RUN_ID, ARTIFACT_ID, ARTIFACT_NAME, JOURNEY_ID,
    CHANGE_SET_ID, ROOT_TASK_ID, RELEASE_RUN_ID, CANDIDATE_SHA,
    PREVIEW_MERGE_SHA, BROWSER_RUN_ID, VERIFIER_FILES, TRUSTED_WORKFLOW,
    _verify_archive, _verify_current_lineage, _verify_unchanged_verifier,
    _workflow_v2_job, verify_existing_crm_v2_traceability,
    TraceabilityUnverified,
)
from ai_product_factory.product_readiness_certification import (
    VerifiedCriterionEvidence,
)

HEAD = "f" * 40
RUN_ID = "987654321"
PROJECT_ID = "00000000-0000-4000-8000-000000000001"
ZIP_NAME = "native-v2-journey-evidence.json"


def fake_archive():
    evidence = {
        "schema_version": 1, "project_key": "crm-infodive",
        "journey_id": JOURNEY_ID, "change_set_id": CHANGE_SET_ID,
        "run_id": RELEASE_RUN_ID,
        "repository": "leandrosilveiradepaula/crm-infodive",
        "candidate_commit": CANDIDATE_SHA,
        "nonproduction_merge_sha": PREVIEW_MERGE_SHA,
        "pr_number": 212, "browser_verifier_run_id": BROWSER_RUN_ID,
        "verified_work_units": 5, "status": "integrated_nonproduction",
        "classification": "integrated_nonproduction",
        "requirement_met": True, "highest_verified": "awaiting_release",
        "human_release_observed": "not_reached", "operations": "not_reached",
        "nonproduction_integrated": True, "production_released": False,
        "product_ready": False, "paid_calls": 0, "writes": 0,
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(ZIP_NAME, json.dumps(evidence))
    return buf.getvalue()


class Reader:
    def __init__(self):
        self.tables = {
            "factory_journeys": [{
                "id": JOURNEY_ID, "project_id": PROJECT_ID,
                "state": "preview_verified", "execution_generation": 19,
                "production_release_sha": None, "candidate_commit": CANDIDATE_SHA,
            }],
            "factory_change_sets": [{
                "id": CHANGE_SET_ID, "project_id": PROJECT_ID,
                "journey_id": JOURNEY_ID, "root_task_id": ROOT_TASK_ID,
                "release_run_id": RELEASE_RUN_ID,
                "status": "completed", "candidate_commit": CANDIDATE_SHA,
            }],
            "factory_tasks": [{
                "id": ROOT_TASK_ID, "project_id": PROJECT_ID,
                "journey_id": JOURNEY_ID, "status": "integrated",
            }],
            "factory_runs": [{
                "id": RELEASE_RUN_ID, "task_id": ROOT_TASK_ID,
                "status": "integrated", "candidate_commit": CANDIDATE_SHA,
            }],
            "factory_project_execution_controls": [{
                "project_id": PROJECT_ID, "state": "running", "generation": 19,
            }],
        }
        self.read_paths = []

    def _get(self, path, *, limit):
        self.read_paths.append(path)
        table, query = path.split("?", 1)
        self._validate_request_columns(table, query)
        return json.loads(json.dumps(self.tables[table]))[:limit]

    @staticmethod
    def _validate_request_columns(table, query):
        from urllib.parse import parse_qs
        select = parse_qs(query)["select"][0].split(",")
        if table == "factory_runs":
            assert "project_id" not in select, "factory_runs has no project_id"
        assert "id" in select or table == "factory_project_execution_controls"


def fake_api(archive_bytes, *, corrupt=None):
    zip_digest = hashlib.sha256(archive_bytes).hexdigest()
    path = "/repos/" + FACTORY
    event = {
        "id": SOURCE_RUN_ID, "name": "Factory autonomous runner",
        "path": TRUSTED_WORKFLOW, "event": "issue_comment",
        "head_sha": SOURCE_SHA, "head_branch": "main",
        "status": "completed", "conclusion": "success", "run_attempt": 1,
        "actor": {"id": 256917842, "login": "leandrosilveiradepaula"},
    }
    current = dict(event, id=int(RUN_ID), event="workflow_run", head_sha=HEAD)
    jobs = [{
        "id": 7, "run_id": SOURCE_RUN_ID,
        "head_sha": SOURCE_SHA, "name": "native-v2-journey-readonly",
        "status": "completed", "conclusion": "success",
    }, {
        "id": 8, "run_id": SOURCE_RUN_ID,
        "head_sha": SOURCE_SHA, "name": "schedule-probe",
        "status": "completed", "conclusion": "skipped",
    }]
    artifact = {
        "id": ARTIFACT_ID, "name": ARTIFACT_NAME, "expired": False,
        "digest": "sha256:" + zip_digest,
        "archive_download_url": path.replace("/repos/", "https://api.github.com/repos/")
        + "/actions/artifacts/" + str(ARTIFACT_ID) + "/zip",
        "workflow_run": {
            "id": SOURCE_RUN_ID, "head_sha": SOURCE_SHA,
            "head_repository_id": 1387883686,
        },
    }
    body = (
        "jobs:\n  native-v2-journey-readonly:\n"
        "    if: owner_verified\n"
        "    steps: read-only\n"
        "  continuation-offline-preflight:\n"
    )
    raw = {"encoding": "base64", "content": base64.b64encode(body.encode()).decode()}
    def get(endpoint):
        if endpoint == path + "/actions/runs/" + RUN_ID:
            return current
        if endpoint == path + "/actions/runs/" + str(SOURCE_RUN_ID):
            return event
        if endpoint == path + "/actions/runs/" + str(SOURCE_RUN_ID) + "/jobs?per_page=100":
            return {"total_count": len(jobs), "jobs": jobs}
        if endpoint == path + "/actions/runs/" + str(SOURCE_RUN_ID) + "/artifacts?per_page=100":
            return {"total_count": 1, "artifacts": [artifact]}
        if endpoint.startswith(path + "/contents/"):
            if "native-v2-journey-readonly" in endpoint:
                raise AssertionError("bad content path")
            if TRUSTED_WORKFLOW in endpoint:
                return raw
            return {"sha": "a" * 40, "size": 20}
        raise AssertionError("unexpected GitHub GET: " + endpoint)
    return get, current, event, jobs, artifact, raw


def env():
    return {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": FACTORY,
        "GITHUB_EVENT_NAME": "workflow_run",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_WORKFLOW_REF": FACTORY + "/" + TRUSTED_WORKFLOW + "@refs/heads/main",
        "GITHUB_RUN_ID": RUN_ID,
        "GITHUB_TOKEN": "offline-fixture",
    }


class ReusedNativeV2EvidenceTests(unittest.TestCase):
    def make_valid(self):
        archive = fake_archive()
        get, current, original, jobs, artifact, workflow = fake_api(archive)
        return archive, get, current, original, jobs, artifact, workflow

    def test_accepts_only_scoped_existing_preview_and_never_product_ready(self):
        archive, get, *_ = self.make_valid()
        reader = Reader()
        proof = verify_existing_crm_v2_traceability(
            repository=FACTORY, assessed_commit=HEAD,
            github_get=get, reader=reader,
            archive_fetch=lambda url, token: archive,
            environment=env(),
        )
        self.assertIs(type(proof), VerifiedCriterionEvidence)
        self.assertEqual((proof.domain, proof.criterion),
                         ("observability_operations", "traceability"))
        self.assertIn(HEAD, proof.evidence[0])
        self.assertFalse(any("/rpc/" in x for x in reader.read_paths))
        self.assertTrue(any(p.startswith("factory_runs?") for p in reader.read_paths))

    def test_denies_mismatched_owner_workflow_jobs_artifact_and_sha(self):
        for key in ("actor", "event", "run_attempt", "conclusion", "head_sha"):
            with self.subTest(key=key):
                archive, get, current, original, *_ = self.make_valid()
                original[key] = (
                    {"id": 7, "login": "attacker"} if key == "actor" else
                    "push" if key == "event" else 2 if key == "run_attempt" else
                    "failure" if key == "conclusion" else "1" * 40
                )
                with self.assertRaises(TraceabilityUnverified):
                    verify_existing_crm_v2_traceability(
                        repository=FACTORY, assessed_commit=HEAD,
                        github_get=get, reader=Reader(),
                        archive_fetch=lambda url, token: archive, environment=env(),
                    )
        archive, get, current, original, jobs, artifact, *_ = self.make_valid()
        jobs[1]["conclusion"] = "success"
        with self.assertRaises(TraceabilityUnverified):
            verify_existing_crm_v2_traceability(
                repository=FACTORY, assessed_commit=HEAD,
                github_get=get, reader=Reader(),
                archive_fetch=lambda url, token: archive, environment=env(),
            )
        archive, get, current, original, jobs, artifact, *_ = self.make_valid()
        artifact["expired"] = True
        with self.assertRaises(TraceabilityUnverified):
            verify_existing_crm_v2_traceability(
                repository=FACTORY, assessed_commit=HEAD,
                github_get=get, reader=Reader(),
                archive_fetch=lambda url, token: archive, environment=env(),
            )

    def test_rejects_modified_archive_scope_and_file_integrity(self):
        archive, *_ = self.make_valid()
        self.assertEqual(_verify_archive(archive, digest="sha256:" + hashlib.sha256(archive).hexdigest())["verified_work_units"], 5)
        for changed in (archive + b"padding", archive[:-2], b"not a zip"):
            with self.subTest(size=len(changed)), self.assertRaises(TraceabilityUnverified):
                _verify_archive(changed, digest="sha256:" + hashlib.sha256(archive).hexdigest())
        with self.assertRaises(TraceabilityUnverified):
            _verify_archive(archive, digest="sha256:" + "0" * 64)

    def test_live_lineage_drift_denies_and_run_has_no_project_id(self):
        for table, key, value in [
            ("factory_journeys", "production_release_sha", PREVIEW_MERGE_SHA),
            ("factory_journeys", "state", "released"),
            ("factory_change_sets", "status", "queued"),
            ("factory_tasks", "journey_id", RELEASE_RUN_ID),
            ("factory_runs", "status", "repair_pending"),
            ("factory_project_execution_controls", "generation", 20),
        ]:
            r = Reader()
            r.tables[table][0][key] = value
            with self.subTest(table=table, key=key), self.assertRaises(TraceabilityUnverified):
                _verify_current_lineage(r)

    def test_code_or_workflow_drift_denied(self):
        archive, gh, current, original, jobs, artifact, workflow = self.make_valid()
        _verify_unchanged_verifier(gh, HEAD)
        bad_workflow = dict(workflow, content=base64.b64encode(
            b"jobs:\n  native-v2-journey-readonly:\n    if: true\n  continuation-offline-preflight:\n"
        ).decode())
        base_path = "/repos/" + FACTORY + "/contents/"
        def mutated(endpoint):
            if endpoint == base_path + TRUSTED_WORKFLOW + "?ref=" + HEAD:
                return bad_workflow
            return gh(endpoint)
        with self.assertRaises(TraceabilityUnverified):
            _verify_unchanged_verifier(mutated, HEAD)
        def changed_code(endpoint):
            if endpoint == base_path + VERIFIER_FILES[0] + "?ref=" + HEAD:
                return {"sha": "1" * 40, "size": 20}
            return gh(endpoint)
        with self.assertRaises(TraceabilityUnverified):
            _verify_unchanged_verifier(changed_code, HEAD)

    def test_wrong_caller_identity_denies_before_any_source_read(self):
        archive, gh, *_ = self.make_valid()
        for update in (
            {"GITHUB_EVENT_NAME": "issue_comment"},
            {"GITHUB_WORKFLOW_REF": "attacker/other"},
            {"GITHUB_REPOSITORY": "attacker/other"},
            {"GITHUB_RUN_ID": "invalid"},
        ):
            modified = dict(env(), **update)
            with self.subTest(update=update), self.assertRaises(TraceabilityUnverified):
                verify_existing_crm_v2_traceability(
                    repository=FACTORY, assessed_commit=HEAD,
                    github_get=gh, reader=Reader(),
                    archive_fetch=lambda url, token: archive,
                    environment=modified,
                )


if __name__ == "__main__":
    unittest.main()
