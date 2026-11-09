"""Independent requirements ledger: real blob bytes, gaps and runner identity."""
from __future__ import annotations

import copy
import hashlib
import tempfile
import unittest
from pathlib import Path

from ai_product_factory.product_readiness_certification import conservative_verified_manifest
from scripts.trace_block1_requirements import (
    CANDIDATES, JOURNEY_STAGES, RequirementsInventoryBlocked,
    _git_blob_oid, matrix, verify_requirements_inventory,
)
from tests.test_product_readiness_certification import github, REPO, SHA

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "/repos/" + REPO
RUN = 42
SOURCE = 7


def fixture():
    tree = [
        {"path": path, "type": "blob", "mode": "100644",
         "sha": _git_blob_oid((ROOT / path).read_bytes())}
        for path in sorted({p for refs in CANDIDATES.values() for p in refs})
    ]
    data = github()
    data.update({
        PREFIX + "/actions/runs/" + str(RUN): {
            "id": RUN, "name": "Factory autonomous runner",
            "path": ".github/workflows/autonomous-runner.yml",
            "event": "workflow_run", "head_branch": "main",
            "head_sha": SHA, "status": "in_progress", "run_attempt": 1,
        },
        PREFIX + "/git/trees/" + SHA + "?recursive=1": {
            "truncated": False, "tree": tree,
        },
    })
    return data


def environment():
    return {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": REPO,
        "GITHUB_EVENT_NAME": "workflow_run",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_WORKFLOW_REF":
            REPO + "/.github/workflows/autonomous-runner.yml@refs/heads/main",
        "GITHUB_RUN_ID": str(RUN),
    }


def event():
    return {"workflow_run": {
        "id": SOURCE, "name": "validate", "path": ".github/workflows/validate.yml",
        "event": "push", "status": "completed", "conclusion": "success",
        "head_sha": SHA, "head_branch": "main", "run_attempt": 1,
        "repository": {"full_name": REPO},
    }}


class RequirementsInventoryEvidenceTests(unittest.TestCase):
    def proof(self, data=None, env=None, payload=None, root=None, criteria=None):
        sources = fixture() if data is None else data
        # Build baseline from unmodified CI first, then mutate only the
        # verifier's own independent source. Otherwise the upstream
        # conservative certifier correctly rejects the fixture before
        # the target negative path can be exercised.
        rows = (conservative_verified_manifest(
            repository=REPO, assessed_commit=SHA,
            github_get=lambda path: fixture()[path],
        )["criteria"] if criteria is None else criteria)
        return verify_requirements_inventory(
            repository=REPO, assessed_commit=SHA,
            github_get=lambda path: sources[path],
            root=ROOT if root is None else root, environment=environment() if env is None else env,
            event_payload=event() if payload is None else payload, criteria=rows,
        )

    def test_complete_inventory_is_only_a_bounded_criterion_attestation(self):
        proof = self.proof()
        self.assertEqual((proof.domain, proof.criterion),
                         ("functional_completeness", "requirements_inventory"))
        self.assertEqual(proof.retained_receipt["mapped_criteria"], 19)
        self.assertEqual(proof.retained_receipt["source_blobs_verified"],
                         len({p for refs in CANDIDATES.values() for p in refs}))
        self.assertIn("functional_completeness/critical_journeys",
                      proof.retained_receipt["unverified_other_criteria"])
        self.assertFalse(proof.retained_receipt["product_ready"])
        self.assertEqual(proof.retained_receipt["production_writes"], 0)
        self.assertEqual(proof.retained_receipt["paid_calls"], 0)
        self.assertEqual(set(CANDIDATES), set(JOURNEY_STAGES))
        self.assertTrue(all(row["journey_stages"] for row in matrix(ROOT)["requirements"]))

    def test_all_negative_provenance_mutations_block(self):
        for mutation in ("missing_blob", "modified_blob", "duplicate_blob",
                         "symlink_mode", "truncated", "failed_job",
                         "fake_runner", "head_changed", "forged_upstream"):
            data, env, payload = fixture(), environment(), event()
            nodes = data[PREFIX + "/git/trees/" + SHA + "?recursive=1"]["tree"]
            if mutation == "missing_blob":
                nodes.pop()
            elif mutation == "modified_blob":
                nodes[0]["sha"] = "f" * 40
            elif mutation == "duplicate_blob":
                nodes.append(dict(nodes[0]))
            elif mutation == "symlink_mode":
                nodes[0]["mode"] = "120000"
            elif mutation == "truncated":
                data[PREFIX + "/git/trees/" + SHA + "?recursive=1"]["truncated"] = True
            elif mutation == "failed_job":
                data[PREFIX + "/actions/runs/7/jobs?per_page=100"]["jobs"][0]["conclusion"] = "failure"
            elif mutation == "fake_runner":
                env["GITHUB_EVENT_NAME"] = "workflow_dispatch"
            elif mutation == "head_changed":
                data[PREFIX + "/git/ref/heads/main"]["object"]["sha"] = "c" * 40
            elif mutation == "forged_upstream":
                payload["workflow_run"]["head_branch"] = "feature"
            with self.subTest(mutation=mutation):
                with self.assertRaises(RequirementsInventoryBlocked):
                    self.proof(data=data, env=env, payload=payload)

    def test_criterion_mapping_and_gap_rewriting_cannot_hide_unverified_journeys(self):
        sources = fixture()
        rows = conservative_verified_manifest(
            repository=REPO, assessed_commit=SHA,
            github_get=lambda path: sources[path],
        )["criteria"]
        orig = self.proof(data=sources, criteria=rows)
        altered = copy.deepcopy(rows)
        altered["functional_completeness"]["critical_journeys"]["status"] = "passed"
        replaced = self.proof(data=sources, criteria=altered)
        self.assertNotEqual(orig.retained_receipt["other_criteria_status_digest"],
                            replaced.retained_receipt["other_criteria_status_digest"])
        altered = copy.deepcopy(rows)
        altered["security"].pop("authn_authz")
        with self.assertRaises(RequirementsInventoryBlocked):
            self.proof(data=sources, criteria=altered)

    def test_local_modified_checkout_cannot_be_attested(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for path in {p for refs in CANDIDATES.values() for p in refs}:
                to = root / path
                to.parent.mkdir(parents=True, exist_ok=True)
                to.write_bytes((ROOT / path).read_bytes())
            self.assertEqual(self.proof(root=root).criterion, "requirements_inventory")
            target = root / "PROJECT_PLAN.md"
            target.write_bytes(target.read_bytes() + b"\nforged")
            with self.assertRaises(RequirementsInventoryBlocked):
                self.proof(root=root)
