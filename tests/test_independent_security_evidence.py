import hashlib
import io
import json
import unittest
import zipfile
from pathlib import Path
import sys
from unittest.mock import patch

from ai_product_factory.independent_security_evidence import (
    MERGE_SHA, OWNER_WORKFLOW, REPO, SCANS, SOURCE_FILES, SOURCE_SHA,
    SecurityEvidenceBlocked, verify_existing_secrets_dependencies,
)
from ai_product_factory.product_readiness_certification import VerifiedCriterionEvidence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_readiness_evidence_manifest import build_verified_baseline
from tests.test_product_readiness_certification import REPO as TEST_REPO, SHA as TEST_SHA, github


def environment():
    return {"GITHUB_ACTIONS":"true", "GITHUB_REPOSITORY":REPO,
            "GITHUB_EVENT_NAME":"workflow_run", "GITHUB_REF":"refs/heads/main",
            "GITHUB_WORKFLOW_REF":REPO + "/" + OWNER_WORKFLOW + "@refs/heads/main",
            "GITHUB_RUN_ID":"123", "GITHUB_TOKEN":"fixture"}


def receipt(kind):
    if kind == "gitleaks":
        value = {"schema":"factory-block1-complete-tracked-tree-gitleaks-v1", "assessed_commit":SOURCE_SHA,
                 "scan_passed":True, "zero_unreviewed_findings":True, "trusted_builtin_rules":True,
                 "repository_allowlists_ignored":True, "tracked_files_scanned":1, "all_history_scanned":False,
                 "secrets_dependencies_certified":False, "block1_certified":False, "paid_calls":0, "production_writes":0}
    else:
        value = {"schema":"factory-block1-npm-advisory-evidence-v1", "sha":SOURCE_SHA,
                 "scope":"production_dependencies_lockfile", "scanner":"npm audit", "valid_report":True,
                 "passed":True, "high":0, "critical":0, "scanner_exit_code":0, "block1_certified":False}
    return value


def archive(kind, member):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(member, json.dumps(receipt(kind), sort_keys=True))
    return output.getvalue()


def fixture(sha="f" * 40):
    root = "/repos/" + REPO
    values = {root + "/git/ref/heads/main":{"object":{"sha":sha}},
              root + "/actions/runs/123":{"id":123,"name":"Factory autonomous runner","path":OWNER_WORKFLOW,"event":"workflow_run","head_sha":sha,"head_branch":"main","run_attempt":1},
              root + "/compare/" + MERGE_SHA + "..." + sha:{"status":"ahead","behind_by":0,"merge_base_commit":{"sha":MERGE_SHA}}}
    raw = {}
    for run_id, name, kind, artifact_name, artifact_id, member, workflow, steps in SCANS:
        item = archive(kind, member); raw[artifact_id] = item
        values[root + "/actions/runs/" + str(run_id)] = {"id":run_id,"name":name,"path":workflow,"event":"pull_request","head_sha":SOURCE_SHA,"status":"completed","conclusion":"success","run_attempt":1}
        values[root + "/actions/runs/" + str(run_id) + "/jobs?per_page=100"] = {"total_count":1,"jobs":[{"run_id":run_id,"head_sha":SOURCE_SHA,"status":"completed","conclusion":"success","steps":[{"name":x,"status":"completed","conclusion":"success"} for x in steps]}]}
        values[root + "/actions/runs/" + str(run_id) + "/artifacts?per_page=100"] = {"total_count":1,"artifacts":[{"id":artifact_id,"name":artifact_name,"expired":False,"digest":"sha256:" + hashlib.sha256(item).hexdigest(),"size_in_bytes":len(item),"archive_download_url":"https://api.github.com" + root + "/actions/artifacts/" + str(artifact_id) + "/zip","workflow_run":{"id":run_id,"head_sha":SOURCE_SHA,"head_repository_id":1387883686}}]}
    for path in SOURCE_FILES:
        values[root + "/contents/" + path + "?ref=" + SOURCE_SHA] = {"sha":"a" * 40,"size":1}
        values[root + "/contents/" + path + "?ref=" + sha] = {"sha":"a" * 40,"size":1}
    return values, raw


class IndependentSecurityEvidenceTests(unittest.TestCase):
    def proof(self, values=None, raw=None, sha="f" * 40):
        values, raw = fixture(sha) if values is None else (values, raw)
        return verify_existing_secrets_dependencies(repository=REPO, assessed_commit=sha,
            github_get=lambda path: values[path], archive_fetch=lambda url, token, ident: raw[ident], environment=environment())

    def test_exact_runs_and_bounded_receipts_only_pass_security_cell(self):
        proof = self.proof()
        self.assertEqual((proof.domain, proof.criterion), ("security", "secrets_dependencies"))
        self.assertEqual(proof.retained_receipt["npm"]["critical"], 0)

    def test_artifact_digest_step_drift_and_receipt_lie_fail_closed(self):
        for mutation in ("digest", "step", "drift", "receipt"):
            values, raw = fixture(); root = "/repos/" + REPO
            if mutation == "digest":
                values[root + "/actions/runs/" + str(SCANS[0][0]) + "/artifacts?per_page=100"]["artifacts"][0]["digest"] = "sha256:" + "0" * 64
            elif mutation == "step":
                values[root + "/actions/runs/" + str(SCANS[1][0]) + "/jobs?per_page=100"]["jobs"][0]["steps"] = []
            elif mutation == "drift":
                values[root + "/contents/" + SOURCE_FILES[0] + "?ref=" + "f" * 40]["sha"] = "b" * 40
            else:
                member = SCANS[1][5]; changed = io.BytesIO()
                bad = receipt("npm"); bad["critical"] = 1
                with zipfile.ZipFile(changed, "w", zipfile.ZIP_DEFLATED) as zf: zf.writestr(member, json.dumps(bad))
                raw[SCANS[1][4]] = changed.getvalue()
                values[root + "/actions/runs/" + str(SCANS[1][0]) + "/artifacts?per_page=100"]["artifacts"][0]["digest"] = "sha256:" + hashlib.sha256(changed.getvalue()).hexdigest()
            with self.subTest(mutation=mutation), self.assertRaises(SecurityEvidenceBlocked): self.proof(values, raw)

    def test_builder_never_trusts_unrelated_security_provider(self):
        proof = VerifiedCriterionEvidence(domain="security", criterion="secrets_dependencies", repository=TEST_REPO, assessed_commit=TEST_SHA, verification_state="reviewed", source="trusted", evidence=("proof:" + TEST_SHA,), retained_receipt={"safe":True})
        with patch("build_readiness_evidence_manifest.verify_existing_secrets_dependencies", return_value=proof):
            report = build_verified_baseline(repository=TEST_REPO, sha=TEST_SHA, github_get=lambda path: github()[path], verify_secrets_dependencies=True)
        row = next(x for x in report["criteria"] if x["domain"] == "security" and x["criterion"] == "secrets_dependencies")
        self.assertEqual(row["status"], "passed")


if __name__ == "__main__": unittest.main()
