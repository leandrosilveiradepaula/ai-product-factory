import unittest

from ai_product_factory.evidence import build_quality_evidence
from ai_product_factory.review_gate import (
    EvalResult,
    ReviewFinding,
    Severity,
    evaluate_quality_gate,
)


class ReviewGateTests(unittest.TestCase):
    def test_warning_does_not_block(self):
        d = evaluate_quality_gate(findings=(
            ReviewFinding("STYLE", Severity.WARNING, "minor"),
        ))
        self.assertTrue(d.passed)

    def test_error_finding_blocks(self):
        d = evaluate_quality_gate(findings=(
            ReviewFinding("CORRECTNESS", Severity.ERROR, "broken"),
        ))
        self.assertFalse(d.passed)

    def test_critical_finding_blocks(self):
        d = evaluate_quality_gate(findings=(
            ReviewFinding("SECURITY", Severity.CRITICAL, "unsafe"),
        ))
        self.assertFalse(d.passed)
        self.assertEqual(len(d.critical_findings), 1)

    def test_required_eval_failure_blocks(self):
        d = evaluate_quality_gate(evals=(
            EvalResult("behavior", passed=False, required=True),
        ))
        self.assertFalse(d.passed)
        self.assertEqual(len(d.failed_required_evals), 1)

    def test_optional_eval_failure_does_not_block(self):
        d = evaluate_quality_gate(evals=(
            EvalResult("cost", passed=False, required=False),
        ))
        self.assertTrue(d.passed)

    def test_evidence_bundle_is_serializable(self):
        findings = (ReviewFinding("STYLE", Severity.INFO, "ok", "a.py"),)
        evals = (EvalResult("tests", True, True, 1.0),)
        d = evaluate_quality_gate(findings=findings, evals=evals)
        bundle = build_quality_evidence(
            source_commit="a",
            candidate_commit="b",
            ci_status="success",
            decision=d,
            findings=findings,
            evals=evals,
        )
        data = bundle.to_dict()
        self.assertTrue(data["metadata"]["quality_gate_passed"])
        self.assertEqual(data["candidate_commit"], "b")


if __name__ == "__main__":
    unittest.main()
