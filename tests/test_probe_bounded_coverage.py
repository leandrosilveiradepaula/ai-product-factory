from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/"src/ai_product_factory/schedule_probe.py").read_text()

class BoundedProbeCoverageContractTests(unittest.TestCase):
    def test_status_partition_still_has_hard_limits(self):
        self.assertIn("order=created_at.desc&limit=200", SOURCE)
        self.assertIn("order=created_at.asc&limit=200", SOURCE)
        self.assertIn("missing[:400]",SOURCE)
        self.assertIn("range(0,len(bounded),40)",SOURCE)

    def test_join_lookup_is_exact_and_read_only(self):
        self.assertIn("def _linked_task_statuses(",SOURCE)
        self.assertIn('re.fullmatch(r"[A-Za-z0-9_-]{1,64}",task_id)',SOURCE)
        self.assertIn("&id=in.(",SOURCE)
        self.assertIn('"linked_task_lookup_truncated": linked_task_lookup_truncated',SOURCE)
        self.assertNotIn("factory_schedule_eligible_direct_run",SOURCE)
        self.assertNotIn("OPENAI_API_KEY",SOURCE)

if __name__=="__main__":
    unittest.main()
