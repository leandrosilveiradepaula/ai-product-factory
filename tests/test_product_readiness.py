from __future__ import annotations

import unittest

from ai_product_factory.product_readiness import REQUIRED_DOMAINS,assess_product_readiness


class ProductReadinessTests(unittest.TestCase):
    def _passed_domains(self):
        return {key:{"status":"passed","reason":"verified","evidence":[f"evidence:{key}"]} for key in REQUIRED_DOMAINS}

    def test_all_domains_with_evidence_can_pass(self):
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
        domains=self._passed_domains();domains["security"]={"status":"passed","reason":"reviewed","evidence":[]}
        out=assess_product_readiness(assessed_commit="abc",assessment_ref="audit:1",domains=domains)
        self.assertFalse(out.ready)
        self.assertIn("security: passed without evidence",out.blockers)

    def test_critical_blocker_forces_not_ready(self):
        out=assess_product_readiness(assessed_commit="abc",assessment_ref="audit:1",domains=self._passed_domains(),critical_blockers=("P0 auth bypass",))
        self.assertFalse(out.ready)
        self.assertIn("P0 auth bypass",out.blockers)


if __name__=="__main__":unittest.main()
