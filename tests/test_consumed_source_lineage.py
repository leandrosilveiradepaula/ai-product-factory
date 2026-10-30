"""Exact CRM #203 -> #205 fixture for consumed, immutable Preview source."""
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ai_product_factory.consumed_source_lineage import attest_consumed_preview_source
from ai_product_factory.nonproduction_candidate_repin import repin_project

PROJECT_ID="2d30e00a-ff72-4044-b838-011c263ed672"
CHANGE_SET="61bc7a1f-dcab-4616-9ce7-1ff28a0aa915"
ROOT_TASK="f97008cc-ce87-436f-8a73-534a4f693288"
REPO="leandrosilveiradepaula/crm-infodive"
BRANCH="preview/crm22-admin-audit-next"
SOURCE="eb628ca165c43a814b70055b3463d5d980807608"
IMPLEMENTATION="4ad04ae668905d3c9110d6925d8bf345132e6db0"
PREVIEW="24c8e4c15332c583d322772b0acbd7262951de56"
FILES=["src/app/(dashboard)/settings/users-actions.ts","test/server-admin-actions-rbac.test.ts"]

def project():
    return {
        "id":PROJECT_ID,"project_key":"crm-infodive","repository":REPO,
        "project_kind":"existing","is_active":True,
        "manifest":{"delivery_target":{
            "schema_version":1,"mode":"open_pr_candidate",
            "repository":REPO,"branch":BRANCH,"sha":SOURCE,
            "candidate_pr_number":203,
            "repin_policy":{"schema_version":1,"enabled":True,"native_ci":{
                "schema_version":1,"workflow_name":"CRM validation",
                "workflow_id":372542929,
                "workflow_path":".github/workflows/crm-validation.yml",
                "event":"pull_request"}}}},
        "execution_control":{"state":"running","generation":16,"version":15},
    }

def receipt():
    return {
        "id":CHANGE_SET,"project_id":PROJECT_ID,"root_task_id":ROOT_TASK,
        "status":"completed","source_commit":SOURCE,
        "candidate_commit":IMPLEMENTATION,
        "metadata":{
            "integrated_files":list(FILES),
            "integration_epoch_receipt":{
                "project_id":PROJECT_ID,"generation":16,
                "candidate_commit":IMPLEMENTATION},
            "integration_release_request":{
                "pr_number":205,"candidate_commit":IMPLEMENTATION,
                "branch":"factory/change-set-61bc7a1f"},
            "nonproduction_integration":{
                "merged":True,"environment":"preview",
                "repository":REPO,"base_ref":BRANCH,
                "head_ref":"factory/change-set-61bc7a1f",
                "head_sha":IMPLEMENTATION,"candidate_commit":IMPLEMENTATION,
                # Exact JSONB shape observed in Supabase Control Plane.
                # This field is text, unlike integration_release_request.pr_number.
                "pr_number":"205","merge_sha":PREVIEW,
                "production_released":False},
        }
    }

def fake_github():
    g=MagicMock()
    g.repository=REPO
    g.get_branch_sha.return_value=PREVIEW
    source=SimpleNamespace(number=203,state="open",merged=False,draft=True,
        head_sha=PREVIEW,head_ref=BRANCH,head_repository=REPO,base_ref="main")
    merged=SimpleNamespace(number=205,state="closed",merged=True,draft=False,
        head_sha=IMPLEMENTATION,head_ref="factory/change-set-61bc7a1f",
        head_repository=REPO,base_ref=BRANCH,merge_commit_sha=PREVIEW)
    g.get_pull_request.side_effect=lambda n: {203:source,205:merged}[n]
    g.get_pull_request_files.return_value=tuple(FILES)
    g.compare_commits.return_value={
        "status":"ahead","ahead_by":1,"behind_by":0,"files":list(FILES)}
    return g

class ConsumedSourceLineageTests(unittest.TestCase):
    def attest(self,g=None,rows=None,p=None):
        p=p or project()
        from ai_product_factory.pinned_nonproduction_target import PinnedNonproductionTarget
        target=PinnedNonproductionTarget.parse(p["manifest"]["delivery_target"],repository=REPO)
        return attest_consumed_preview_source(
            g or fake_github(),project=p,target=target,
            observed_sha=PREVIEW,records=[receipt()] if rows is None else rows)

    def test_real_change_set_merge_is_consumed_not_new_source(self):
        proof=self.attest()
        self.assertEqual(proof.source_sha,SOURCE)
        self.assertEqual(proof.preview_merge_sha,PREVIEW)
        self.assertEqual(proof.implementation_sha,IMPLEMENTATION)
        self.assertEqual(proof.execution_generation,16)

    def test_exact_persisted_decimal_pr_number_is_normalized_to_github_id(self):
        # JSON serialization preserves the mixed types from the actual
        # Change Set receipt: nonproduction_integration.pr_number is a string,
        # while the integration request and GitHub REST PR number are numeric.
        import json
        persisted=json.loads(json.dumps(receipt()))
        observed=persisted["metadata"]["nonproduction_integration"]["pr_number"]
        requested=persisted["metadata"]["integration_release_request"]["pr_number"]
        self.assertEqual(observed,"205")
        self.assertEqual(requested,205)
        proof=self.attest(rows=[persisted])
        self.assertEqual(proof.implementation_pr,205)
        self.assertIs(type(proof.implementation_pr),int)
        # Older receipts with a numeric JSON field stay compatible.
        persisted["metadata"]["nonproduction_integration"]["pr_number"]=205
        self.assertEqual(self.attest(rows=[persisted]).implementation_pr,205)

    def test_only_canonical_decimal_pr_identity_is_accepted(self):
        invalid=(None,True,False,0,-1,205.0, "0","0205","+205",
                 "2e2","205.0","205 "," 205","205\\n","205x", [], {},
                 2147483648, "2147483648")
        for bad in invalid:
            row=receipt()
            row["metadata"]["nonproduction_integration"]["pr_number"]=bad
            with self.subTest(invalid=repr(bad)),self.assertRaises(PermissionError):
                self.attest(rows=[row])
        for bad in (None,True,205.0,"0205","205x",2147483648):
            row=receipt()
            row["metadata"]["integration_release_request"]["pr_number"]=bad
            with self.subTest(request_invalid=repr(bad)),self.assertRaises(PermissionError):
                self.attest(rows=[row])

    def test_repin_defers_consumed_source_without_cas_or_actions(self):
        g=fake_github()
        with patch(
            "ai_product_factory.nonproduction_candidate_repin._fetch_consumed_source_rows",
            return_value=[receipt()]
        ):
            rpc=MagicMock()
            result=repin_project(project(),github_factory=lambda _:g,rpc=rpc)
        self.assertEqual(result,{"status":"deferred",
            "project_key":"crm-infodive",
            "reason_code":"candidate_source_consumed","observed_sha":PREVIEW})
        rpc.assert_not_called()
        g._call.assert_not_called()

    def test_missing_proof_does_not_claim_source_consumed(self):
        self.assertIsNone(self.attest(rows=[]))
        incomplete=receipt()
        del incomplete["metadata"]["nonproduction_integration"]
        self.assertIsNone(self.attest(rows=[incomplete]))

    def test_forged_receipts_and_wrong_epoch_block(self):
        cases=[
            lambda row: row.update(project_id="different"),
            lambda row: row.update(source_commit="0"*40),
            lambda row: row["metadata"]["integration_epoch_receipt"].update(generation=15),
            lambda row: row["metadata"]["nonproduction_integration"].update(head_sha="0"*40),
            lambda row: row["metadata"]["nonproduction_integration"].update(merged=False),
            lambda row: row["metadata"]["nonproduction_integration"].update(base_ref="main"),
            lambda row: row["metadata"]["integration_release_request"].update(pr_number=206),
            lambda row: row["metadata"].update(integrated_files=["src/evil.ts"]),
            lambda row: row.update(status="running"),
        ]
        for i,mutate in enumerate(cases):
            row=receipt()
            mutate(row)
            with self.subTest(case=i):
                if i in (0,1,8):
                    self.assertIsNone(self.attest(rows=[row]))
                else:
                    with self.assertRaises(PermissionError):
                        self.attest(rows=[row])

    def test_branch_move_pr_drift_and_wrong_scope_fail_closed(self):
        for kind in ("branch","merge-pr","source-pr","file-scope","ancestry"):
            g=fake_github()
            if kind=="branch":
                g.get_branch_sha.return_value="0"*40
            elif kind=="merge-pr":
                old=g.get_pull_request.side_effect
                g.get_pull_request.side_effect=lambda n: (
                    SimpleNamespace(**{**vars(old(n)),"merged":False}) if n==205
                    else old(n))
            elif kind=="source-pr":
                old=g.get_pull_request.side_effect
                g.get_pull_request.side_effect=lambda n: (
                    SimpleNamespace(**{**vars(old(n)),"head_sha":"0"*40}) if n==203
                    else old(n))
            elif kind=="file-scope":
                g.get_pull_request_files.return_value=("src/foreign.py",)
            elif kind=="ancestry":
                g.compare_commits.return_value={
                    "status":"diverged","ahead_by":1,"behind_by":1,"files":FILES}
            with self.subTest(kind=kind),self.assertRaises(PermissionError):
                self.attest(g=g)

    def test_duplicate_or_unbounded_evidence_blocks(self):
        with self.assertRaises(PermissionError):
            self.attest(rows=[receipt(),receipt()])
        with self.assertRaises(PermissionError):
            self.attest(rows=[receipt()]*21)

if __name__=="__main__":
    unittest.main()
