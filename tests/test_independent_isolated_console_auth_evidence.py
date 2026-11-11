from __future__ import annotations
import unittest

from ai_product_factory.independent_isolated_console_auth_evidence import (
    IsolatedConsoleAuthEvidenceBlocked, verify_isolated_console_auth,
)
from ai_product_factory.product_readiness_certification import VerifiedCriterionEvidence

REPO="leandrosilveiradepaula/ai-product-factory"; SHA="a"*40

def regression(receipt=None):
    return VerifiedCriterionEvidence(
        domain="test_strategy",criterion="regression_gates",repository=REPO,
        assessed_commit=SHA,verification_state="executed",source="test",evidence=("https://x#sha="+SHA,),
        retained_receipt=({"postgres_qa":{"run_id":42,"source_sha":"b"*40,"scope":"identical_git_tree"}}
                          if receipt is None else receipt),
    )

class IsolatedConsoleAuthEvidenceTests(unittest.TestCase):
    def test_exact_tree_postgres_receipt_yields_only_partial_safe_facts(self):
        proof=verify_isolated_console_auth(repository=REPO,assessed_commit=SHA,regression_proof=regression())
        self.assertIn("#sha="+SHA,proof.evidence()[0])
        self.assertTrue(proof.receipt()["isolated_sql_role_and_rpc_negatives_verified"])
        self.assertEqual(proof.receipt()["does_not_certify"],["authn_authz","data_access_boundaries","product_ready"])
        self.assertEqual(proof.receipt()["writes"],0)

    def test_missing_or_unbound_postgres_receipt_fails_closed(self):
        for value in (None, {}, {"postgres_qa":{"run_id":0}}, {"postgres_qa":{"run_id":1,"source_sha":"bad","scope":"wrong"}}):
            with self.subTest(value=value), self.assertRaises(IsolatedConsoleAuthEvidenceBlocked):
                verify_isolated_console_auth(repository=REPO,assessed_commit=SHA,
                    regression_proof=regression(value) if value is not None else object())

    def test_pipeline_requires_independent_revalidation(self):
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        builder=(root/"scripts/build_readiness_evidence_manifest.py").read_text()
        certifier=(root/"scripts/certify_product_readiness.py").read_text()
        workflow=(root/".github/workflows/autonomous-runner.yml").read_text()
        self.assertIn("isolated_console_auth_evidence",builder)
        self.assertIn("isolated Console Auth receipt changed before persistence",certifier)
        self.assertIn("--verify-isolated-console-auth",workflow)

if __name__=="__main__": unittest.main()
