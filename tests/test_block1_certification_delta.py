"""Regression alarm contract: no decrease can hide behind a stable score."""
import unittest

from scripts.check_block1_certification_delta import (
    CertificationRegression, compare_certifications, collect,
)
from ai_product_factory.product_readiness import REQUIRED_COVERAGE_BY_DOMAIN

SHA1 = "a" * 40
SHA2 = "b" * 40
REPO = "leandrosilveiradepaula/ai-product-factory"


def make_certificate(sha, overrides=None):
    overrides = overrides or {}
    criteria = {}
    for domain, required in REQUIRED_COVERAGE_BY_DOMAIN.items():
        criteria[domain] = {
            criterion: {"status": overrides.get((domain, criterion), "missing")}
            for criterion in required
        }
    return {"repository": REPO, "assessed_commit": sha, "state": "persisted",
            "report": {"criteria": criteria}}


class CertificateDeltaTests(unittest.TestCase):
    def test_identical_ten_passes_are_monotonic(self):
        cells = [(d, key) for d, keys in REQUIRED_COVERAGE_BY_DOMAIN.items()
                 for key in keys][:10]
        status = {cell: "passed" for cell in cells}
        report = compare_certifications(
            [make_certificate(SHA2, status), make_certificate(SHA1, status)], SHA2)
        self.assertEqual(report["current_passed"], 10)
        self.assertEqual(report["regressed"], [])
        self.assertTrue(report["monotonic"])
        self.assertFalse(report["product_ready_claimed"])
        self.assertEqual(report["writes"], 0)

    def test_one_lost_pass_blocks_even_with_more_new_passes(self):
        cells = [(d, key) for d, keys in REQUIRED_COVERAGE_BY_DOMAIN.items()
                 for key in keys]
        previous = {cell: "passed" for cell in cells[:10]}
        current = {cell: "passed" for cell in cells[1:12]}
        report = compare_certifications(
            [make_certificate(SHA2, current), make_certificate(SHA1, previous)], SHA2)
        self.assertEqual(report["current_passed"], 11)
        self.assertEqual(report["previous_passed"], 10)
        self.assertFalse(report["monotonic"])
        self.assertEqual(report["regressed"], ["%s/%s" % cells[0]])
        self.assertEqual(len(report["newly_passed"]), 2)

    def test_stale_main_cannot_reuse_old_passes(self):
        with self.assertRaisesRegex(CertificationRegression, "current_main"):
            compare_certifications([make_certificate(SHA1)], SHA2)

    def test_missing_or_duplicate_history_fails_closed(self):
        with self.assertRaises(CertificationRegression):
            compare_certifications([], SHA2)
        same_sha = compare_certifications([make_certificate(SHA2), make_certificate(SHA2)], SHA2)
        self.assertTrue(same_sha['monotonic'])
        self.assertEqual(same_sha['regressed'], [])

    def test_bad_or_extra_criterion_cannot_count_as_monotonic(self):
        cert = make_certificate(SHA2)
        cert["report"]["criteria"]["security"]["new_feature"] = {"status": "passed"}
        with self.assertRaises(CertificationRegression):
            compare_certifications([cert], SHA2)
        cert = make_certificate(SHA2)
        cert["report"]["criteria"]["security"]["authn_authz"]["status"] = "success"
        with self.assertRaises(CertificationRegression):
            compare_certifications([cert], SHA2)

    def test_get_must_return_correct_repository_and_single_current_sha(self):
        calls = []
        def get(path):
            calls.append(path)
            return [make_certificate(SHA2), make_certificate(SHA1)]
        result = collect(get, SHA2)
        self.assertTrue(result["monotonic"])
        self.assertIn("state=eq.persisted", calls[0])
        self.assertIn("order=created_at.desc", calls[0])
        self.assertEqual(len(calls), 1)
        def wrong_repo(path):
            cert = make_certificate(SHA2)
            cert["repository"] = "attacker/repository"
            return [cert]
        with self.assertRaisesRegex(CertificationRegression, "repository"):
            collect(wrong_repo, SHA2)


if __name__ == "__main__":
    unittest.main()
