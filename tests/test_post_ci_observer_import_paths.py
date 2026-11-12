"""Regression for #1371: post-CI observers must import repo-root scripts.

The workflow runs "python scripts/build_readiness_evidence_manifest.py" where
sys.path[0] is scripts/. Restricting PYTHONPATH to src makes the package import
"from scripts.audit_block1_real_journeys_readonly" fail before certification.
This test executes the exact CLI bootstrap (only --help, no credentials/writes).
"""
from __future__ import annotations

import os
import re
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "autonomous-runner.yml"


class PostCiObserverImports(unittest.TestCase):
    def test_both_protected_observers_include_repo_root_in_pythonpath(self):
        content = WORKFLOW.read_text(encoding="utf-8")
        for job in ("product-readiness-certification-post-ci", "global-readiness-post-ci"):
            with self.subTest(job=job):
                start = content.index("\n  " + job + ":")
                # Stop at the next two-space YAML job declaration; do not
                # accidentally match a sibling job's environment.
                next_job = re.search(r"(?m)^  [a-z][a-z0-9-]+:$", content[start + 1:])
                end = start + 1 + next_job.start() if next_job else len(content)
                config = content[start:end]
                self.assertIn("PYTHONPATH: src:.", config)
                self.assertIn("actions/checkout@", config)
                self.assertIn("python scripts/build_readiness_evidence_manifest.py", config)

    def test_both_certifier_entrypoints_import_in_post_ci_environment(self):
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(("src", "."))
        env.pop("GITHUB_TOKEN", None)
        env.pop("SUPABASE_SECRET_KEY", None)
        env.pop("SUPABASE_SERVICE_ROLE_KEY", None)
        for script in ("build_readiness_evidence_manifest.py", "certify_product_readiness.py"):
            with self.subTest(script=script):
                result = subprocess.run(
                    [sys.executable, str(ROOT / "scripts" / script), "--help"],
                    cwd=ROOT,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                self.assertEqual(result.returncode, 0,
                    f"{script} import failed: {(result.stderr or '')[:1200]}")
                self.assertIn("usage:", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
