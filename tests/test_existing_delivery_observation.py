from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from ai_product_factory.existing_delivery_observation import inspect_prior_merged_delivery

REPO="leandrosilveiradepaula/crm-infodive"
SOURCE="fea4669258fcd832c7e187e7b00c1c5fb4d90a76"
MERGE="e87048c92aa38249e67d87fe9432d79f09d40dbd"
CANDIDATE="f5f7d91f8e98cfaf482cca72c974abb7a82f6a5e"
PATH="src/services/ContractService.ts"

def fixture():
    g=MagicMock()
    g.repository=REPO
    g._call.return_value={"total_count":2,"items":[
        {"number":208,"pull_request":{},"body":"CRM issue #171 governance task"},
        {"number":172,"pull_request":{},"body":"Issue #171: fix enormous IN list"},
    ]}
    def pr(number):
        return SimpleNamespace(
            number=number,merged=True,state="closed",head_repository=REPO,
            merge_commit_sha=MERGE if number==172 else "d"*40,
            head_sha="c"*40,base_ref="product/hardening-release-candidate",
        )
    g.get_pull_request.side_effect=pr
    g.get_pull_request_files.side_effect=lambda number: (
        (PATH,"src/lib/contract-owner-access.test.ts") if number==172
        else ("docs/codex/CURRENT_TASK.md",)
    )
    g.get_branch_sha.return_value=CANDIDATE
    g.compare_commits.return_value={
        "status":"ahead","ahead_by":18,"behind_by":0,
    }
    g.get_file_text.side_effect=lambda path,ref: "legacy IN" if ref==SOURCE else "fixed relational join"
    return g

def inspect(g):
    return inspect_prior_merged_delivery(
        g,issue_number=171,source_sha=SOURCE,source_evidence={
            "assessed_commit":SOURCE,
            "inspected_files":[{"path":PATH,"assessed_commit":SOURCE,"complete":True,"content":"legacy IN"}],
            "omitted_paths":[],
        },
    )

class ExistingDeliveryObservationTests(unittest.TestCase):
    def test_crm171_unique_code_pr_not_governance_pr(self):
        g=fixture()
        result=inspect(g)
        self.assertEqual(result["status"],"existing_delivery_candidate_unverified")
        self.assertEqual(result["pr_number"],172)
        self.assertEqual(result["candidate_sha"],CANDIDATE)
        self.assertEqual(result["matched_files"],[PATH])
        self.assertEqual(result["original_source_sha"],SOURCE)
        self.assertFalse(result["release_authorized"])
        self.assertFalse(result["ci_verified"])
        self.assertFalse(result["product_ready"])
        self.assertTrue(result["source_binding_unchanged"])

    def test_ambiguous_prs_fail_closed(self):
        g=fixture()
        g.get_pull_request_files.side_effect=lambda n: (PATH,)
        self.assertIsNone(inspect(g))

    def test_unmerged_pr_or_cross_repo_rejected(self):
        g=fixture()
        old=g.get_pull_request.side_effect
        g.get_pull_request.side_effect=lambda n: SimpleNamespace(
            **{**vars(old(n)),"head_repository":"attacker/repo"}
        )
        self.assertIsNone(inspect(g))

    def test_branch_lineage_or_sha_drift_rejected(self):
        for wrong in [
            {"status":"diverged","ahead_by":3,"behind_by":1},
            {"status":"behind","ahead_by":0,"behind_by":1},
        ]:
            g=fixture()
            g.compare_commits.return_value=wrong
            with self.subTest(wrong=wrong):
                self.assertIsNone(inspect(g))
        g=fixture()
        g.get_branch_sha.side_effect=[CANDIDATE,"b"*40]
        self.assertIsNone(inspect(g))

    def test_equal_content_does_not_count_as_candidate(self):
        g=fixture()
        g.get_file_text.return_value="same"
        g.get_file_text.side_effect=None
        self.assertIsNone(inspect(g))

    def test_missing_or_truncated_search_is_inconclusive(self):
        for count in (0,11):
            g=fixture()
            g._call.return_value={"total_count":count,"items":[]}
            with self.subTest(count=count):
                self.assertIsNone(inspect(g))
        g=fixture()
        g._call.side_effect=RuntimeError("GitHub offline")
        self.assertIsNone(inspect(g))

    def test_truncated_source_not_a_candidate(self):
        g=fixture()
        result=inspect_prior_merged_delivery(
            g,issue_number=171,source_sha=SOURCE,
            source_evidence={"assessed_commit":SOURCE,"inspected_files":[
                {"path":PATH,"complete":False,"assessed_commit":SOURCE},
            ],"omitted_paths":[]},
        )
        self.assertIsNone(result)
        g._call.assert_not_called()

if __name__=="__main__":
    unittest.main()
