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

    def _candidate(self, definition_of_done=None, *, changed_files=("src/core.py",)):
        if definition_of_done is None:
            facts={}
        else:
            facts={"definition_of_done":definition_of_done}
        return build_release_assessment(
            policy=POLICY,candidate_commit="f"*40,changed_files=changed_files,
            risk={},facts=facts,unknown_paid_cost=False,known_cost=Decimal("0"),
        )

    def test_false_string_is_not_human_only_and_blocks_release(self):
        for value in ("false","true",0,1,None,[],{}):
            with self.subTest(value=value):
                decision=self._candidate({
                    "satisfied":["github_ci"],
                    "missing":[{"key":"critical_e2e","human_only":value}],
                })
                self.assertEqual(decision.decision.outcome,"blocked")
                self.assertIn("critical_e2e",decision.context["missing_nonhuman_dod"])

    def test_true_boolean_is_the_only_exempt_human_gate(self):
        decision=self._candidate({
            "satisfied":["github_ci"],
            "missing":[{"key":"human_release","human_only":True}],
        })
        self.assertEqual(decision.decision.outcome,"ready_for_human_release")
        self.assertEqual(decision.context["missing_nonhuman_dod"],[])

    def test_missing_dod_payload_or_fields_blocks_instead_of_implicitly_passing(self):
        for dod in (None,{},{"satisfied":[]},{"missing":[]},
                    {"satisfied":[],"missing":"qa"},
                    {"satisfied":"github_ci","missing":[]}):
            with self.subTest(dod=dod):
                out=self._candidate(dod)
                self.assertEqual(out.decision.outcome,"blocked")
                self.assertIn("definition_of_done_unverified",
                              out.context["missing_nonhuman_dod"])

    def test_malformed_missing_entries_fail_closed(self):
        for row in (None,7,False,{"human_only":True},
                    {"key":42,"human_only":True},{"key":"  ","human_only":True}):
            with self.subTest(row=row):
                out=self._candidate({"satisfied":["github_ci"],"missing":[row]})
                self.assertEqual(out.decision.outcome,"blocked")
                self.assertIn("definition_of_done_invalid_missing",
                              out.context["missing_nonhuman_dod"])

    def test_missing_and_satisfied_cannot_conflict(self):
        out=self._candidate({
            "satisfied":["critical_e2e","github_ci"],
            "missing":[{"key":"critical_e2e","human_only":True}],
        })
        self.assertEqual(out.decision.outcome,"blocked")
        self.assertIn("definition_of_done_conflicting_status:critical_e2e",
                      out.context["missing_nonhuman_dod"])

    def test_duplicate_missing_keys_fail_closed(self):
        out=self._candidate({
            "satisfied":["github_ci"],
            "missing":[
                {"key":"qa","human_only":False},
                {"key":"qa","human_only":True},
            ],
        })
        self.assertEqual(out.decision.outcome,"blocked")
        self.assertIn("definition_of_done_duplicate_missing:qa",
                      out.context["missing_nonhuman_dod"])

    def test_invalid_satisfied_entry_blocks_even_if_other_gates_are_clear(self):
        out=self._candidate({
            "satisfied":["github_ci",{"key":"rollback_analysis"}],
            "missing":[],
        })
        self.assertEqual(out.decision.outcome,"blocked")
        self.assertIn("definition_of_done_invalid_satisfied",
                      out.context["missing_nonhuman_dod"])

    def test_malformed_dod_cannot_bypass_migration_rollback_evidence(self):
        out=self._candidate(
            {"satisfied":"rollback_analysis","missing":[]},
            changed_files=("supabase/migrations/20261014_sample.sql",),
        )
        self.assertEqual(out.decision.outcome,"blocked")
        self.assertFalse(out.rollback["verified"])
        self.assertIn("definition_of_done_unverified",out.context["missing_nonhuman_dod"])

    def test_human_only_true_cannot_waive_nonhuman_required_checks(self):
        for key in ("github_ci","qa","preview","browser_evidence",
                    "critical_e2e","rollback_analysis","security_review"):
            with self.subTest(key=key):
                out=self._candidate({
                    "satisfied":["github_ci"] if key!="github_ci" else ["qa"],
                    "missing":[{"key":key,"human_only":True}],
                })
                self.assertEqual(out.decision.outcome,"blocked")
                self.assertIn(
                    "definition_of_done_unauthorized_human_only:"+key,
                    out.context["missing_nonhuman_dod"],
                )
                self.assertIn(key,out.context["missing_nonhuman_dod"])

    def test_empty_well_typed_dod_cannot_claim_release_ready(self):
        out=self._candidate({"satisfied":[],"missing":[]})
        self.assertEqual(out.decision.outcome,"blocked")
        self.assertIn(
            "definition_of_done_missing_verified_ci",
            out.context["missing_nonhuman_dod"],
        )

    def test_human_release_only_without_ci_is_still_blocked(self):
        out=self._candidate({
            "satisfied":[],
            "missing":[{"key":"human_release","human_only":True}],
        })
        self.assertEqual(out.decision.outcome,"blocked")
        self.assertIn("definition_of_done_missing_verified_ci",
                      out.context["missing_nonhuman_dod"])

    def test_declaring_github_ci_human_only_cannot_bypass_ci(self):
        out=self._candidate({
            "satisfied":["qa"],
            "missing":[{"key":"github_ci","human_only":True},
                       {"key":"human_release","human_only":True}],
        })
        self.assertEqual(out.decision.outcome,"blocked")
        self.assertIn("github_ci",out.context["missing_nonhuman_dod"])
        self.assertIn("definition_of_done_missing_verified_ci",
                      out.context["missing_nonhuman_dod"])

    def test_release_ready_requires_ci_and_only_real_human_merge_gate(self):
        out=self._candidate({
            "satisfied":["github_ci","qa","preview","browser_evidence"],
            "missing":[{"key":"human_release","human_only":True}],
        })
        self.assertEqual(out.decision.outcome,"ready_for_human_release")
        self.assertEqual(out.context["missing_nonhuman_dod"],[])
        self.assertIn("human",out.decision.reasons[0])

    def test_nonhuman_human_only_spoof_does_not_change_production_gate(self):
        spoof=self._candidate({
            "satisfied":["github_ci"],
            "missing":[{"key":"qa","human_only":True}],
        })
        legitimate=self._candidate({
            "satisfied":["github_ci"],
            "missing":[{"key":"human_release","human_only":True}],
        })
        self.assertEqual(spoof.decision.outcome,"blocked")
        self.assertEqual(legitimate.decision.outcome,"ready_for_human_release")
        self.assertTrue(legitimate.context["production_change"])



if __name__=="__main__":
    unittest.main()
