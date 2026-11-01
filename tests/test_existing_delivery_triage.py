from __future__ import annotations

from unittest import TestCase
from unittest.mock import MagicMock

from ai_product_factory.existing_delivery_triage import classify_existing_delivery

REPO="leandrosilveiradepaula/crm-infodive"
SHA="f5f7d91f8e98cfaf482cca72c974abb7a82f6a5e"
SOURCE="fea4669258fcd832c7e187e7b00c1c5fb4d90a76"
BRANCH="product/hardening-release-candidate"
POLICY={"workflow_id":372542929,"workflow_path":".github/workflows/crm-validation.yml",
        "workflow_name":"CRM validation","event":"pull_request"}


def fixture():
    github=MagicMock()
    github.repository=REPO
    github.get_branch_sha.return_value=SHA
    run={
        "id":38584240284,"run_attempt":1,"head_sha":SHA,
        "workflow_id":POLICY["workflow_id"],"path":POLICY["workflow_path"],
        "name":POLICY["workflow_name"],"event":POLICY["event"],
        "status":"completed","conclusion":"success",
    }
    github._call.side_effect=[
        {"total_count":1,"workflow_runs":[run]},
        {"total_count":2,"jobs":[
            {"run_id":run["id"],"status":"completed","conclusion":"success"},
            {"run_id":run["id"],"status":"completed","conclusion":"success"},
        ]},
    ]
    witness={"status":"existing_delivery_candidate_unverified",
        "repository":REPO,"issue_number":171,"original_source_sha":SOURCE,
        "pr_number":172,"pr_merge_commit":"e87048c92aa38249e67d87fe9432d79f09d40dbd",
        "candidate_ref":BRANCH,"candidate_sha":SHA,
        "matched_files":["src/services/ContractService.ts"],
        "source_binding_unchanged":True,"ci_verified":False,
        "release_authorized":False,"product_ready":False}
    return github,witness


class ExistingDeliveryTriageTests(TestCase):
    def test_crm171_native_ci_evidence_is_review_only(self):
        github,witness=fixture()
        result=classify_existing_delivery(github,witness=witness,ci_policy=POLICY)
        self.assertEqual(result["status"],"awaiting_existing_delivery_reconciliation")
        self.assertEqual(result["decision"],"review_existing_candidate_not_reimplement")
        self.assertEqual(result["ci_evidence_state"],"exact_sha_native_actions_success")
        self.assertTrue(result["ci_verified"])
        self.assertEqual(result["ci_run_id"],38584240284)
        self.assertFalse(result["release_authorized"])
        self.assertFalse(result["product_ready"])
        self.assertTrue(result["source_binding_unchanged"])
        self.assertEqual(result["original_source_sha"],SOURCE)
        self.assertEqual(witness["status"],"existing_delivery_candidate_unverified")

    def test_absent_or_invalid_policy_never_claims_ci(self):
        for policy in (None,{},{"workflow_id":0}, {"workflow_id":372542929,"event":"workflow_dispatch"}):
            github,witness=fixture()
            with self.subTest(policy=policy):
                result=classify_existing_delivery(github,witness=witness,ci_policy=policy)
                self.assertFalse(result["ci_verified"])
                github._call.assert_not_called()

    def test_wrong_or_failed_workflow_cannot_certify(self):
        for modifier in (
            lambda run:run.update(head_sha="b"*40),
            lambda run:run.update(workflow_id=3),
            lambda run:run.update(event="schedule"),
            lambda run:run.update(status="in_progress"),
            lambda run:run.update(conclusion="failure"),
        ):
            github,witness=fixture()
            run={"id":38584240284,"run_attempt":1,"head_sha":SHA,
                "workflow_id":372542929,"path":POLICY["workflow_path"],
                "name":"CRM validation","event":"pull_request",
                "status":"completed","conclusion":"success"}
            modifier(run)
            github._call.side_effect=[
                {"total_count":1,"workflow_runs":[run]},
                {"total_count":1,"jobs":[{"run_id":run["id"],"status":"completed","conclusion":"success"}]},
            ]
            result=classify_existing_delivery(github,witness=witness,ci_policy=POLICY)
            self.assertFalse(result["ci_verified"])

    def test_partial_jobs_fail_closed(self):
        github,witness=fixture()
        github._call.side_effect=[
            {"total_count":1,"workflow_runs":[{
                "id":38584240284,"run_attempt":1,"head_sha":SHA,"workflow_id":372542929,
                "path":POLICY["workflow_path"],"name":"CRM validation",
                "event":"pull_request","status":"completed","conclusion":"success"}]},
            {"total_count":1,"jobs":[{"run_id":38584240284,"status":"completed","conclusion":"failure"}]},
        ]
        result=classify_existing_delivery(github,witness=witness,ci_policy=POLICY)
        self.assertFalse(result["ci_verified"])

    def test_ref_move_rejected_before_or_after_ci(self):
        for refs in ([("b"*40)], [SHA,"b"*40]):
            github,witness=fixture()
            github.get_branch_sha.side_effect=refs
            with self.subTest(refs=refs),self.assertRaises(PermissionError):
                classify_existing_delivery(github,witness=witness,ci_policy=POLICY)

    def test_untrusted_witness_never_causes_network_access(self):
        github,witness=fixture()
        witness["product_ready"]=True
        with self.assertRaises(PermissionError):
            classify_existing_delivery(github,witness=witness,ci_policy=POLICY)
        github._call.assert_not_called()

    def test_ci_outage_keeps_candidate_unverified(self):
        github,witness=fixture()
        github._call.side_effect=RuntimeError("GitHub unavailable")
        result=classify_existing_delivery(github,witness=witness,ci_policy=POLICY)
        self.assertFalse(result["ci_verified"])
        self.assertEqual(result["next_gate"],"independent_candidate_evaluation")
