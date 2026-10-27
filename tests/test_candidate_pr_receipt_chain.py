"""Adversarial offline tests for cumulative Factory PR candidate provenance."""
import copy
import unittest

from ai_product_factory.candidate_pr_receipt import validate_create_pr_candidate

ORIGINAL = "4" * 40
FIRST = "1" * 40
SECOND = "2" * 40
META = {"source": "change-set", "change_set_id": "change-123"}


def receipt(old: str, new: str, **extra):
    return {"metadata": {
        "old_sha": old, "new_sha": new,
        "previous_commit": old, "candidate_commit": new,
        "pr_number": "10", "change_set_id": "change-123",
        "compare_status": "ahead", "ahead_by": "1", "behind_by": "0",
        **extra,
    }}


def verify(records, *, candidate=SECOND, metadata=None):
    calls = []
    def read(path):
        calls.append(path)
        return copy.deepcopy(records)
    validate_create_pr_candidate(
        read=read,run_id="run-1",pr_number=10,
        original_head=ORIGINAL,candidate_commit=candidate,
        run_metadata=metadata if metadata is not None else META,
    )
    return calls


class Tests(unittest.TestCase):
    def test_two_hop_receipt_chain_reaches_immutable_original(self):
        calls = verify([receipt(FIRST, SECOND), receipt(ORIGINAL, FIRST)])
        self.assertEqual(len(calls), 1)
        self.assertIn("limit=9",calls[0])
        self.assertIn("order=created_at.desc,id.desc",calls[0])

    def test_original_head_requires_no_reconciliation(self):
        self.assertEqual(verify([],candidate=ORIGINAL),[])

    def test_single_hop_still_works(self):
        verify([receipt(ORIGINAL,FIRST)],candidate=FIRST)

    def test_cycle_and_gap_do_not_authorize_moved_branch(self):
        cases = [
            [receipt(FIRST, SECOND)],
            [receipt(FIRST, SECOND), receipt(SECOND, FIRST)],
            [receipt(FIRST, SECOND), receipt("3"*40, FIRST)],
            [receipt(ORIGINAL, FIRST), receipt(FIRST, SECOND)],
            [receipt(FIRST, SECOND), receipt(ORIGINAL, FIRST,pr_number="11")],
            [receipt(FIRST, SECOND), receipt(ORIGINAL, FIRST,change_set_id="wrong")],
            [receipt(FIRST, SECOND), receipt(ORIGINAL, FIRST,compare_status="diverged")],
            [receipt(FIRST, SECOND), receipt(ORIGINAL, FIRST,behind_by="1")],
            [receipt(FIRST, SECOND), receipt(ORIGINAL, FIRST,ahead_by="0")],
            [receipt(FIRST, SECOND), receipt(ORIGINAL, FIRST,old_sha="bad")],
            [receipt(FIRST, SECOND), receipt(ORIGINAL, FIRST,new_sha="bad")],
        ]
        for rows in cases:
            with self.subTest(rows=rows), self.assertRaises(RuntimeError):
                verify(rows)

    def test_unbounded_and_invalid_receipt_history_fail_closed(self):
        for invalid in ([], [{}], [{"metadata":[]}], ["not an object"],
                        [receipt(FIRST,SECOND)]*9):
            with self.subTest(invalid=str(invalid)[:60]),self.assertRaises(RuntimeError):
                verify(invalid)

    def test_no_change_set_or_trusted_source_rejected(self):
        for metadata in ({}, {"source":"operator"}, {"source":"change-set"},
                         {"source":"change-set","change_set_id":""}):
            with self.subTest(metadata=metadata),self.assertRaises(RuntimeError):
                verify([receipt(FIRST,SECOND),receipt(ORIGINAL,FIRST)],metadata=metadata)


if __name__ == "__main__":
    unittest.main()
