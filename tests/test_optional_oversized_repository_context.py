import unittest
from unittest.mock import Mock

from ai_product_factory.change_set_worker import ChangeSetBuilderWorker


class OversizedOptionalContextTests(unittest.TestCase):
    def make_worker(self, files):
        worker = object.__new__(ChangeSetBuilderWorker)
        github = Mock()
        github.get_file_text.side_effect = lambda path, ref: files[path]
        worker.github = github
        return worker

    def test_optional_oversized_provider_file_is_skipped(self):
        worker = self.make_worker({
            "AGENTS.md": "governance",
            "large.ts": ValueError("repository context file too large"),
            "small.ts": "export const ok = true;",
        })
        def read(path, ref):
            value = worker.github.get_file_text.side_effect.__closure__
            return None
        worker.github.get_file_text.side_effect = lambda path, ref: (
            (_ for _ in ()).throw(ValueError("repository context file too large"))
            if path == "large.ts" else
            ("governance" if path == "AGENTS.md" else "export const ok = true;")
        )
        worker._governance_paths = lambda paths: ("AGENTS.md",)
        snapshot, unsafe = worker._repository_snapshot_with_safety(
            source={"assignment": {"context_paths": ["AGENTS.md", "large.ts", "small.ts"], "scope_keys": []}},
            base_commit="a" * 40,
        )
        self.assertEqual(snapshot["AGENTS.md"], "governance")
        self.assertEqual(snapshot["small.ts"], "export const ok = true;")
        self.assertNotIn("large.ts", snapshot)
        self.assertIn("large.ts", unsafe)
        with self.assertRaises(PermissionError):
            worker._assert_snapshot_edit_safety({"large.ts": "rewrite"}, unsafe)

    def test_required_oversized_file_remains_blocked(self):
        worker = self.make_worker({})
        worker.github.get_file_text.side_effect = ValueError("repository context file too large")
        worker._governance_paths = lambda paths: ("AGENTS.md",)
        with self.assertRaisesRegex(ValueError, "repository context file too large"):
            worker._repository_snapshot_with_safety(
                source={"assignment": {"context_paths": ["AGENTS.md"], "scope_keys": []}},
                base_commit="a" * 40,
            )

    def test_other_optional_read_errors_remain_blocked(self):
        worker = self.make_worker({})
        worker.github.get_file_text.side_effect = ValueError("invalid UTF-8")
        worker._governance_paths = lambda paths: ()
        with self.assertRaisesRegex(ValueError, "invalid UTF-8"):
            worker._repository_snapshot_with_safety(
                source={"assignment": {"context_paths": ["small.ts"], "scope_keys": []}},
                base_commit="a" * 40,
            )


if __name__ == "__main__":
    unittest.main()
