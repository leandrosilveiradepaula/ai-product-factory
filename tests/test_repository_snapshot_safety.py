"""Safe, bounded repository context for the actual Change Set builder."""
from __future__ import annotations

import hashlib
import unittest

from ai_product_factory.change_set_worker import ChangeSetBuilderWorker


class _GitHub:
    def __init__(self, files: dict[str, str]):
        self.files = files
        self.calls: list[tuple[str, str]] = []

    def get_file_text(self, path: str, *, ref: str) -> str:
        self.calls.append((path, ref))
        return self.files[path]


def _worker(files: dict[str, str]) -> ChangeSetBuilderWorker:
    worker = object.__new__(ChangeSetBuilderWorker)
    worker.github = _GitHub(files)
    return worker


def _source(paths: list[str], scopes: list[str]) -> dict:
    return {"assignment": {"context_paths": paths, "scope_keys": scopes}}


class SnapshotSafetyTests(unittest.TestCase):
    SHA = "a" * 40

    def test_large_editable_source_is_complete_and_optional_is_bounded(self):
        files = {
            "AGENTS.md": "Read and obey governing instructions.",
            "src/SettingsService.ts": "export const long = " + ("x" * 80000),
            "docs/extra.md": "A" * 100000,
        }
        w = _worker(files)
        packet, unsafe = w._repository_snapshot_with_safety(
            source=_source(list(files), ["src/SettingsService.ts"]),
            base_commit=self.SHA,
        )
        self.assertEqual(packet["AGENTS.md"], files["AGENTS.md"])
        self.assertEqual(packet["src/SettingsService.ts"], files["src/SettingsService.ts"])
        self.assertIn("[CONTEXT_EXCERPT path=docs/extra.md", packet["docs/extra.md"])
        self.assertIn("INCOMPLETE READ-ONLY CONTEXT", packet["docs/extra.md"])
        self.assertIn("sha256=" + hashlib.sha256(files["docs/extra.md"].encode()).hexdigest(), packet["docs/extra.md"])
        self.assertNotIn("src/SettingsService.ts", unsafe)
        self.assertEqual(unsafe, frozenset({"docs/extra.md"}))
        self.assertLessEqual(sum(len(v.encode()) for v in packet.values()), 131072)
        self.assertEqual(w.github.calls, [(p, self.SHA) for p in files])

    def test_many_large_optional_files_are_adaptively_budgeted(self):
        paths = [f"docs/f{n}.md" for n in range(12)]
        files = {path: "Z" * 90000 for path in paths}
        w = _worker(files)
        a, unsafe = w._repository_snapshot_with_safety(
            source=_source(paths, ["src/**"]), base_commit=self.SHA,
        )
        b, again = w._repository_snapshot_with_safety(
            source=_source(paths, ["src/**"]), base_commit=self.SHA,
        )
        self.assertEqual(a, b)
        self.assertEqual(unsafe, again)
        self.assertEqual(set(a), set(paths))
        self.assertEqual(unsafe, frozenset(paths))
        self.assertLessEqual(sum(len(v.encode()) for v in a.values()), 131072)
        self.assertTrue(all("[CONTEXT_EXCERPT" in v for v in a.values()))

    def test_utf8_excerpts_remain_valid_with_global_budget(self):
        files = {"docs/utf8.md": "😀üç" * 15000, "src/target.py": "def code(): return True"}
        w = _worker(files)
        result, unsafe = w._repository_snapshot_with_safety(
            source=_source(list(files), ["src/target.py"]), base_commit=self.SHA,
        )
        self.assertEqual(result["src/target.py"], files["src/target.py"])
        self.assertIn("docs/utf8.md", unsafe)
        self.assertLessEqual(sum(len(v.encode("utf-8")) for v in result.values()), 131072)
        self.assertIn("CONTEXT_EXCERPT", result["docs/utf8.md"])

    def test_too_large_required_source_fails_instead_of_clipping(self):
        w = _worker({"src/target.py": "x" * 131073})
        with self.assertRaisesRegex(ValueError, "complete required repository context"):
            w._repository_snapshot_with_safety(
                source=_source(["src/target.py"], ["src/target.py"]), base_commit=self.SHA,
            )

    def test_governance_cannot_be_truncated(self):
        w = _worker({"AGENTS.md": "x" * 131073})
        with self.assertRaisesRegex(ValueError, "complete required repository context"):
            w._repository_snapshot_with_safety(
                source=_source(["AGENTS.md"], ["src/**"]), base_commit=self.SHA,
            )

    def test_sensitive_edit_target_fails_before_any_model_call(self):
        w = _worker({"src/target.py": "token = 'sk-proj-abcdefghijklmnopqrstuv123456'"})
        with self.assertRaisesRegex(PermissionError, "redacted secret"):
            w._repository_snapshot_with_safety(
                source=_source(["src/target.py"], ["src/target.py"]), base_commit=self.SHA,
            )

    def test_sensitive_optional_context_is_redacted_and_read_only(self):
        text = "Service endpoint = sk-proj-abcdefghijklmnopqrstuv123456"
        w = _worker({"docs/context.md": text})
        packet, unsafe = w._repository_snapshot_with_safety(
            source=_source(["docs/context.md"], ["src/**"]), base_commit=self.SHA,
        )
        self.assertIn("[REDACTED_SECRET]", packet["docs/context.md"])
        self.assertNotIn("sk-proj-", packet["docs/context.md"])
        self.assertEqual(unsafe, frozenset({"docs/context.md"}))

    def test_truncated_or_redacted_files_cannot_be_committed_even_with_broad_scope(self):
        safety = frozenset({"src/very-large.ts", "docs/redacted.md"})
        with self.assertRaisesRegex(PermissionError, "incomplete or redacted"):
            ChangeSetBuilderWorker._assert_snapshot_edit_safety(
                {"src/very-large.ts": "replace whole file"}, safety
            )
        with self.assertRaisesRegex(PermissionError, "docs/redacted.md"):
            ChangeSetBuilderWorker._assert_snapshot_edit_safety(
                {"docs/redacted.md": "overwrite"}, safety
            )
        ChangeSetBuilderWorker._assert_snapshot_edit_safety(
            {"src/fully-seen.ts": "safe file"}, safety
        )

    def test_no_optional_context_is_invented_after_budget_is_exhausted(self):
        w = _worker({"src/target.py": "t" * 131000, "docs/optional.md": "a" * 90000})
        result, unsafe = w._repository_snapshot_with_safety(
            source=_source(["docs/optional.md", "src/target.py"], ["src/target.py"]),
            base_commit=self.SHA,
        )
        self.assertEqual(result["src/target.py"], "t" * 131000)
        self.assertNotIn("docs/optional.md", result)
        self.assertIn("docs/optional.md", unsafe)

    def test_path_traversal_and_too_many_context_paths_rejected(self):
        w = _worker({})
        for path in ("../secret", "src/../secret", "/root/secret", "src//file.py", ".git/config"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                w._repository_snapshot_with_safety(
                    source=_source([path], ["src/**"]), base_commit=self.SHA,
                )
        with self.assertRaisesRegex(ValueError, "too many"):
            w._repository_snapshot_with_safety(
                source=_source([f"docs/{i}.md" for i in range(13)], ["src/**"]),
                base_commit=self.SHA,
            )


if __name__ == "__main__":
    unittest.main()
