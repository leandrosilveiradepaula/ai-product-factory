"""Adversarial and positive coverage of complete candidate tree secret scanning."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

P = Path(__file__).resolve().parents[1] / "scripts/audit_block1_complete_tree.py"
spec = importlib.util.spec_from_file_location("block1_complete_tree", P)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def git(root: Path, *args: str) -> None:
    command = subprocess.run(["git", "-C", str(root), *args],
                             capture_output=True, text=True, check=False,
                             timeout=10)
    if command.returncode != 0:
        raise RuntimeError("cannot create local git test fixture")


class CompleteTrackedTreeScanTests(unittest.TestCase):
    def test_isolated_local_checkout_is_scanned_and_receipt_stays_scoped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "checkout"
            root.mkdir()
            git(root, "init", "-q")
            git(root, "config", "user.name", "CI Fixture")
            git(root, "config", "user.email", "ci@example.invalid")
            (root / "regular.txt").write_text("safe source\n", encoding="utf-8")
            git(root, "add", "regular.txt")
            git(root, "commit", "-q", "-m", "init")
            scanner = Path(tmp) / "scanner"
            scanner.write_text(
                "#!" + sys.executable + "\n"
                "import json, pathlib, sys\n"
                "if '--version' in sys.argv:\n"
                "  print('gitleaks version 8.24.3')\n"
                "else:\n"
                "  pathlib.Path(sys.argv[sys.argv.index('--report-path') + 1]).write_text('[]')\n",
                encoding="utf-8",
            )
            scanner.chmod(scanner.stat().st_mode | stat.S_IXUSR)
            with patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}):
                report = mod.audit(root, scanner)
            self.assertTrue(report["scan_passed"])
            self.assertEqual(report["tracked_files_scanned"], 1)
            self.assertEqual(report["scanner_version"], "8.24.3")
            self.assertFalse(report["all_history_scanned"])
            self.assertFalse(report["secrets_dependencies_certified"])
            self.assertFalse(report["block1_certified"])
            self.assertEqual(report["production_writes"], 0)

    def test_archive_denies_traversal_duplicate_and_symlink(self):
        import io
        import tarfile

        def archive(entries):
            stream = io.BytesIO()
            with tarfile.open(fileobj=stream, mode="w") as tar:
                for name, kind in entries:
                    data = b"x"
                    info = tarfile.TarInfo(name)
                    info.type = tarfile.SYMTYPE if kind == "symlink" else tarfile.REGTYPE
                    info.size = 0 if kind == "symlink" else len(data)
                    tar.addfile(info, io.BytesIO(data) if kind != "symlink" else None)
            return stream.getvalue()

        for items in (
            [("../escape", "file")],
            [("/tmp/leak", "file")],
            [("safe", "file"), ("safe", "file")],
            [("linked", "symlink")],
            [(".git/config", "file")],
        ):
            with self.subTest(items=items), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "archive.tar"
                path.write_bytes(archive(items))
                with self.assertRaises(mod.ScanBlocked):
                    mod._extract_committed_tree(path, Path(tmp) / "target")

    def test_invalid_scanner_and_uncontrolled_root_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scanner").write_text("not an executable", encoding="utf-8")
            with self.assertRaises(mod.ScanBlocked):
                mod.audit(root, root / "scanner")

    def test_reviewed_fixtures_require_exact_source_blob_rule_and_line(self):
        from unittest.mock import patch
        expected = sorted(mod.REVIEWED_FIXTURE_FINDINGS)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            findings = []
            hashes = {}
            for rel, line, rule, oid in expected:
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("reviewed synthetic fixture", encoding="utf-8")
                hashes[str(path.resolve())] = "".join(oid)
                findings.append({"File": str(path), "StartLine": line, "RuleID": "-".join(rule)})
            with patch.object(mod, "_git_blob_oid", side_effect=lambda p: hashes[str(p.resolve())]):
                result = mod._classify_reviewed_fixtures(findings, root)
                self.assertEqual(len(result), 8)
                for mutation in ("extra", "removed", "wrong_line", "wrong_rule"):
                    altered = [dict(x) for x in findings]
                    if mutation == "extra":
                        altered.append(dict(altered[0]))
                    elif mutation == "removed":
                        altered.pop()
                    elif mutation == "wrong_line":
                        altered[0]["StartLine"] += 1
                    else:
                        altered[0]["RuleID"] = "other-rule"
                    with self.subTest(mutation=mutation), self.assertRaises(mod.ScanBlocked):
                        mod._classify_reviewed_fixtures(altered, root)
            with patch.object(mod, "_git_blob_oid", return_value="0" * 40):
                with self.assertRaisesRegex(mod.ScanBlocked, "blob_drift"):
                    mod._classify_reviewed_fixtures(findings, root)

    def test_scanner_argv_enforces_ignore_override_and_redaction(self):
        script = P.read_text(encoding="utf-8")
        for required in (
            '"--gitleaks-ignore-path"', '"--ignore-gitleaks-allow"',
            '"--redact"', '"--config"', '"--report-format"',
            '"--exit-code"', "complete_committed_tree_not_all_historical_git_commits",
        ):
            with self.subTest(required=required):
                self.assertIn(required, script)


if __name__ == "__main__":
    unittest.main()
