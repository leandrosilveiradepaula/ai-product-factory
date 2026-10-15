from __future__ import annotations

import contextlib
from io import StringIO
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from ai_product_factory.existing_project_inventory import (
    BaselineInventoryError, main, scan_existing_checkout,
)
from ai_product_factory.release_intelligence import _verified_existing_baseline


def git(path: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(path), *args], stderr=subprocess.DEVNULL
    ).decode().strip()


class ExistingProjectInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        git(self.root, "init", "-q")
        entries = {
            "src/app/page.tsx": "export default function Home(){return null}\n",
            "src/app/api/health/route.ts": "export const GET = () => null;\n",
            "tests/test_tenant.py": "def test_tenant(): assert True\n",
            "supabase/migrations/20261001_safe.sql": "select 1;\n",
            ".github/workflows/ci.yml": "name: CI\n",
            "docs/OPERATIONS.md": "Known inherited debt is not certified resolved.\n",
            "secret/example.env": "PRIVATE_TEST_SENTINEL=do-not-print\n",
        }
        for filename, content in entries.items():
            target = self.root / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        git(self.root, "add", ".")
        git(self.root, "-c", "user.name=Test", "-c", "user.email=test@example.com",
            "commit", "-qm", "fixture")
        self.sha = git(self.root, "rev-parse", "HEAD")

    def audit(self):
        return scan_existing_checkout(
            root=self.root, candidate_sha=self.sha, repository="example/crm"
        )

    def test_pinned_committed_inventory_is_counts_only_and_fails_closed(self):
        result = self.audit()
        self.assertEqual(result["assessed_commit"], self.sha)
        self.assertEqual(result["inventory"]["tracked_files"], 7)
        self.assertEqual(result["inventory"]["source_files"], 2)
        self.assertEqual(result["inventory"]["test_files"], 1)
        self.assertEqual(result["inventory"]["migration_files"], 1)
        self.assertEqual(result["inventory"]["workflow_files"], 1)
        self.assertEqual(result["inventory"]["route_files"], 2)
        self.assertTrue(result["inventory"]["debt_documentation_present"])
        self.assertEqual(result["coverage"], ["repository_inventory"])
        self.assertEqual(result["verification_state"], "inventory_only")
        self.assertEqual(result["status"], "not_assessed")
        self.assertFalse(result["remote_identity_verified"])
        self.assertFalse(result["production_schema_verified"])
        self.assertFalse(result["authenticated_journeys_verified"])
        self.assertNotIn("PRIVATE_TEST_SENTINEL", json.dumps(result))
        self.assertNotIn("secret/example.env", json.dumps(result))

    def test_inventory_cannot_be_forged_into_a_passing_existing_baseline(self):
        result = self.audit()
        ok, reason = _verified_existing_baseline(
            {"evaluation_status": "passed", "baseline_ref": self.sha, "result": result},
            self.sha,
        )
        self.assertFalse(ok)
        self.assertTrue(reason.startswith("existing_project_baseline:"))

    def test_cli_is_deterministic_and_non_passing(self):
        outputs = []
        for _ in range(2):
            stream = StringIO()
            with contextlib.redirect_stdout(stream):
                code = main(["--repo-path", str(self.root), "--candidate-sha", self.sha,
                             "--repository", "example/crm"])
            self.assertEqual(code, 0)
            outputs.append(stream.getvalue())
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(json.loads(outputs[0])["status"], "not_assessed")

    def test_wrong_sha_and_bad_repository_fail_closed(self):
        for sha, repository in (("b" * 40, "example/crm"), (self.sha, "../evil"),
                                 (self.sha[:-1], "example/crm")):
            with self.subTest(sha=sha, repository=repository):
                with self.assertRaises(BaselineInventoryError):
                    scan_existing_checkout(root=self.root, candidate_sha=sha,
                                           repository=repository)

    def test_subdirectory_is_not_accepted_as_independent_repo(self):
        with self.assertRaisesRegex(BaselineInventoryError, "repository root"):
            scan_existing_checkout(root=self.root / "src", candidate_sha=self.sha,
                                   repository="example/crm")

    def test_uncommitted_files_never_substitute_for_pinned_tree(self):
        (self.root / "tests" / "untracked.test.ts").write_text("test()\n")
        (self.root / "src" / "app" / "page.tsx").write_text("MODIFIED\n")
        self.assertEqual(self.audit()["inventory"]["test_files"], 1)
        self.assertFalse(self.audit()["working_tree_contents_inspected"])


if __name__ == "__main__":
    unittest.main()
