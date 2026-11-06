import hashlib
import io
import json
import zipfile
import unittest
from pathlib import Path
import sys
from unittest.mock import patch

from ai_product_factory.independent_rollback_evidence import (
    ARTIFACT_FILE, ARTIFACT_ID, ARTIFACT_NAME, MERGE_SHA, OWNER_WORKFLOW,
    REPO, SOURCE_FILES, SOURCE_RUN, SOURCE_SHA, WORKFLOW,
    RollbackEvidenceBlocked, verify_existing_isolated_rollback,
)
from ai_product_factory.product_readiness_certification import VerifiedCriterionEvidence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_readiness_evidence_manifest import build_verified_baseline
from tests.test_product_readiness_certification import REPO as TEST_REPO, SHA as TEST_SHA, github


def archive():
    receipt = {"schema":"factory-block1-isolated-git-revert-v1","scope":"synthetic_offline_revert_not_production_rollback","git_revert_executed":True,"reverted_tree_equal_to_baseline":True,"working_tree_clean":True,"no_git_remotes":True,"original_bytes_restored":True,"distinct_revert_commit":True,"commit_count":3,"baseline_tree_digest":"a"*64,"revert_tree_digest":"b"*64,"production_human_gate_required":True,"passed":True,"production_rollback_executed":False,"schema_rollback_executed":False,"block1_certified":False,"paid_calls":0,"production_writes":0}
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(ARTIFACT_FILE, json.dumps(receipt, sort_keys=True))
    return output.getvalue(), receipt


def environment():
    return {"GITHUB_ACTIONS":"true","GITHUB_REPOSITORY":REPO,"GITHUB_EVENT_NAME":"workflow_run","GITHUB_REF":"refs/heads/main","GITHUB_WORKFLOW_REF":REPO + "/" + OWNER_WORKFLOW + "@refs/heads/main","GITHUB_RUN_ID":"123","GITHUB_TOKEN":"fixture"}


def fixture(sha="f" * 40):
    raw, receipt = archive(); root = "/repos/" + REPO
    values = {
        root + "/git/ref/heads/main":{"object":{"sha":sha}},
        root + "/actions/runs/123":{"id":123,"name":"Factory autonomous runner","path":OWNER_WORKFLOW,"event":"workflow_run","head_sha":sha,"head_branch":"main","run_attempt":1},
        root + "/actions/runs/" + str(SOURCE_RUN):{"id":SOURCE_RUN,"name":"Block 1 isolated rollback rehearsal","path":WORKFLOW,"event":"pull_request","head_sha":SOURCE_SHA,"run_attempt":1,"status":"completed","conclusion":"success"},
        root + "/actions/runs/" + str(SOURCE_RUN) + "/jobs?per_page=100":{"total_count":1,"jobs":[{"name":"isolated-git-revert","run_id":SOURCE_RUN,"head_sha":SOURCE_SHA,"status":"completed","conclusion":"success","steps":[{"name":"Reproduce offline Git revert and enforce production human gate","status":"completed","conclusion":"success"}]}]},
        root + "/actions/runs/" + str(SOURCE_RUN) + "/artifacts?per_page=100":{"total_count":1,"artifacts":[{"id":ARTIFACT_ID,"name":ARTIFACT_NAME,"expired":False,"digest":"sha256:" + hashlib.sha256(raw).hexdigest(),"size_in_bytes":len(raw),"archive_download_url":"https://api.github.com" + root + "/actions/artifacts/" + str(ARTIFACT_ID) + "/zip","workflow_run":{"id":SOURCE_RUN,"head_sha":SOURCE_SHA,"head_repository_id":1387883686}}]},
        root + "/compare/" + MERGE_SHA + "..." + sha:{"status":"ahead","behind_by":0,"merge_base_commit":{"sha":MERGE_SHA}},
    }
    for path in SOURCE_FILES:
        values[root + "/contents/" + path + "?ref=" + SOURCE_SHA] = {"sha":"a"*40,"size":1}
        values[root + "/contents/" + path + "?ref=" + sha] = {"sha":"a"*40,"size":1}
    return values, raw, receipt


class RollbackEvidenceTests(unittest.TestCase):
    def proof(self, values=None, raw=None, sha="f" * 40):
        values, raw, _ = fixture(sha) if values is None else (values, raw, None)
        return verify_existing_isolated_rollback(repository=REPO, assessed_commit=sha,
            github_get=lambda path: values[path], archive_fetch=lambda url, token: raw,
            environment=environment())

    def test_verified_run_and_bounded_receipt_pass_only_documentation_rollback(self):
        proof = self.proof()
        self.assertEqual((proof.domain, proof.criterion), ("documentation", "release_rollback"))
        self.assertFalse(proof.retained_receipt["production_rollback_executed"])

    def test_expired_artifact_failed_step_and_source_drift_fail_closed(self):
        for mutation in ("expired", "step", "source"):
            values, raw, _ = fixture(); root = "/repos/" + REPO
            if mutation == "expired":
                values[root + "/actions/runs/" + str(SOURCE_RUN) + "/artifacts?per_page=100"]["artifacts"][0]["expired"] = True
            elif mutation == "step":
                values[root + "/actions/runs/" + str(SOURCE_RUN) + "/jobs?per_page=100"]["jobs"][0]["steps"] = []
            else:
                values[root + "/contents/" + SOURCE_FILES[0] + "?ref=" + "f"*40]["sha"] = "b"*40
            with self.subTest(mutation=mutation), self.assertRaises(RollbackEvidenceBlocked):
                self.proof(values, raw)

    def test_builder_uses_trusted_rollback_only(self):
        proof = VerifiedCriterionEvidence(domain="documentation", criterion="release_rollback", repository=TEST_REPO, assessed_commit=TEST_SHA, verification_state="reviewed", source="trusted", evidence=("proof:" + TEST_SHA,), retained_receipt={"safe":True})
        with patch("build_readiness_evidence_manifest.verify_existing_isolated_rollback", return_value=proof):
            report = build_verified_baseline(repository=TEST_REPO, sha=TEST_SHA, github_get=lambda path: github()[path], verify_rollback=True)
        row = next(row for row in report["criteria"] if row["domain"] == "documentation" and row["criterion"] == "release_rollback")
        self.assertEqual(row["status"], "passed")


if __name__ == "__main__":
    unittest.main()
