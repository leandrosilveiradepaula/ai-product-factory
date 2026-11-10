"""Independent negative contracts for the read-only role probes and secret scanner."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SQL = ROOT / "scripts/audit_block1_rls_role_probes.sql"
WORKFLOW = ROOT / ".github/workflows/block1-independent-secrets.yml"


class Block1IndependentSecurityEvidenceTests(unittest.TestCase):
    def test_rls_probes_are_transactional_read_only(self):
        sql = SQL.read_text(encoding="utf-8")
        source = re.sub(r"--[^\n]*", "", sql)
        self.assertEqual(source.count("BEGIN TRANSACTION READ ONLY;"), 4)
        self.assertEqual(source.count("ROLLBACK;"), 4)
        self.assertEqual(source.count("SET LOCAL ROLE authenticated;"), 3)
        for marker in ("anon_table_grant_denied", "missing_subject_denied",
                       "unauthorized_subject_denied", "active_operator_self_only"):
            self.assertIn(marker, source)
        self.assertIn("auth.uid()", source)
        self.assertIn("NOT has_table_privilege", source)
        self.assertIn("count(*) = 1", source)
        self.assertIn("count(*) = 0", source)
        self.assertNotIn("SET ROLE service_role", source)
        scrubbed = re.sub(r"\x27(?:\x27\x27|[^\x27])*\x27", "\x27\x27", source)
        for statement in ("GRANT", "REVOKE", "INSERT", "UPDATE", "DELETE",
                          "TRUNCATE", "ALTER", "DROP", "CREATE", "COMMIT"):
            with self.subTest(statement=statement):
                self.assertNotRegex(scrubbed, rf"(?i)\b{statement}\b")

    def test_scanner_is_independent_pinned_nonprivileged_and_repeatable(self):
        yaml = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("pull_request:", yaml)
        self.assertIn("workflow_dispatch:", yaml)
        self.assertIn("contents: read", yaml)
        self.assertIn("fetch-depth: 0", yaml)
        self.assertIn("persist-credentials: false", yaml)
        self.assertIn("9991e0b2903da4c8f6122b5c3186448b927a5da4deef1fe45271c3793f4ee29c", yaml)
        self.assertIn("sha256sum --check --status", yaml)
        self.assertIn("Scan PR/history with independent Gitleaks engine", yaml)
        self.assertIn("git merge-base --is-ancestor", yaml)
        self.assertIn("--log-opts=", yaml)
        self.assertNotIn("gitleaks/gitleaks-action@", yaml)
        actions = re.findall(r"uses:\s*([^\s#]+)", yaml)
        self.assertEqual(len(actions), 2)
        self.assertEqual(sum(a.startswith('actions/checkout@') for a in actions), 1)
        self.assertEqual(sum(a.startswith('gitleaks/gitleaks-action@') for a in actions), 0)
        self.assertEqual(sum(a.startswith('actions/upload-artifact@') for a in actions), 1)
        self.assertIn('block1-full-tree-gitleaks', yaml)
        self.assertIn('scripts/audit_block1_complete_tree.py', yaml)
        for action in actions:
            self.assertRegex(action, r"^[\w-]+/[\w-]+@[0-9a-f]{40}$")
        for forbidden in ("pull_request_target:", "contents: write", "actions: write",
                          "secrets.", "GITLEAKS_LICENSE:", "npm install", "merge --"):
            self.assertNotIn(forbidden, yaml)


if __name__ == "__main__":
    unittest.main()
