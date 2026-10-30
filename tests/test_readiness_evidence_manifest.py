"""Trusted independent evidence baseline contracts, with no paid/external writes."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_readiness_evidence_manifest import build_verified_baseline
from tests.test_product_readiness_certification import SHA, REPO, github


class VerifiedBaselineTests(unittest.TestCase):
    def collect(self, data=None):
        fixtures = data if data is not None else github()
        return build_verified_baseline(
            repository=REPO, sha=SHA, github_get=lambda path: fixtures[path]
        )

    def test_all_19_present_only_executed_unit_ci_positive(self):
        report = self.collect()
        self.assertEqual(len(report["criteria"]), 19)
        self.assertFalse(report["product_ready"])
        self.assertFalse(report["assessment"]["ready"])
        passed = [x for x in report["criteria"] if x["status"] == "passed"]
        self.assertEqual([(x["domain"], x["criterion"]) for x in passed],
                         [("test_strategy", "unit_integration")])
        self.assertEqual(len(report["assessment"]["blockers"]), 18)
        self.assertEqual(report["writes"], 0)
        self.assertEqual(report["paid_calls"], 0)
        self.assertFalse(report["start_authorized"])
        self.assertEqual(report["source_snapshot"]["validation_run_id"], 7)
        self.assertNotIn("Authorization", json.dumps(report))
        self.assertNotIn("service_role", json.dumps(report))

    def test_credentialless_baseline_does_not_infer_domain_certification(self):
        report = self.collect()
        for row in report["criteria"]:
            if row["status"] == "passed":
                continue
            self.assertIn(row["status"], {"partial", "missing"})
        self.assertEqual(report["manifest"]["criteria"]["test_strategy"]["regression_gates"]["status"],
                         "partial")
        for domain in ("security","observability_operations",
                       "product_experience","documentation","functional_completeness"):
            self.assertFalse(any(
                x["status"] == "passed" and x["domain"] == domain
                for x in report["criteria"]
            ))
        self.assertEqual(report, self.collect())

    def test_wrong_sha_or_ci_fails_before_any_manifest(self):
        data = github()
        data["/repos/" + REPO + "/git/ref/heads/main"]["object"]["sha"] = "b"*40
        with self.assertRaisesRegex(RuntimeError, "HEAD changed"):
            self.collect(data)
        data = github()
        data["/repos/" + REPO + "/actions/runs/7/jobs?per_page=100"]["jobs"][0]["status"] = "queued"
        with self.assertRaisesRegex(RuntimeError, "job is not executed"):
            self.collect(data)

    def test_observer_identity_remains_read_only_and_preserves_both_receipts(self):
        yaml = (ROOT / ".github/workflows/autonomous-runner.yml").read_text()
        job = yaml.split("\n  global-readiness-post-ci:", 1)[1].split("\n  owner-start:", 1)[0]
        self.assertIn("Collect verified criterion evidence (read-only, no model)", job)
        self.assertIn("scripts/build_readiness_evidence_manifest.py", job)
        self.assertIn("factory-global-product-readiness.json", job)
        self.assertIn("factory-verified-readiness-baseline.json", job)
        self.assertIn("      actions: read", job)
        self.assertNotIn("      actions: write", job)
        self.assertIn("persist-credentials: false", job)
        script = (ROOT / "scripts/build_readiness_evidence_manifest.py").read_text()
        self.assertNotIn("SupabaseDeliveryStore", script)
        self.assertNotIn("SUPABASE_SECRET", script)
        self.assertNotIn("model_client", script)


if __name__ == "__main__":
    unittest.main()
