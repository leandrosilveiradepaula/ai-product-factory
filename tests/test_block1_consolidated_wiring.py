"""Co-located integration contracts for the consolidated Block 1 evidence batch.

These prove CI/post-CI wiring is exercised, not product readiness. The live
post-merge observer must still validate all source proofs and persist a report.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ConsolidatedBlock1Wiring(unittest.TestCase):
    def test_post_ci_persists_before_comparing_actual_certificates(self):
        workflow = (ROOT / ".github/workflows/autonomous-runner.yml").read_text()
        job = workflow.split("\n  product-readiness-certification-post-ci:", 1)[1].split(
            "\n  global-readiness-post-ci:", 1)[0]
        persisted = job.index("Persist independently reverified criterion states")
        delta = job.index("Detect persisted Block 1 criterion regression by exact SHA")
        witness = job.index("Witness real CRM and greenfield blockers without writes")
        self.assertLess(persisted, delta)
        self.assertLess(delta, witness)
        self.assertIn("factory-block1-criterion-delta.json", job)
        self.assertIn("factory-block1-real-journey-witness.json", job)
        self.assertIn("control-plane-oidc", job)
        self.assertIn("if: always()", job)

    def test_all_mobile_surfaces_are_audited_in_actual_browser_capture(self):
        capture = (ROOT / "scripts/capture_authenticated_console.mjs").read_text()
        self.assertIn("const routes = CONSOLE_ROUTES;", capture)
        self.assertIn("for (const route of routes.map(", capture)
        self.assertIn("verifyConsoleSurfaceCoverage({", capture)
        self.assertIn("interactionEvidence.surfaceCoverage", capture)
        workflow = (ROOT / ".github/workflows/validate.yml").read_text()
        self.assertIn("scripts/tests/console_surface_coverage_contract.test.mjs", workflow)

    def test_critical_e2e_requires_real_journey_not_synthetic_receipt(self):
        from scripts.audit_block1_real_journeys_readonly import assess
        result = assess(
            projects=[{"id": "2d30e00a-ff72-4044-b838-011c263ed672",
                       "project_key": "crm-infodive",
                       "repository": "leandrosilveiradepaula/crm-infodive",
                       "is_active": True}],
            journeys=[],
            greenfield=[{"project_key": "infodive-service-desk",
                         "project_kind": "greenfield",
                         "repository": "owner/retired",
                         "is_active": True}],
        )
        self.assertFalse(result["critical_journeys_certified"])
        self.assertFalse(result["critical_e2e_certified"])
        self.assertFalse(result["product_ready"])
        self.assertEqual(result["other_active_greenfield_count"], 0)


if __name__ == "__main__":
    unittest.main()
