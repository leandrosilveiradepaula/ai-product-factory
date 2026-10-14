from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import unittest

from ai_product_factory.release_intelligence import build_release_assessment


ROOT = Path(__file__).resolve().parents[1]
GIT_COMMIT='a'*40


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
            candidate_commit=GIT_COMMIT,
            changed_files=("src/example.py",),
            risk={},
            facts={"definition_of_done": {"satisfied": [], "missing": []}},
            unknown_paid_cost=False,
            known_cost=Decimal("0"),
        )
        self.assertEqual(assessment.report["readiness_scope"], "release_candidate")
        self.assertFalse(assessment.report["product_complete"])
        self.assertEqual(assessment.report["product_readiness"]["status"], "not_assessed")

    def _full_evidence(self,sha=GIT_COMMIT):
        from ai_product_factory.product_readiness import (
            REQUIRED_DOMAINS,REQUIRED_COVERAGE_BY_DOMAIN,
        )
        verification={
            "security":"reviewed",
            "observability_operations":"observed",
            "test_strategy":"executed",
            "product_experience":"observed",
            "documentation":"reviewed",
            "functional_completeness":"executed",
        }
        return {
            "ready":True,"status":"passed","assessed_commit":sha,
            # Independent durable factory_evaluations row fields: a JSON result
            # cannot overwrite this information in SupabaseReleasePolicyStore.
            "evaluation_status":"passed","baseline_ref":sha,
            "assessment_ref":"audit:full-product:2026-10-14",
            "domains":{
                key:{
                    "status":"passed","reason":"assessed for exact SHA",
                    "evidence":[f"audit:{key}:{sha}"],
                    "coverage":list(REQUIRED_COVERAGE_BY_DOMAIN[key]),
                    "verification_state":verification[key],
                }
                for key in REQUIRED_DOMAINS
            },
            "blockers":[],
        }

    def _release(self,product,sha=GIT_COMMIT):
        return build_release_assessment(
            policy=_policy(),candidate_commit=sha,
            changed_files=("src/example.py",),risk={},
            facts={"definition_of_done":{"satisfied":[],"missing":[]},
                   "product_readiness":product},
            unknown_paid_cost=False,known_cost=Decimal("0"),
        )

    def test_product_ready_requires_validated_full_six_domain_assessment(self):
        assessment=self._release(self._full_evidence())
        self.assertTrue(assessment.report["product_complete"])
        self.assertEqual(assessment.report["product_readiness"]["status"],"passed")
        self.assertEqual(len(assessment.report["product_readiness"]["domains"]),6)

    def test_short_sha_can_never_mark_release_product_complete(self):
        evidence=self._full_evidence(sha="abc")
        result=self._release(evidence,sha="abc")
        self.assertFalse(result.report["product_complete"])
        self.assertEqual(result.report["product_readiness"]["status"],"not_ready")
        self.assertIn(
            "assessed_commit: exact 40-character Git SHA required",
            result.report["product_readiness"]["blockers"],
        )

    def test_ready_true_summary_without_domains_fails_closed(self):
        assessment=self._release({
            "ready":True,"status":"passed","assessed_commit":GIT_COMMIT,
            "assessment_ref":"audit:forged-summary",
        })
        self.assertFalse(assessment.report["product_complete"])
        self.assertFalse(assessment.report["product_readiness"]["ready"])
        self.assertEqual(assessment.report["product_readiness"]["status"],"not_ready")
        self.assertEqual(assessment.report["readiness_scope"],"release_candidate")

    def test_missing_critical_domain_never_passes(self):
        evidence=self._full_evidence()
        evidence["domains"].pop("security")
        out=self._release(evidence)
        self.assertFalse(out.report["product_complete"])
        self.assertIn("security: missing assessment",out.report["product_readiness"]["blockers"])

    def test_missing_critical_e2e_coverage_never_passes(self):
        evidence=self._full_evidence()
        evidence["domains"]["test_strategy"]["coverage"]=["unit_integration"]
        out=self._release(evidence)
        self.assertFalse(out.report["product_complete"])
        self.assertTrue(any("critical_e2e" in b for b in out.report["product_readiness"]["blockers"]))

    def test_declared_product_blockers_cannot_be_overridden_by_green_domains(self):
        evidence=self._full_evidence()
        evidence["blockers"]=["CRM: Preview candidate missing"]
        out=self._release(evidence)
        self.assertFalse(out.report["product_complete"])
        self.assertIn("CRM: Preview candidate missing",out.report["product_readiness"]["blockers"])

    def test_malformed_blocker_record_fails_closed(self):
        evidence=self._full_evidence()
        evidence["blockers"]="not-a-list"
        out=self._release(evidence)
        self.assertFalse(out.report["product_complete"])
        self.assertIn("invalid product assessment blocker record",out.report["product_readiness"]["blockers"])

    def test_baseline_ref_cannot_impersonate_assessed_commit(self):
        evidence=self._full_evidence()
        evidence.pop("assessed_commit")
        evidence["baseline_ref"]=GIT_COMMIT
        out=self._release(evidence)
        self.assertFalse(out.report["product_complete"])
        self.assertEqual(out.report["product_readiness"]["status"],"stale")

    def test_recorded_negative_state_not_promoted_by_valid_domains(self):
        evidence=self._full_evidence()
        evidence["ready"]=False
        out=self._release(evidence)
        self.assertFalse(out.report["product_complete"])
        self.assertEqual(out.report["product_readiness"]["status"],"not_ready")

    def test_release_human_gate_independent_of_product_complete_flag(self):
        good=self._release(self._full_evidence())
        bad=self._release({"ready":True,"status":"passed","assessed_commit":GIT_COMMIT})
        self.assertEqual(good.report["release_state"],bad.report["release_state"])
        self.assertEqual(good.report["readiness_scope"],"release_candidate")

    def test_stale_product_assessment_does_not_make_new_candidate_complete(self):
        assessment = build_release_assessment(
            policy=_policy(),
            candidate_commit="new-sha",
            changed_files=("src/example.py",),
            risk={},
            facts={
                "definition_of_done": {"satisfied": [], "missing": []},
                "product_readiness": {
                    "ready": True,
                    "status": "passed",
                    "assessed_commit": "old-sha",
                    "assessment_ref": "audit:old",
                },
            },
            unknown_paid_cost=False,
            known_cost=Decimal("0"),
        )
        self.assertFalse(assessment.report["product_complete"])
        self.assertEqual(assessment.report["product_readiness"]["status"], "stale")

    def test_release_rejects_not_applicable_security_even_with_evidence(self):
        assessment=self._full_evidence()
        assessment["domains"]["security"]={
            "status":"not_applicable","reason":"app owner says no security",
            "evidence":["claimed-review"],"verification_state":"reviewed",
        }
        result=self._release(assessment)
        self.assertFalse(result.report["product_complete"])
        self.assertIn(
            "security: not_applicable forbidden for required domain",
            result.report["product_readiness"]["blockers"],
        )

    def test_release_rejects_nonstring_evidence_with_other_valid_references(self):
        assessment=self._full_evidence()
        assessment["domains"]["test_strategy"]["evidence"].append({"ref":"fabricated"})
        result=self._release(assessment)
        self.assertFalse(result.report["product_complete"])
        self.assertIn("test_strategy: malformed evidence",result.report["product_readiness"]["blockers"])

    def test_release_accepts_only_product_experience_headless_exception(self):
        assessment=self._full_evidence()
        assessment["domains"]["product_experience"]={
            "status":"not_applicable",
            "reason":"no user interface; background-only service",
            "evidence":["architecture:headless-verified"],
            "verification_state":"reviewed",
        }
        result=self._release(assessment)
        self.assertTrue(result.report["product_complete"])
        self.assertEqual(result.report["product_readiness"]["status"],"passed")

    def test_failed_row_cannot_be_promoted_by_embedded_ready_true(self):
        evidence=self._full_evidence()
        evidence["evaluation_status"]="failed"
        out=self._release(evidence)
        self.assertFalse(out.report["product_complete"])
        self.assertEqual(out.report["product_readiness"]["status"],"not_ready")
        self.assertIn("durable product evaluation",out.report["product_readiness"]["reason"])

    def test_nonpassing_or_missing_durable_evaluation_status_fails_closed(self):
        for value in (None,"not_ready","pending","success",True,0):
            with self.subTest(status=value):
                evidence=self._full_evidence()
                evidence["evaluation_status"]=value
                out=self._release(evidence)
                self.assertFalse(out.report["product_complete"])
                self.assertEqual(out.report["product_readiness"]["status"],"not_ready")

    def test_baseline_from_durable_row_must_match_candidate(self):
        for value in (None,"", "b"*40, "a"*39, False):
            with self.subTest(baseline=value):
                evidence=self._full_evidence()
                evidence["baseline_ref"]=value
                out=self._release(evidence)
                self.assertFalse(out.report["product_complete"])
                self.assertEqual(out.report["product_readiness"]["status"],"stale")
                self.assertIn("recorded evaluation baseline",out.report["product_readiness"]["reason"])

    def test_missing_row_provenance_never_approves_product(self):
        evidence=self._full_evidence()
        evidence.pop("evaluation_status")
        evidence.pop("baseline_ref")
        out=self._release(evidence)
        self.assertFalse(out.report["product_complete"])

    def test_recorded_provenance_does_not_replace_global_evidence(self):
        evidence=self._full_evidence()
        evidence["domains"].pop("security")
        out=self._release(evidence)
        self.assertFalse(out.report["product_complete"])
        self.assertIn("security: missing assessment",out.report["product_readiness"]["blockers"])

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
