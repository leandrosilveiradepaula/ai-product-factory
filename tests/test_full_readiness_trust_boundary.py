"""The 19-criterion engine can pass only with all 19 trusted verifiers.

A synthetic TEST-ONLY trusted verifier does not enable an operational PASS:
the production CLI contains only the explicitly installed source verifiers.
"""
from __future__ import annotations

import unittest

from ai_product_factory.product_readiness_certification import (
    CertificationEvidenceError, VerifiedCriterionEvidence,
    certify_product_readiness, conservative_verified_manifest,
)
from tests.test_product_readiness_certification import SHA, REPO, github
from scripts.certify_product_readiness import require_verified_baseline


class FullReadinessTrustBoundaryTests(unittest.TestCase):
    def fixture(self, *, omit=None):
        data = github()
        gh = lambda path: data[path]
        manifest = conservative_verified_manifest(
            repository=REPO, assessed_commit=SHA, github_get=gh
        )
        expected = set()
        for domain, rows in manifest["criteria"].items():
            for key, item in rows.items():
                if (domain, key) == ("test_strategy", "unit_integration"):
                    continue
                expected.add((domain, key))
                item.update(
                    status="passed",
                    evidence=["UNTRUSTED_MANIFEST_CANNOT_PROVE:" + SHA],
                )

        def trusted(domain, key, snapshot):
            if (domain, key) == omit:
                return None
            return VerifiedCriterionEvidence(
                domain=domain, criterion=key,
                repository=REPO, assessed_commit=SHA,
                verification_state=manifest["criteria"][domain][key]["verification_state"],
                source="TEST_ONLY_ALL_18_INDEPENDENT_VERIFIERS",
                evidence=("independently-verified-TEST-ONLY:" + SHA + ":" + domain + "/" + key,),
            )

        report = certify_product_readiness(
            repository=REPO, assessed_commit=SHA,
            manifest=manifest, github_get=gh, trusted_verifier=trusted,
        )
        return report, manifest, expected

    def test_engine_can_reach_19_but_only_with_18_additional_verified_proofs(self):
        report, manifest, expected = self.fixture()
        self.assertEqual(len(expected), 18)
        self.assertTrue(report.assessment.ready)
        self.assertEqual(report.assessment.status, "passed")
        self.assertEqual(report.assessment.blockers, ())
        self.assertEqual(sum(c["status"] == "passed" for d in report.report["criteria"].values()
                             for c in d.values()), 19)
        envelope = {
            "schema_version": 1,
            "scope": "read_only_independent_source_verified_baseline",
            "repository": REPO,
            "assessed_commit": SHA,
            "writes": 0,
            "paid_calls": 0,
            "start_authorized": False,
            "product_ready": True,
            "manifest": manifest,
            "source_snapshot": report.report["source_snapshot"],
            "evidence_digest": report.evidence_digest,
            "assessment": report.assessment.as_result(),
        }
        self.assertEqual(
            require_verified_baseline(envelope, repository=REPO, assessed_commit=SHA),
            manifest,
        )
        # The envelope is NOT enough without executing the 18 trusted verifiers.
        no_trust = certify_product_readiness(
            repository=REPO, assessed_commit=SHA,
            manifest=manifest, github_get=lambda path: github()[path],
        )
        self.assertFalse(no_trust.assessment.ready)

    def test_one_missing_trusted_proof_blocks_readiness(self):
        report, _, _ = self.fixture(omit=("security", "authn_authz"))
        self.assertFalse(report.assessment.ready)
        self.assertEqual(report.report["criteria"]["security"]["authn_authz"]["status"], "failed")

    def test_boolean_and_assessment_consistency_in_envelope(self):
        report, manifest, _ = self.fixture()
        good = dict(
            schema_version=1, scope="read_only_independent_source_verified_baseline",
            repository=REPO, assessed_commit=SHA, writes=0, paid_calls=0,
            start_authorized=False, product_ready=True, manifest=manifest,
            source_snapshot=report.report["source_snapshot"],
            evidence_digest=report.evidence_digest,
            assessment=report.assessment.as_result(),
        )
        for field, val in (
            ("product_ready", False), ("product_ready", "true"),
            ("repository", "another/repo"), ("assessed_commit", "b" * 40),
            ("writes", 1), ("scope", "self_asserted"),
        ):
            altered = dict(good)
            altered[field] = val
            with self.subTest(field=field, value=val), self.assertRaises(CertificationEvidenceError):
                require_verified_baseline(altered, repository=REPO, assessed_commit=SHA)


if __name__ == "__main__":
    unittest.main()
