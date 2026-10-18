import unittest
from unittest.mock import MagicMock

from ai_product_factory.change_set_store import SupabaseChangeSetStore


class IntegrationClaimContractTests(unittest.TestCase):
    def setUp(self):
        self.store=SupabaseChangeSetStore(url="https://example.supabase.co",service_role_key="secret")
        self.base={
            "change_set_id":"11111111-1111-4111-8111-111111111111","project_id":"22222222-2222-4222-8222-222222222222","execution_generation":3,"lease_owner":"worker","project_key":"demo","repository":"owner/repo",
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

    def test_worker_identity_rejects_three_unsafe_forms(self):
        for worker in ("x"*129, " worker", "worker\n"):
            with self.subTest(worker=repr(worker)):
                self.store._rpc=MagicMock()
                with self.assertRaisesRegex(ValueError,"worker ID"):
                    self.store.claim_integration(worker)
                self.store._rpc.assert_not_called()

    def test_six_unsafe_path_classes_are_rejected(self):
        unit=self.base["work_units"][0]
        cases=[
            ("src/"+"a"*1021,"length limit"),
            ("src/a\nb.py","control character"),
            ("src/"+"a"*256,"segment exceeds limit"),
            ("src/.git/config","git internals"),
            ("src/a.py ","unsafe path suffix"),
            ("src/a. /file","unsafe path suffix"),
        ]
        for path,message in cases:
            with self.subTest(message=message):
                payload={**self.base,"work_units":[{**unit,"changed_files":[path]}]}
                self.store._rpc=MagicMock(return_value=payload)
                with self.assertRaisesRegex(RuntimeError,message):
                    self.store.claim_integration("worker")

    def test_ten_more_path_ambiguity_classes(self):
        unit=self.base["work_units"][0]
        cases=[
            ("src/.gitignore","protected git metadata"),
            ("src/name:stream","colon"),
            ("src/file?.py","wildcard"),
            ("src/file*.py","wildcard"),
            ("src/a|b.py","forbidden character"),
            ("src/CON.txt","reserved device name"),
            ("src/~config","home alias"),
            ("src/-rf","option-like segment"),
            ("src/cache.lock","lock file"),
            ("src/.private/key","hidden segment"),
        ]
        for path,message in cases:
            with self.subTest(path=path):
                self.store._rpc=MagicMock(return_value={
                    **self.base,"work_units":[{**unit,"changed_files":[path]}],
                })
                with self.assertRaisesRegex(RuntimeError,message):
                    self.store.claim_integration("worker")

    def test_epoch_checkpoint_rejects_boolean_generation(self):
        from dataclasses import replace
        self.store._rpc=MagicMock(return_value=self.base)
        item=self.store.claim_integration("worker")
        self.store._rpc.reset_mock()
        with self.assertRaises(PermissionError):
            self.store.assert_integration_epoch(replace(item,execution_generation=True),"worker")
        self.store._rpc.assert_not_called()

    def test_empty_queue_is_not_an_error(self):
        self.store._rpc=MagicMock(return_value=None)
        self.assertIsNone(self.store.claim_integration("worker"))

    def test_valid_claim_preserves_exact_work_units(self):
        self.store._rpc=MagicMock(return_value=self.base)
        item=self.store.claim_integration("worker")
        self.assertEqual(item.current_wave,1)
        self.assertEqual(item.execution_generation,3)
        self.assertEqual(item.lease_owner,"worker")
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


    def test_ten_integration_safety_invariants(self):
        unit={"plan_task_key":"a","base_commit":"candidate","output_commit":"out","changed_files":["src/a.py"]}
        cases=[
            ({"repository":"invalid"},"invalid repository"),
            ({"integration_branch":"main"},"unsafe branch"),
            ({"integration_branch":"refs/heads/main"},"unsafe branch"),
            ({"work_units":[unit]*101},"work unit limit"),
            ({"work_units":[unit,dict(unit,changed_files=["src/b.py"])]},"repeats plan task"),
            ({"work_units":[dict(unit,output_commit="candidate")]},"unchanged output"),
            ({"work_units":[dict(unit,changed_files=[f"src/{n}.py" for n in range(201)])]},"changed file limit"),
            ({"work_units":[dict(unit,changed_files=["../secret"])]},"unsafe path"),
            ({"work_units":[dict(unit,changed_files=["/etc/passwd"])]},"unsafe path"),
            ({"work_units":[dict(unit,changed_files=["src\\\\unsafe.py"])]},"unsafe path"),
            ({"work_units":[unit,dict(unit,plan_task_key="b")]},"conflicting file owners"),
        ]
        for override,message in cases:
            with self.subTest(message=message,override=str(override)[:100]):
                self.store._rpc=MagicMock(return_value={**self.base,**override})
                with self.assertRaisesRegex(RuntimeError,message):
                    self.store.claim_integration("worker")

    def test_epoch_claim_contract_rejects_stale_or_missing_capability(self):
        cases=[
            ({"project_id":None},"UUID capability"),
            ({"execution_generation":None},"execution generation"),
            ({"execution_generation":False},"execution generation"),
            ({"execution_generation":0},"execution generation"),
            ({"lease_owner":"stale-worker"},"lease owner mismatch"),
        ]
        for override,message in cases:
            with self.subTest(override=override):
                self.store._rpc=MagicMock(return_value={**self.base,**override})
                with self.assertRaisesRegex(RuntimeError,message):
                    self.store.claim_integration("worker")

    def test_integration_epoch_rpc_is_bound_to_claim_identity(self):
        self.store._rpc=MagicMock(return_value=self.base)
        item=self.store.claim_integration("worker")
        self.store.assert_integration_epoch(item,"worker")
        self.store._rpc.assert_called_with("factory_assert_change_set_integration_epoch",{
            "p_change_set_id":"11111111-1111-4111-8111-111111111111","p_project_id":"22222222-2222-4222-8222-222222222222","p_generation":3,
            "p_worker_id":"worker","p_wave":1,
        })
        with self.assertRaises(PermissionError):
            self.store.assert_integration_epoch(item,"stale-worker")

if __name__=="__main__":
    unittest.main()
