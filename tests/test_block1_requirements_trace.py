"""Fail-closed tests for requirement coverage and missing source paths."""
import tempfile
from pathlib import Path
import unittest

from ai_product_factory.product_readiness import REQUIRED_COVERAGE_BY_DOMAIN
from scripts.trace_block1_requirements import CANDIDATES, matrix

ROOT = Path(__file__).resolve().parents[1]


class RequirementTraceabilityTests(unittest.TestCase):
    def test_all_nineteen_requirements_are_mapped_without_pass(self):
        result = matrix(ROOT)
        self.assertEqual(result["count"], 19)
        self.assertEqual(result["certified"], 0)
        self.assertFalse(result["product_ready"])
        self.assertTrue(all(x["certification_status"] == "unverified"
                            and x["independent_execution_verified"] is False
                            for x in result["requirements"]))
        self.assertEqual(set(CANDIDATES),
                         {d + "/" + k for d, ks in REQUIRED_COVERAGE_BY_DOMAIN.items() for k in ks})

    def test_missing_sources_cannot_be_silently_satisfied(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = matrix(Path(tmp))
            self.assertEqual(result["count"], 19)
            self.assertTrue(all(x["source_inventory_status"] == "incomplete"
                                for x in result["requirements"]))
            self.assertEqual(result["certified"], 0)

    def test_digest_only_and_no_source_contents(self):
        result = matrix(ROOT)
        for row in result["requirements"]:
            self.assertEqual(set(row), {"criterion", "journey_stages", "candidate_sources", "missing_sources",
                                        "independent_execution_verified", "source_inventory_status",
                                        "certification_status"})
            self.assertTrue(all(len(x["sha256"]) == 64 for x in row["candidate_sources"]))
            self.assertTrue(row["journey_stages"])

    def test_product_experience_rows_bind_the_executable_browser_contracts(self):
        rows = {row["criterion"]: row for row in matrix(ROOT)["requirements"]}
        self.assertIn("scripts/console_surface_coverage_contract.mjs", {
            ref["path"] for ref in rows["product_experience/surface_inventory"]["candidate_sources"]
        })
        self.assertIn("scripts/console_accessibility_contract.mjs", {
            ref["path"] for ref in rows["product_experience/accessibility"]["candidate_sources"]
        })
        self.assertIn("scripts/verify_block1_b3_live_console_states.mjs", {
            ref["path"] for ref in rows["product_experience/states"]["candidate_sources"]
        })


if __name__ == "__main__":
    unittest.main()
