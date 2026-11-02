"""Fail-closed Change Set source binding regression tests (no remote calls)."""
import unittest
from unittest.mock import MagicMock

from ai_product_factory.change_set_store import SupabaseChangeSetStore

SHA = "b" * 40
OTHER = "a" * 40
BRANCH = "factory/journey-example"


class V2ChangeSetBranchBaseTests(unittest.TestCase):
    def make_store(self, base=SHA, source=SHA, branch=BRANCH):
        store = object.__new__(SupabaseChangeSetStore)
        store._rpc = MagicMock(return_value={
            "change_set_id": "cs",
            "work_unit_id": "wu",
            "base_commit": base,
            "source_commit": source,
            "integration_branch": branch,
            "wave": 1,
        })
        return store

    def bind(self, store):
        return store.bind_source(
            run_id="run", source_commit=SHA,
            integration_branch=BRANCH, work_branch="factory/cs-example/one",
        )

    def test_verified_base_and_source_pass_through_without_coercion(self):
        store = self.make_store()
        result = self.bind(store)
        self.assertEqual(result.base_commit, SHA)
        self.assertEqual(result.source_commit, SHA)
        self.assertEqual(result.integration_branch, BRANCH)

    def test_null_base_never_becomes_literal_none_in_github_ref(self):
        for value in (None, "", "None", OTHER[:12], OTHER.upper(), 0, {}, []):
            store = self.make_store(base=value)
            with self.subTest(value=value), self.assertRaisesRegex(
                PermissionError, "verified exact base_commit"
            ):
                self.bind(store)

    def test_source_or_integration_branch_mismatch_blocks(self):
        for case in ({"source": OTHER}, {"branch": "factory/other"}):
            store = self.make_store(**case)
            with self.subTest(case=case), self.assertRaises(PermissionError):
                self.bind(store)


if __name__ == "__main__":
    unittest.main()
