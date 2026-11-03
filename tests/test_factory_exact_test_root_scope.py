"""Regression: exact OWNER-approved contract tests under existing test/ root."""
import unittest
from ai_product_factory.change_set_worker import ChangeSetBuilderWorker

class ExactTestRootScopeTests(unittest.TestCase):
    FILES = (
        "AGENTS.md", "docs/codex/CURRENT_TASK.md",
        "test/auth-tenant-boundary.test.ts",
        "test/server-admin-rbac.test.ts",
        "src/services/ContractService.ts",
        "src/app/(dashboard)/contracts/actions.ts",
    )

    def test_exact_test_root_file_allowed(self):
        self.assertEqual(
            ChangeSetBuilderWorker._bounded_file_scope("test/contract-access.test.ts", self.FILES),
            ("test/contract-access.test.ts", None),
        )
        self.assertIsNone(ChangeSetBuilderWorker._bounded_file_scope(
            "test/contract-access.test.ts", tuple(p for p in self.FILES if not p.startswith("test/"))
        ))

    def test_no_new_top_level_source_or_unpopulated_directory(self):
        for path in ("src/new-service.ts","app/unknown.ts","tests/contract-access.test.ts",
                     "test/nested/missing.test.ts", "test/../secrets.ts", "test/.env.ts",
                     "test/contract-access.sql", "test/**"):
            with self.subTest(path=path):
                self.assertIsNone(ChangeSetBuilderWorker._bounded_file_scope(path, self.FILES))

    def test_scope_is_exact_not_prefix(self):
        granted = ChangeSetBuilderWorker._bounded_file_scope("test/contract-access.test.ts", self.FILES)[0]
        self.assertNotEqual(granted, "test/**")
        self.assertNotEqual(granted, "tests/**")
        self.assertFalse("test/other-contract.test.ts" == granted)

if __name__ == "__main__":
    unittest.main()
