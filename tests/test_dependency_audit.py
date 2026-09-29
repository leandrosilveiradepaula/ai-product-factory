import unittest
from datetime import datetime, timezone

from ai_product_factory.dependency_audit import AuditPolicyError, evaluate_dependency_audit


NOW = datetime(2026, 9, 29, 22, 0, tzinfo=timezone.utc)


def report(vulnerabilities):
    return {"auditReportVersion": 2, "vulnerabilities": vulnerabilities}


def finding(severity):
    return {"name": "package", "severity": severity, "via": [], "effects": [], "range": "*"}


def lock(**versions):
    return {
        "packages": {
            f"node_modules/{name}": {"version": version}
            for name, version in versions.items()
        }
    }


def policy(expires_at="2026-10-02T23:59:59Z"):
    return {
        "schema_version": 1,
        "audit_level": "moderate",
        "exceptions": [
            {
                "package": "next",
                "installed_version": "15.5.26",
                "max_severity": "high",
                "expires_at": expires_at,
                "reason": "Temporary exact exception tracked by issue #402 pending upstream remediation.",
            },
            {
                "package": "postcss",
                "installed_version": "8.4.31",
                "max_severity": "high",
                "expires_at": expires_at,
                "reason": "Temporary exact transitive exception tracked by issue #402 pending upstream remediation.",
            },
        ],
    }


class DependencyAuditTests(unittest.TestCase):
    def test_known_exact_exceptions_pass_before_expiry(self):
        violations, accepted = evaluate_dependency_audit(
            report({"next": finding("high"), "postcss": finding("moderate")}),
            lock(next="15.5.26", postcss="8.4.31"),
            policy(),
            now=NOW,
        )
        self.assertEqual([], violations)
        self.assertEqual(2, len(accepted))

    def test_unknown_package_fails(self):
        violations, _ = evaluate_dependency_audit(
            report({"new-package": finding("high")}),
            lock(**{"new-package": "1.0.0"}),
            policy(),
            now=NOW,
        )
        self.assertIn("has no approved exception", violations[0])

    def test_version_drift_fails(self):
        violations, _ = evaluate_dependency_audit(
            report({"next": finding("high")}),
            lock(next="15.5.27"),
            policy(),
            now=NOW,
        )
        self.assertIn("does not match exception version", violations[0])

    def test_expired_exception_fails(self):
        violations, _ = evaluate_dependency_audit(
            report({"next": finding("high")}),
            lock(next="15.5.26"),
            policy(expires_at="2026-09-29T21:00:00Z"),
            now=NOW,
        )
        self.assertIn("exception expired", violations[0])

    def test_critical_cannot_be_exempted_by_high_ceiling(self):
        violations, _ = evaluate_dependency_audit(
            report({"next": finding("critical")}),
            lock(next="15.5.26"),
            policy(),
            now=NOW,
        )
        self.assertIn("exceeds exception ceiling", violations[0])

    def test_malformed_audit_report_fails_closed(self):
        with self.assertRaises(AuditPolicyError):
            evaluate_dependency_audit(
                {"vulnerabilities": {}},
                lock(next="15.5.26"),
                policy(),
                now=NOW,
            )

    def test_policy_rejects_wildcard_exception(self):
        unsafe = policy()
        unsafe["exceptions"][0]["package"] = "next*"
        with self.assertRaises(AuditPolicyError):
            evaluate_dependency_audit(
                report({}),
                lock(next="15.5.26"),
                unsafe,
                now=NOW,
            )

    def test_policy_rejects_critical_exception_ceiling(self):
        unsafe = policy()
        unsafe["exceptions"][0]["max_severity"] = "critical"
        with self.assertRaises(AuditPolicyError):
            evaluate_dependency_audit(
                report({}),
                lock(next="15.5.26"),
                unsafe,
                now=NOW,
            )


if __name__ == "__main__":
    unittest.main()
