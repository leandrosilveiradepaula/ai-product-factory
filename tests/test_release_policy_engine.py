import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from ai_product_factory.release_intelligence import build_release_assessment
from ai_product_factory.release_policy_engine import ReleasePolicyContext,evaluate_release_policy,load_release_policy


POLICY={
    "policy_key":"factory-release-v1","version":1,
    "production":{"human_release_required":True,"auto_merge_allowed":False},
    "gates":{
        "unknown_paid_cost":"block",
        "missing_nonhuman_definition_of_done":"block",
        "destructive_data_change":"human_gate",
        "expands_sensitive_access":"human_gate",
        "new_paid_service":"human_gate",
        "material_requirement_change":"human_gate",
        "production_change":"human_gate",
    },
    "rollback":{"migration_change_requires_verified_rollback":True},
}


class ReleasePolicyEngineTests(unittest.TestCase):
    def test_policy_loader_rejects_auto_merge(self):
        bad={**POLICY,"production":{"human_release_required":True,"auto_merge_allowed":True}}
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"policy.json";path.write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError,"forbid auto merge"):
                load_release_policy(path)

    def test_unknown_paid_cost_blocks(self):
        out=evaluate_release_policy(POLICY,ReleasePolicyContext(unknown_paid_cost=True))
        self.assertEqual(out.outcome,"blocked")

    def test_missing_nonhuman_dod_blocks(self):
        out=evaluate_release_policy(POLICY,ReleasePolicyContext(missing_nonhuman_dod=("qa","preview")))
        self.assertEqual(out.outcome,"blocked")

    def test_migration_without_verified_rollback_blocks(self):
        out=evaluate_release_policy(POLICY,ReleasePolicyContext(migration_change=True,rollback_verified=False))
        self.assertEqual(out.outcome,"blocked")
        self.assertTrue(any("rollback" in reason for reason in out.reasons))

    def test_ready_production_candidate_still_requires_human_release(self):
        out=evaluate_release_policy(POLICY,ReleasePolicyContext(production_change=True))
        self.assertEqual(out.outcome,"ready_for_human_release")
        self.assertTrue(any("human gate" in reason for reason in out.reasons))

    def test_release_assessment_ignores_human_only_missing(self):
        facts={
            "definition_of_done":{
                "satisfied":["github_ci","qa","preview","browser_evidence"],
                "missing":[{"key":"human_release","human_only":True}],
            },
            "requirements":{"total":2,"with_passing_evidence":2},
            "evaluations":[],"preview":{"status":"ready"},
            "previous_production":{"deployment_ref":"old"},
        }
        out=build_release_assessment(
            policy=POLICY,candidate_commit="a"*40,changed_files=("src/core.py",),risk={},
            facts=facts,unknown_paid_cost=False,known_cost=Decimal("0.1"),
        )
        self.assertEqual(out.decision.outcome,"ready_for_human_release")
        self.assertEqual(out.context["missing_nonhuman_dod"],[])
        self.assertFalse(out.rollback["required"])

    def test_release_assessment_blocks_migration_until_rollback_evidence(self):
        facts={
            "definition_of_done":{
                "satisfied":["github_ci","qa"],
                "missing":[{"key":"rollback_analysis","human_only":False},{"key":"human_release","human_only":True}],
            },
            "requirements":{"total":1,"with_passing_evidence":1},
        }
        out=build_release_assessment(
            policy=POLICY,candidate_commit="b"*40,changed_files=("supabase/migrations/20260929.sql",),risk={},
            facts=facts,unknown_paid_cost=False,known_cost=Decimal("0"),
        )
        self.assertEqual(out.decision.outcome,"blocked")
        self.assertTrue(out.rollback["required"])
        self.assertFalse(out.rollback["verified"])


if __name__=="__main__":
    unittest.main()
