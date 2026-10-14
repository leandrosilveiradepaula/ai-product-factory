from __future__ import annotations

import unittest

SHA='a'*40

from ai_product_factory.product_readiness import (
    REQUIRED_COVERAGE_BY_DOMAIN,
    REQUIRED_DOMAINS,
    assess_product_readiness,
)


class ProductReadinessTests(unittest.TestCase):
    def _passed_domains(self):
        verification={
            "security":"reviewed",
            "observability_operations":"observed",
            "test_strategy":"executed",
            "product_experience":"observed",
            "documentation":"reviewed",
            "functional_completeness":"reviewed",
        }
        return {
            key:{
                "status":"passed",
                "reason":"verified",
                "evidence":[f"evidence:{key}"],
                "coverage":list(REQUIRED_COVERAGE_BY_DOMAIN[key]),
                "verification_state":verification[key],
            }
            for key in REQUIRED_DOMAINS
        }

    def test_all_domains_with_evidence_and_coverage_can_pass(self):
        out=assess_product_readiness(assessed_commit=SHA,assessment_ref="audit:1",domains=self._passed_domains())
        self.assertTrue(out.ready)
        self.assertEqual(out.status,"passed")
        self.assertEqual(out.blockers,())

    def test_readiness_requires_full_git_commit_not_short_prefix(self):
        for invalid in ("abc", "a"*39, "a"*41, "g"*40,
                        "main", " "*2+"a"*40, "a"*40+" "):
            with self.subTest(commit=invalid):
                out=assess_product_readiness(
                    assessed_commit=invalid,assessment_ref="audit:complete",
                    domains=self._passed_domains(),
                )
                self.assertFalse(out.ready)
                self.assertEqual(out.status,"not_ready")
                self.assertIn("assessed_commit: exact 40-character Git SHA required",out.blockers)

    def test_full_uppercase_git_commit_normalized(self):
        out=assess_product_readiness(
            assessed_commit="ABCDEF0123456789ABCDEF0123456789ABCDEF01",
            assessment_ref="audit:sha-normalization",
            domains=self._passed_domains(),
        )
        self.assertTrue(out.ready)
        self.assertEqual(out.assessed_commit,"abcdef0123456789abcdef0123456789abcdef01")

    def test_missing_domain_is_fail_closed(self):
        domains=self._passed_domains();domains.pop("security")
        out=assess_product_readiness(assessed_commit=SHA,assessment_ref="audit:1",domains=domains)
        self.assertFalse(out.ready)
        self.assertIn("security: missing assessment",out.blockers)

    def test_not_applicable_requires_reason(self):
        domains=self._passed_domains();domains["product_experience"]={"status":"not_applicable","evidence":[],"verification_state":"reviewed"}
        out=assess_product_readiness(assessed_commit=SHA,assessment_ref="audit:1",domains=domains)
        self.assertFalse(out.ready)
        self.assertIn("product_experience: not_applicable without reason",out.blockers)

    def test_passed_domain_requires_evidence(self):
        domains=self._passed_domains();domains["security"]["evidence"]=[]
        out=assess_product_readiness(assessed_commit=SHA,assessment_ref="audit:1",domains=domains)
        self.assertFalse(out.ready)
        self.assertIn("security: passed without evidence",out.blockers)

    def test_passed_domain_requires_explicit_coverage(self):
        domains=self._passed_domains();domains["product_experience"]["coverage"]=["responsive"]
        out=assess_product_readiness(assessed_commit=SHA,assessment_ref="audit:1",domains=domains)
        self.assertFalse(out.ready)
        blocker=next(item for item in out.blockers if item.startswith("product_experience: missing coverage"))
        self.assertIn("accessibility",blocker)
        self.assertIn("states",blocker)
        self.assertIn("surface_inventory",blocker)

    def test_blank_evidence_and_coverage_do_not_count(self):
        domains=self._passed_domains()
        domains["documentation"]["evidence"]=["   "]
        domains["documentation"]["coverage"]=["setup_configuration","operations"," "]
        out=assess_product_readiness(assessed_commit=SHA,assessment_ref="audit:1",domains=domains)
        self.assertFalse(out.ready)
        self.assertIn("documentation: passed without evidence",out.blockers)
        self.assertTrue(any(item.startswith("documentation: missing coverage") for item in out.blockers))

    def test_not_applicable_does_not_require_passed_coverage(self):
        domains=self._passed_domains()
        domains["product_experience"]={
            "status":"not_applicable",
            "reason":"headless service with no user interface",
            "evidence":["architecture:headless"],
            "verification_state":"reviewed",
        }
        out=assess_product_readiness(assessed_commit=SHA,assessment_ref="audit:1",domains=domains)
        self.assertTrue(out.ready)


    def test_not_applicable_requires_evidence(self):
        domains=self._passed_domains()
        domains["product_experience"]={
            "status":"not_applicable",
            "reason":"headless service",
            "evidence":[],
            "verification_state":"reviewed",
        }
        out=assess_product_readiness(assessed_commit=SHA,assessment_ref="audit:1",domains=domains)
        self.assertFalse(out.ready)
        self.assertIn("product_experience: not_applicable without evidence",out.blockers)

    def test_test_strategy_requires_executed_verification(self):
        domains=self._passed_domains()
        domains["test_strategy"]["verification_state"]="reviewed"
        out=assess_product_readiness(assessed_commit=SHA,assessment_ref="audit:1",domains=domains)
        self.assertFalse(out.ready)
        self.assertIn("test_strategy: invalid verification_state",out.blockers)

    def test_domain_requires_explicit_verification_state(self):
        domains=self._passed_domains()
        domains["security"].pop("verification_state")
        out=assess_product_readiness(assessed_commit=SHA,assessment_ref="audit:1",domains=domains)
        self.assertFalse(out.ready)
        self.assertIn("security: invalid verification_state",out.blockers)

    def test_critical_blocker_forces_not_ready(self):
        out=assess_product_readiness(
            assessed_commit=SHA,
            assessment_ref="audit:1",
            domains=self._passed_domains(),
            critical_blockers=("P0 auth bypass",),
        )
        self.assertFalse(out.ready)
        self.assertIn("P0 auth bypass",out.blockers)


    def test_all_six_domains_not_applicable_is_never_product_ready(self):
        domains=self._passed_domains()
        for key in REQUIRED_DOMAINS:
            domains[key]={
                "status":"not_applicable","reason":"claimed exception",
                "evidence":[f"audit:{key}"],
                "verification_state":domains[key]["verification_state"],
            }
        result=assess_product_readiness(
            assessed_commit=SHA,assessment_ref="audit:1",domains=domains
        )
        self.assertFalse(result.ready)
        self.assertIn("security: not_applicable forbidden for required domain",result.blockers)
        self.assertIn("test_strategy: not_applicable forbidden for required domain",result.blockers)
        self.assertIn("functional_completeness: not_applicable forbidden for required domain",result.blockers)

    def test_required_domains_cannot_claim_not_applicable(self):
        for key in ("security","observability_operations","test_strategy",
                    "documentation","functional_completeness"):
            with self.subTest(domain=key):
                domains=self._passed_domains()
                domains[key]={
                    "status":"not_applicable","reason":"no tests necessary",
                    "evidence":["assessment:review"],
                    "verification_state":domains[key]["verification_state"],
                }
                result=assess_product_readiness(
                    assessed_commit=SHA,assessment_ref="audit:1",domains=domains
                )
                self.assertFalse(result.ready)
                self.assertIn(f"{key}: not_applicable forbidden for required domain",result.blockers)

    def test_malformed_evidence_items_never_count_as_verified(self):
        for bad in (None,42,True,{"ref":"audit:fake"}):
            with self.subTest(value=bad):
                domains=self._passed_domains()
                domains["security"]["evidence"]=["evidence:real",bad]
                result=assess_product_readiness(
                    assessed_commit=SHA,assessment_ref="audit:1",domains=domains
                )
                self.assertFalse(result.ready)
                self.assertIn("security: malformed evidence",result.blockers)

    def test_malformed_evidence_container_never_passes(self):
        domains=self._passed_domains()
        domains["security"]["evidence"]={"ref":"audit:fake"}
        result=assess_product_readiness(
            assessed_commit=SHA,assessment_ref="audit:1",domains=domains
        )
        self.assertFalse(result.ready)
        self.assertIn("security: malformed evidence",result.blockers)

    def test_malformed_coverage_never_passes_with_valid_coverage_present(self):
        domains=self._passed_domains()
        domains["security"]["coverage"].append({"key":"forged"})
        result=assess_product_readiness(
            assessed_commit=SHA,assessment_ref="audit:1",domains=domains
        )
        self.assertFalse(result.ready)
        self.assertIn("security: malformed coverage",result.blockers)

    def test_none_or_nonstring_assessment_identity_is_rejected(self):
        for sha,ref in ((None,"audit:1"),(SHA,None),(123,"audit:1"),(SHA,7)):
            with self.subTest(sha=sha,ref=ref):
                with self.assertRaises(ValueError):
                    assess_product_readiness(
                        assessed_commit=sha,assessment_ref=ref,
                        domains=self._passed_domains(),
                    )

if __name__=="__main__":unittest.main()
