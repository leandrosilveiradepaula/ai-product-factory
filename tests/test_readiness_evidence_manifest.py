"""Trusted independent evidence baseline contracts, with no paid/external writes."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

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
        self.assertEqual(sum("/" in x for x in report["assessment"]["blockers"]),18)
        self.assertEqual(len(report["assessment"]["blockers"]),24)
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

    def test_authenticated_console_receipt_is_partial_and_never_a_product_pass(self):
        from ai_product_factory.independent_authenticated_console_evidence import AuthenticatedConsoleEvidence
        proof = AuthenticatedConsoleEvidence(
            repository=REPO, assessed_commit=SHA, workflow_run_id=42, artifact_id=9,
        )
        with patch("build_readiness_evidence_manifest.verify_authenticated_console_evidence",
                   return_value=proof):
            report = build_verified_baseline(
                repository=REPO, sha=SHA, github_get=lambda path: github()[path],
                authenticated_console_run_id=42,
            )
        self.assertFalse(report["product_ready"])
        self.assertEqual(report["authenticated_console_evidence"], proof.receipt())
        rows = report["manifest"]["criteria"]["product_experience"]
        for criterion in ("surface_inventory", "responsive", "accessibility"):
            self.assertEqual(rows[criterion]["status"], "partial")
            self.assertEqual(rows[criterion]["evidence"], list(proof.evidence))
        self.assertEqual(rows["states"]["status"], "missing")
        self.assertEqual(report["manifest"]["criteria"]["security"]["authn_authz"]["status"], "missing")
        self.assertEqual(report["manifest"]["criteria"]["test_strategy"]["critical_e2e"]["status"], "missing")

    def test_historical_capture_blocker_is_visible_without_ux_promotion(self):
        from ai_product_factory.independent_authenticated_console_evidence import (
            AuthenticatedConsoleEvidenceBlocked,
        )
        with patch("build_readiness_evidence_manifest.verify_reusable_historical_authenticated_console_evidence",
                   side_effect=AuthenticatedConsoleEvidenceBlocked("historical artifact provenance mismatch")):
            report = build_verified_baseline(
                repository=REPO, sha=SHA, github_get=lambda path: github()[path],
                reuse_historical_authenticated_console_evidence=True,
                control_plane_get=lambda path: [],
            )
        self.assertNotIn("authenticated_console_evidence", report)
        for criterion in ("surface_inventory", "responsive", "accessibility"):
            item = report["manifest"]["criteria"]["product_experience"][criterion]
            self.assertEqual(item["status"], "missing")
            self.assertIn("historical artifact provenance mismatch", item["reason"])
        self.assertFalse(report["product_ready"])

    def test_historical_capture_provider_errors_are_sanitized(self):
        with patch("build_readiness_evidence_manifest.verify_reusable_historical_authenticated_console_evidence",
                   side_effect=OSError("secret=DO_NOT_LEAK")):
            report = build_verified_baseline(
                repository=REPO, sha=SHA, github_get=lambda path: github()[path],
                reuse_historical_authenticated_console_evidence=True,
                control_plane_get=lambda path: [],
            )
        self.assertNotIn("DO_NOT_LEAK", json.dumps(report))
        self.assertEqual(
            report["manifest"]["criteria"]["product_experience"]["responsive"]["reason"],
            "authenticated Console evidence source unavailable",
        )

    def test_regression_gate_blockers_are_actionable_but_never_promoted(self):
        from ai_product_factory.independent_regression_evidence import RegressionEvidenceBlocked
        with patch("build_readiness_evidence_manifest.verify_effective_regression_gates",
                   side_effect=RegressionEvidenceBlocked("regression_postgres_matching_tree_missing")):
            result = build_verified_baseline(
                repository=REPO, sha=SHA, github_get=lambda path: github()[path],
                verify_regression_gates=True,
            )
        entry = result["manifest"]["criteria"]["test_strategy"]["regression_gates"]
        self.assertEqual(entry["status"], "partial")
        self.assertIn("regression_postgres_matching_tree_missing", entry["reason"])
        self.assertFalse(result["product_ready"])

    def test_regression_gate_provider_errors_are_sanitized(self):
        with patch("build_readiness_evidence_manifest.verify_effective_regression_gates",
                   side_effect=OSError("secret=DO_NOT_LEAK")):
            result = build_verified_baseline(
                repository=REPO, sha=SHA, github_get=lambda path: github()[path],
                verify_regression_gates=True,
            )
        self.assertNotIn("DO_NOT_LEAK", json.dumps(result))
        entry = result["manifest"]["criteria"]["test_strategy"]["regression_gates"]
        self.assertEqual(entry["status"], "partial")
        self.assertIn("regression_evidence_source_unavailable", entry["reason"])

    def test_health_blocker_is_durable_without_false_positive(self):
        from ai_product_factory.independent_health_evidence import HealthEvidenceBlocked
        with patch("build_readiness_evidence_manifest.verify_health_for_certification",
                   side_effect=HealthEvidenceBlocked("health_scheduler_cadence_invalid")):
            report = build_verified_baseline(
                repository=REPO, sha=SHA, github_get=lambda path: github()[path],
                verify_health=True,
            )
        row = report["manifest"]["criteria"]["observability_operations"]["health"]
        self.assertEqual(row["status"], "missing")
        self.assertEqual(row["reason"],
                         "independent operational health evidence blocked: health_scheduler_cadence_invalid")
        self.assertFalse(report["product_ready"])

    def test_health_provider_errors_never_leak_secrets(self):
        with patch("build_readiness_evidence_manifest.verify_health_for_certification",
                   side_effect=OSError("provider secret=DO_NOT_LEAK")):
            report = build_verified_baseline(
                repository=REPO, sha=SHA, github_get=lambda path: github()[path],
                verify_health=True,
            )
        self.assertNotIn("DO_NOT_LEAK", json.dumps(report))
        self.assertEqual(
            report["manifest"]["criteria"]["observability_operations"]["health"]["reason"],
            "independent operational health evidence blocked: health_evidence_source_unavailable",
        )

    def test_post_ci_certifier_has_time_for_both_live_verifications(self):
        yaml = (ROOT / ".github/workflows/autonomous-runner.yml").read_text()
        job = yaml.split("\n  product-readiness-certification-post-ci:", 1)[1].split(
            "\n  global-readiness-post-ci:", 1)[0]
        self.assertIn("timeout-minutes: 15", job)
        self.assertIn("Persist independently reverified criterion states on exact-SHA", job)
        self.assertIn("Collect exact-SHA CI, operations and independent security evidence", job)

    def test_requirements_attestation_never_approves_other_journeys(self):
        from ai_product_factory.product_readiness_certification import VerifiedCriterionEvidence
        proof = VerifiedCriterionEvidence(
            repository=REPO, assessed_commit=SHA,
            domain="functional_completeness", criterion="requirements_inventory",
            verification_state="reviewed", source="source-verified-inventory",
            evidence=("https://github.com/" + REPO + "/actions/runs/7#sha=" + SHA,),
        )
        with patch("build_readiness_evidence_manifest.verify_requirements_inventory_fn",
                   return_value=proof):
            report = build_verified_baseline(
                repository=REPO, sha=SHA, github_get=lambda path: github()[path],
                verify_requirements_inventory=True,
            )
        self.assertEqual(
            report["manifest"]["criteria"]["functional_completeness"]["requirements_inventory"]["status"],
            "passed",
        )
        self.assertEqual(
            report["manifest"]["criteria"]["functional_completeness"]["critical_journeys"]["status"],
            "missing",
        )
        self.assertFalse(report["product_ready"])

    def test_mock_inventory_is_bounded_partial_never_a_fabricated_pass(self):
        report = build_verified_baseline(
            repository=REPO, sha=SHA, github_get=lambda path: github()[path],
            verify_static_simulation_inventory=True,
        )
        row = report["manifest"]["criteria"]["functional_completeness"]["mock_noop_demo_inventory"]
        # A source scan alone must never force partial/PASS: if the
        # import-closure audit cannot establish its bounded provenance,
        # retaining missing is the correct fail-closed result.
        self.assertIn(row["status"], {"missing", "partial"})
        if row["status"] == "partial":
            self.assertIn("dynamic production entrypoints remain unverified", row["reason"])
        else:
            self.assertIn("simulation source inventory unavailable", row["reason"])
        self.assertFalse(report["product_ready"])

    def test_requirements_source_failure_fails_closed_without_leaking_remote_errors(self):
        from trace_block1_requirements import RequirementsInventoryBlocked
        with patch("build_readiness_evidence_manifest.verify_requirements_inventory_fn",
                   side_effect=RequirementsInventoryBlocked("requirements_source_tree_incomplete")):
            report = build_verified_baseline(
                repository=REPO, sha=SHA, github_get=lambda path: github()[path],
                verify_requirements_inventory=True,
            )
        row = report["manifest"]["criteria"]["functional_completeness"]["requirements_inventory"]
        self.assertEqual(row["status"], "missing")
        self.assertIn("requirements_source_tree_incomplete", row["reason"])

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
