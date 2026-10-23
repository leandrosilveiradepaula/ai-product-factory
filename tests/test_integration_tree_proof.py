"""Fail-closed recovery proof of a Factory integration commit's entire tree.

The simulated GitHub API is read-only. A commit with correct parent, message
and authorized contents but one extra changed file is *not* a repair receipt.
"""
import unittest
from unittest.mock import MagicMock

from ai_product_factory.github_rest import GitHubRestAdapter

PARENT = "b" * 40
CANDIDATE = "c" * 40
TREE_PARENT = "d" * 40
TREE_CANDIDATE = "e" * 40

def entry(path, sha, mode="100644", kind="blob"):
    return {"path": path, "sha": sha, "mode": mode, "type": kind}

def make_adapter(parent_entries, candidate_entries, *, truncated=False):
    adapter = object.__new__(GitHubRestAdapter)
    adapter.repository = "owner/repo"
    responses = {
        f"/repos/owner/repo/git/commits/{PARENT}": {"tree": {"sha": TREE_PARENT}},
        f"/repos/owner/repo/git/commits/{CANDIDATE}": {"tree": {"sha": TREE_CANDIDATE}},
        f"/repos/owner/repo/git/trees/{TREE_PARENT}": {
            "truncated": False, "tree": parent_entries,
        },
        f"/repos/owner/repo/git/trees/{TREE_CANDIDATE}": {
            "truncated": truncated, "tree": candidate_entries,
        },
    }
    adapter._call = MagicMock(side_effect=lambda method, path, **kwargs: responses[path])
    return adapter


class IntegrationTreeProofTests(unittest.TestCase):
    def test_exact_single_authorized_file_and_unchanged_neighbors_are_accepted(self):
        parent = [entry("src/a.py", "1" * 40), entry("docs/keep.md", "2" * 40)]
        candidate = [entry("src/a.py", "3" * 40), entry("docs/keep.md", "2" * 40)]
        adapter = make_adapter(parent, candidate)
        adapter.verify_integration_commit_tree(
            parent_sha=PARENT, candidate_sha=CANDIDATE, expected_paths=("src/a.py",),
        )
        self.assertEqual(adapter._call.call_count, 4)

    def test_unexpected_extra_file_blocks_even_with_correct_authorized_contents(self):
        parent = [entry("src/a.py", "1" * 40)]
        candidate = [entry("src/a.py", "3" * 40), entry("src/unapproved.py", "4" * 40)]
        adapter = make_adapter(parent, candidate)
        with self.assertRaisesRegex(RuntimeError, "extra or no file changes"):
            adapter.verify_integration_commit_tree(
                parent_sha=PARENT, candidate_sha=CANDIDATE, expected_paths=("src/a.py",),
            )

    def test_unapproved_deletion_and_mode_change_are_rejected(self):
        parent = [entry("src/a.py", "1" * 40), entry("docs/keep.md", "2" * 40)]
        candidate = [entry("src/a.py", "3" * 40)]
        with self.assertRaisesRegex(RuntimeError, "extra or no file changes"):
            make_adapter(parent, candidate).verify_integration_commit_tree(
                parent_sha=PARENT, candidate_sha=CANDIDATE, expected_paths=("src/a.py",),
            )
        changed_mode = [entry("src/a.py", "3" * 40, mode="100755"), entry("docs/keep.md", "2" * 40)]
        with self.assertRaisesRegex(RuntimeError, "file type or mode"):
            make_adapter(parent, changed_mode).verify_integration_commit_tree(
                parent_sha=PARENT, candidate_sha=CANDIDATE, expected_paths=("src/a.py",),
            )

    def test_missing_or_truncated_tree_never_passes(self):
        adapter = make_adapter([entry("src/a.py", "1" * 40)], [entry("src/a.py", "3" * 40)], truncated=True)
        with self.assertRaisesRegex(RuntimeError, "incomplete or unbounded"):
            adapter.verify_integration_commit_tree(
                parent_sha=PARENT, candidate_sha=CANDIDATE, expected_paths=("src/a.py",),
            )

    def test_message_only_commit_without_file_change_cannot_be_adopted(self):
        same = [entry("src/a.py", "1" * 40)]
        with self.assertRaisesRegex(RuntimeError, "extra or no file changes"):
            make_adapter(same, same).verify_integration_commit_tree(
                parent_sha=PARENT, candidate_sha=CANDIDATE, expected_paths=("src/a.py",),
            )

    def test_duplicate_path_or_non_regular_expected_file_never_passes(self):
        parent = [entry("src/a.py", "1" * 40)]
        duplicate = [entry("src/a.py", "3" * 40), entry("src/a.py", "4" * 40)]
        with self.assertRaisesRegex(RuntimeError, "duplicate path"):
            make_adapter(parent, duplicate).verify_integration_commit_tree(
                parent_sha=PARENT, candidate_sha=CANDIDATE, expected_paths=("src/a.py",),
            )
        symlink = [entry("src/a.py", "3" * 40, mode="120000")]
        with self.assertRaisesRegex(RuntimeError, "file type or mode"):
            make_adapter(parent, symlink).verify_integration_commit_tree(
                parent_sha=PARENT, candidate_sha=CANDIDATE, expected_paths=("src/a.py",),
            )

if __name__ == "__main__":
    unittest.main()
