from __future__ import annotations

from decimal import Decimal
from pathlib import Path

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


def test_release_candidate_never_implies_product_ready_without_global_assessment():
    assessment = build_release_assessment(
        policy=_policy(),
        candidate_commit="abc123",
        changed_files=("src/example.py",),
        risk={},
        facts={"definition_of_done": {"satisfied": [], "missing": []}},
        unknown_paid_cost=False,
        known_cost=Decimal("0"),
    )
    assert assessment.report["readiness_scope"] == "release_candidate"
    assert assessment.report["product_complete"] is False
    assert assessment.report["product_readiness"]["status"] == "not_assessed"


def test_product_ready_requires_explicit_passing_product_assessment():
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
    assert assessment.report["product_complete"] is True
    assert assessment.report["product_readiness"]["assessment_ref"].startswith("audit:full-product:")


def test_governance_forbids_ambiguous_product_completion_claims():
    agents = (ROOT / "AGENTS.md").read_text()
    contract = (ROOT / "docs/PRODUCT_READINESS.md").read_text()
    for marker in ("work_item_complete", "release_candidate_ready", "release_completed", "product_ready"):
        assert marker in agents
        assert marker in contract
    assert "nao implicam" in agents
    assert "must never infer `product_ready`" in contract
