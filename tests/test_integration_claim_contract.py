import unittest
from unittest.mock import MagicMock

from ai_product_factory.change_set_store import SupabaseChangeSetStore


class IntegrationClaimContractTests(unittest.TestCase):
    def setUp(self):
        self.store=SupabaseChangeSetStore(url="https://example.supabase.co",service_role_key="secret")
        self.base={
            "change_set_id":"cs","project_key":"demo","repository":"owner/repo",
            "source_commit":"source","candidate_commit":"candidate",
            "integration_branch":"factory/change-set-cs","current_wave":1,
            "work_units":[{
                "plan_task_key":"a","base_commit":"candidate","output_commit":"out",
                "changed_files":["src/a.py"],
            }],
        }

    def test_empty_worker_rejected_before_rpc(self):
        self.store._rpc=MagicMock()
        with self.assertRaisesRegex(ValueError,"worker ID"):
            self.store.claim_integration(" ")
        self.store._rpc.assert_not_called()

    def test_empty_queue_is_not_an_error(self):
        self.store._rpc=MagicMock(return_value=None)
        self.assertIsNone(self.store.claim_integration("worker"))

    def test_valid_claim_preserves_exact_work_units(self):
        self.store._rpc=MagicMock(return_value=self.base)
        item=self.store.claim_integration("worker")
        self.assertEqual(item.current_wave,1)
        self.assertEqual(item.work_units[0]["output_commit"],"out")
        self.store._rpc.assert_called_once_with("factory_claim_change_set_integration",{
            "p_worker_id":"worker","p_lease_seconds":600,
        })

    def test_invalid_claims_fail_closed(self):
        cases=[
            ([], "non-object"),
            ({"project_key":""},"missing project_key"),
            ({"repository":None},"missing repository"),
            ({"current_wave":True},"invalid wave"),
            ({"current_wave":0},"invalid wave"),
            ({"work_units":[]},"no work units"),
            ({"work_units":[None]},"invalid work unit"),
            ({"work_units":[{"plan_task_key":"","base_commit":"candidate","output_commit":"out","changed_files":["src/a.py"]}]},"missing plan_task_key"),
            ({"work_units":[{"plan_task_key":"a","base_commit":"old","output_commit":"out","changed_files":["src/a.py"]}]},"stale candidate base"),
            ({"work_units":[{"plan_task_key":"a","base_commit":"candidate","output_commit":"out","changed_files":[None]}]},"invalid changed files"),
        ]
        for override,message in cases:
            payload=override if isinstance(override,list) else {**self.base,**override}
            with self.subTest(override=override):
                self.store._rpc=MagicMock(return_value=payload)
                with self.assertRaisesRegex(RuntimeError,message):
                    self.store.claim_integration("worker")


if __name__=="__main__":
    unittest.main()
