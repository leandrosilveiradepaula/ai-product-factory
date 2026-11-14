"""Regression coverage for exact-SHA specialist reconciliation receipts."""
import unittest
from ai_product_factory.candidate_pr_receipt import validate_create_pr_candidate


class CandidateReceiptTests(unittest.TestCase):
    def test_numeric_pr_number_matches_audited_receipt(self):
        receipt={"previous_commit":"a"*40,"candidate_commit":"b"*40,
                 "change_set_id":"change-1","pr_number":2,"old_sha":"a"*40,
                 "new_sha":"b"*40,"compare_status":"ahead"}
        reads=[]
        def read(query):
            reads.append(query)
            return [{"metadata":receipt}]
        validate_create_pr_candidate(
            read=read,run_id="run-1",pr_number=2,original_head="a"*40,
            candidate_commit="b"*40,
            run_metadata={"source":"change-set","change_set_id":"change-1"})
        self.assertEqual(len(reads),1)
        self.assertIn("operation=eq.reconcile_pr_candidate",reads[0])

    def test_identity_mismatch_and_boolean_are_fail_closed(self):
        base={"previous_commit":"a"*40,"candidate_commit":"b"*40,
              "change_set_id":"change-1","pr_number":2,"old_sha":"a"*40,
              "new_sha":"b"*40,"compare_status":"ahead"}
        for changed in ({"pr_number":True},{"pr_number":3},
                        {"candidate_commit":"c"*40},{"old_sha":"c"*40},
                        {"change_set_id":"other"},{"compare_status":"diverged"}):
            with self.subTest(changed=changed):
                def read(_query):
                    return [{"metadata":{**base,**changed}}]
                with self.assertRaisesRegex(RuntimeError,"does not match PR"):
                    validate_create_pr_candidate(
                        read=read,run_id="run-1",pr_number=2,
                        original_head="a"*40,candidate_commit="b"*40,
                        run_metadata={"source":"change-set","change_set_id":"change-1"})


if __name__=="__main__":
    unittest.main()
