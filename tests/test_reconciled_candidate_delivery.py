import json
import unittest
from unittest.mock import patch

from ai_product_factory.candidate_pr_receipt import validate_create_pr_candidate
from ai_product_factory.specialist_lane_queue import SupabaseSpecialistLaneQueue
from ai_product_factory.preview_followup_queue import SupabasePreviewFollowupQueue


class Response:
    def __init__(self,data):self.data=data
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self):return json.dumps(self.data).encode()


OLD = "a" * 40
NEW = "b" * 40

def receipt(pr="180",new=NEW,old=OLD,change_set="cs"):
    return [{"metadata":{
        "pr_number":pr,"previous_commit":old,"candidate_commit":new,
        "change_set_id":change_set,"old_sha":old,"new_sha":new,
        "compare_status":"ahead","ahead_by":"1","behind_by":"0",
    }}]


def runmeta():
    return {"source":"change-set","change_set_id":"cs","github_issue":{"number":179}}


class CandidateReceiptTests(unittest.TestCase):
    def test_direct_pr_candidate_requires_no_additional_lookup(self):
        validate_create_pr_candidate(read=lambda path: self.fail("unexpected lookup"),
            run_id="r",pr_number=180,original_head="same",
            candidate_commit="same",run_metadata={})

    def test_reconciled_candidate_accepts_exact_receipt(self):
        calls=[]
        def read(path):
            calls.append(path)
            return receipt()
        validate_create_pr_candidate(read=read,run_id="r",pr_number=180,
            original_head=OLD,candidate_commit=NEW,run_metadata=runmeta())
        self.assertEqual(len(calls),1)
        self.assertIn("operation=eq.reconcile_pr_candidate",calls[0])

    def test_rejects_unrelated_receipts_and_missing_change_set_binding(self):
        for data in ([],receipt(pr="181"),receipt(new="other"),
                     receipt(old="other"),receipt(change_set="other"),
                     [{"metadata":{}}]):
            with self.subTest(data=data):
                with self.assertRaises(RuntimeError):
                    validate_create_pr_candidate(read=lambda path:data,run_id="r",
                        pr_number=180,original_head=OLD,candidate_commit=NEW,
                        run_metadata=runmeta())
        with self.assertRaises(RuntimeError):
            validate_create_pr_candidate(read=lambda path:receipt(),run_id="r",
                pr_number=180,original_head=OLD,candidate_commit=NEW,
                run_metadata={"source":"operator_reconciled_dogfood"})

    def test_specialist_claim_accepts_reconciliation_at_exact_new_sha(self):
        claimed={"run_id":"r","job_id":"j","project_key":"crm",
                 "repository":"owner/crm","role":"security",
                 "candidate_commit":NEW,"manifest":{},
                 "claim_token":"123e4567-e89b-42d3-a456-426614174099",
                 "execution_generation":4}
        rows=[Response(claimed),
              Response([{"metadata":{"pr":180,"head_sha":OLD}}]),
              Response([{"task_id":"t","execution_route":"direct","branch_name":"factory/reconciled-candidate",
                         "metadata":{**runmeta(),"execution_generation":4}}]),
              Response(receipt()),
              Response([{"project_id":"123e4567-e89b-42d3-a456-426614174000","acceptance_criteria":["works"]}])]
        with patch("urllib.request.urlopen",side_effect=rows):
            obj=SupabaseSpecialistLaneQueue(url="https://x.supabase.co",secret_key="sb_secret_x")
            item=obj.claim("security","worker")
        self.assertEqual(item.pr_number,180)
        self.assertEqual(item.candidate_commit,NEW)
        self.assertEqual(item.branch,"factory/reconciled-candidate")

    def test_specialist_claim_rejects_mismatched_reconciliation(self):
        claimed={"run_id":"r","job_id":"j","project_key":"crm",
                 "repository":"owner/crm","role":"security",
                 "candidate_commit":NEW,"manifest":{},
                 "claim_token":"123e4567-e89b-42d3-a456-426614174099",
                 "execution_generation":4}
        rows=[Response(claimed),
              Response([{"metadata":{"pr":180,"head_sha":OLD}}]),
              Response([{"task_id":"t","execution_route":"direct","branch_name":"factory/reconciled-candidate",
                         "metadata":{**runmeta(),"execution_generation":4}}]),
              Response(receipt(pr="181"))]
        with patch("urllib.request.urlopen",side_effect=rows):
            obj=SupabaseSpecialistLaneQueue(url="https://x.supabase.co",secret_key="sb_secret_x")
            with self.assertRaisesRegex(RuntimeError,"reconciliation chain"):
                obj.claim("security","worker")

    def test_preview_queue_accepts_reconciled_sha_with_exact_quality_gate(self):
        run={"id":"r","task_id":"t","branch_name":"factory/branch",
             "candidate_commit":NEW,"metadata":runmeta()}
        rows=[
            Response([run]),Response([]),
            Response([{"project_id":"p","risk":{}}]),
            Response([{"project_key":"crm","repository":"owner/crm","manifest":{}}]),
            Response([{"metadata":{"pr":180,"head_sha":OLD}}]),
            Response(receipt()),
            Response([{"status":"success","baseline_ref":NEW,"result":{"passed":True}}]),
        ]
        with patch("urllib.request.urlopen",side_effect=rows):
            obj=SupabasePreviewFollowupQueue(url="https://x.supabase.co",secret_key="sb_secret_x")
            item=obj.next_pending()
        self.assertEqual(item.candidate_commit,NEW)
        self.assertEqual(item.pr_number,180)


if __name__=="__main__":unittest.main()
