"""Regression: a successful visual capture without configured B2 evidence is NOT a B2 PASS.

Source-verification, not a browser CI badge, is the only path to a durable
positive security criterion. Never re-run the protected operator workflow here.
"""
from __future__ import annotations

import unittest
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from certify_product_readiness import require_b2_source_readiness
from ai_product_factory.product_readiness_certification import CertificationEvidenceError


def baseline(auth="partial", boundary="partial"):
    return {"criteria":{"security":{
        "authn_authz":{"status":auth},
        "data_access_boundaries":{"status":boundary},
    }}}


class B2PostVisualSecurityAdmissionTests(unittest.TestCase):
    def check(self, *, enabled=True, ready=False, manifest=None, receipt=None):
        return require_b2_source_readiness(
            enabled=enabled,prerequisites_ready=ready,
            manifest=baseline() if manifest is None else manifest,
            evidence={} if receipt is None else receipt,
        )

    def test_successful_capture_without_publishable_key_never_blocks_other_certifications(self):
        self.assertIs(self.check(enabled=True,ready=False),False)
        self.assertIs(self.check(enabled=False,ready=False),False)
        self.assertIs(self.check(enabled=True,ready=True),True)
        self.assertIs(self.check(enabled=False,ready=True),False)

    def test_forged_positive_without_complete_source_fails_closed(self):
        for cell in ("authn_authz","data_access_boundaries"):
            claim=baseline()
            claim["criteria"]["security"][cell]["status"]="passed"
            with self.subTest(cell=cell), self.assertRaises(CertificationEvidenceError):
                self.check(ready=False,manifest=claim)
            with self.subTest(cell=cell+" disabled"), self.assertRaises(CertificationEvidenceError):
                self.check(enabled=False,ready=True,manifest=claim)
        for enabled, ready in ((True,False),(False,True),(False,False)):
            with self.subTest(enabled=enabled,ready=ready), self.assertRaises(CertificationEvidenceError):
                self.check(enabled=enabled,ready=ready,
                           receipt={"independent_b2_signed_security_evidence":{"schema":"forged"}})

    def test_positive_claim_requires_actual_independent_reverification_not_parser_flag(self):
        self.assertIs(self.check(ready=True,manifest=baseline(auth="passed",boundary="passed"),
                                 receipt={"independent_b2_signed_security_evidence":{}}),True)
        # A true admission decision is NOT a certificate: main() still requires
        # verify_independent_signed_b2 and byte-identical artifact receipts.
        source=(ROOT/"scripts/certify_product_readiness.py").read_text()
        self.assertIn("verify_independent_signed_b2(",source)
        self.assertIn('evidence.get("independent_b2_signed_security_evidence") != b2_security_proof.receipt()',source)
        self.assertIn('if not isinstance(row, dict) or row.get("status") != "passed"',source)
        self.assertIn("B2 independently verified security baseline inconsistent",source)

    def test_console_capture_identity_is_not_overwritten_by_native_traceability(self):
        source=(ROOT/"scripts/certify_product_readiness.py").read_text()
        capture=source.index("authenticated_console_proof = proof")
        trace=source.index("    proof = None\n    if args.verify_native_v2_traceability:")
        b2=source.index("    b2_security_proof = None")
        self.assertLess(capture,trace)
        self.assertLess(trace,b2)
        assert source[b2:].count("authenticated_capture=authenticated_console_proof")==1
        assert "authenticated_console_proof is not None" in source[b2:]
        assert "full_surface_proof is not None" in source[b2:]
        assert 'raise CertificationEvidenceError("B2 independent prerequisites unavailable")' not in source[b2:]

    def test_manual_workflow_shows_which_security_source_is_missing(self):
        workflow=(ROOT/".github/workflows/authenticated-visual-evidence.yml").read_text()
        self.assertIn("FACTORY_B2_SUPABASE_PUBLISHABLE_KEY",workflow)
        self.assertIn("::warning title=B2 source missing::",workflow)
        self.assertIn("Capture authenticated Console",workflow)
        self.assertNotIn("sb_secret_",workflow)


if __name__ == "__main__":
    unittest.main()
