from __future__ import annotations

import unittest

from ai_product_factory.product_readiness import (
    REQUIRED_COVERAGE_BY_DOMAIN,
    REQUIRED_DOMAINS,
    assess_product_readiness,
)


class ProductReadinessTests(unittest.TestCase):
    def _passed_domains(self):
        return {
            key:{
                "status":"passed",
                "reason":"verified",
                "evidence":[f"evidence:{key}"],
                "coverage":list(REQUIRED_COVERAGE_BY_DOMAIN[key]),
            }
            for key in REQUIRED_DOMAINS
        }

    def test_all_domains_with_evidence_and_coverage_can_pass(self):
        out=assess_product_readiness(assessed_commit="abc",assessment_ref="audit:1",domains=self._passed_domains())
        self.assertTrue(out.ready)
        self.assertEqual(out.status,"passed")
        self.assertEqual(out.blockers,())

    def test_missing_domain_is_fail_closed(self):
        domains=self._passed_domains();domains.pop("security")
        out=assess_product_readiness(assessed_commit="abc",assessment_ref="audit:1",domains=domains)
        self.assertFalse(out.ready)
        self.assertIn("security: missing assessment",out.blockers)

    def test_not_applicable_requires_reason(self):
        domains=self._passed_domains();domains["product_experience"]={"status":"not_applicable","evidence":[]}
        out=assess_product_readiness(assessed_commit="abc",assessment_ref="audit:1",domains=domains)
        self.assertFalse(out.ready)
        self.assertIn("product_experience: not_applicable without reason",out.blockers)

    def test_passed_domain_requires_evidence(self):
        domains=self._passed_domains();domains["security"]["evidence"]=[]
        out=assess_product_readiness(assessed_commit="abc",assessment_ref="audit:1",domains=domains)
        self.assertFalse(out.ready)
        self.assertIn("security: passed without evidence",out.blockers)

    def test_passed_domain_requires_explicit_coverage(self):
        domains=self._passed_domains();domains["product_experience"]["coverage"]=["responsive"]
        out=assess_product_readiness(assessed_commit="abc",assessment_ref="audit:1",domains=domains)
        self.assertFalse(out.ready)
        blocker=next(item for item in out.blockers if item.startswith("product_experience: missing coverage"))
        self.assertIn("accessibility",blocker)
        self.assertIn("states",blocker)
        self.assertIn("surface_inventory",blocker)

    def test_blank_evidence_and_coverage_do_not_count(self):
        domains=self._passed_domains()
        domains["documentation"]["evidence"]=["   "]
        domains["documentation"]["coverage"]=["setup_configuration","operations"," "]
        out=assess_product_readiness(assessed_commit="abc",assessment_ref="audit:1",domains=domains)
        self.assertFalse(out.ready)
        self.assertIn("documentation: passed without evidence",out.blockers)
        self.assertTrue(any(item.startswith("documentation: missing coverage") for item in out.blockers))

    def test_not_applicable_does_not_require_passed_coverage(self):
        domains=self._passed_domains()
        domains["product_experience"]={
            "status":"not_applicable",
            "reason":"headless service with no user interface",
            "evidence":["architecture:headless"],
        }
        out=assess_product_readiness(assessed_commit="abc",assessment_ref="audit:1",domains=domains)
        self.assertTrue(out.ready)

    def test_critical_blocker_forces_not_ready(self):
        out=assess_product_readiness(
            assessed_commit="abc",
            assessment_ref="audit:1",
            domains=self._passed_domains(),
            critical_blockers=("P0 auth bypass",),
        )
        self.assertFalse(out.ready)
        self.assertIn("P0 auth bypass",out.blockers)


if __name__=="__main__":unittest.main()
