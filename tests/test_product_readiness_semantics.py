from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import unittest

from ai_product_factory.release_intelligence import build_release_assessment


ROOT = Path(__file__).resolve().parents[1]


def _policy() -> dict:
    return {
        "policy_key": "test",
        "version": 1,
        "production": {"auto_merge_allowed": False, "human_release_required": True},
        "gates": {"production_change": "human_gate"},
        "rollback": {"migration_change_requires_verified_rollback": True},
    }


class ProductReadinessSemanticsTests(unittest.TestCase):
    def test_release_candidate_never_implies_product_ready_without_global_assessment(self):
        assessment = build_release_assessment(
            policy=_policy(),
            candidate_commit="abc123",
            changed_files=("src/example.py",),
            risk={},
            facts={"definition_of_done": {"satisfied": [], "missing": []}},
            unknown_paid_cost=False,
            known_cost=Decimal("0"),
        )
        self.assertEqual(assessment.report["readiness_scope"], "release_candidate")
        self.assertFalse(assessment.report["product_complete"])
        self.assertEqual(assessment.report["product_readiness"]["status"], "not_assessed")

    def test_product_ready_requires_explicit_passing_product_assessment(self):
        assessment = build_release_assessment(
            policy=_policy(),
            candidate_commit="abc123",
            changed_files=("src/example.py",),
            risk={},
            facts={
                "definition_of_done": {"satisfied": [], "missing": []},
                "product_readiness": {
                    "ready": True,
                    "status": "passed",
                    "assessment_ref": "audit:full-product:2026-10-06",
                },
            },
            unknown_paid_cost=False,
            known_cost=Decimal("0"),
        )
        self.assertTrue(assessment.report["product_complete"])
        self.assertTrue(assessment.report["product_readiness"]["assessment_ref"].startswith("audit:full-product:"))

    def test_governance_forbids_ambiguous_product_completion_claims(self):
        agents = (ROOT / "AGENTS.md").read_text()
        contract = (ROOT / "docs/PRODUCT_READINESS.md").read_text()
        for marker in ("work_item_complete", "release_candidate_ready", "release_completed", "product_ready"):
            self.assertIn(marker, agents)
            self.assertIn(marker, contract)
        self.assertIn("nao implicam", agents)
        self.assertIn("must never infer `product_ready`", contract)


if __name__ == "__main__":
    unittest.main()
