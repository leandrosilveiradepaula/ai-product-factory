import copy
import unittest

from ai_product_factory.independent_complete_console_evidence import VerifiedConsoleSurface, NAMES
from ai_product_factory.independent_console_accessibility_evidence import (
    ConsoleAccessibilityBlocked, PREFIX, TAGS,
    validate_a11y_receipt, verify_console_accessibility,
)

REPO = "owner/factory"
SHA = "a" * 40
RUN = 12345


def receipt():
    return {
        "schema": "factory-b3-wcag22-aa-keyboard-audit-v1",
        "runId": RUN, "sourceCommit": SHA, "targetCommit": SHA,
        "routeNames": list(NAMES), "engine": "@axe-core/playwright@4.14.0",
        "tags": TAGS.copy(), "desktopScans": len(NAMES),
        "mobileScans": len(NAMES), "mobileMenuScans": len(NAMES),
        "projectDetailScans": 2, "contrastNodes": 44,
        "axeRulePasses": 200, "keyboardSkipVerified": True,
        "keyboardFocusVisible": True,
        "productionWrites": 0, "paidCalls": 0, "personalDataRetained": False,
        "fullWcagCertified": False, "allRolesCertified": False,
    }


def artifacts():
    return {
        "total_count": 1,
        "artifacts": [{
            "id": 77, "name": PREFIX + str(RUN), "expired": False,
            "size_in_bytes": 950,
            "workflow_run": {"id": RUN, "head_branch": "main", "head_sha": SHA},
        }],
    }


class TestIndependentConsoleAccessibility(unittest.TestCase):
    def surface(self):
        return VerifiedConsoleSurface(REPO, SHA, RUN, SHA, 66)

    def verify(self, meta=None, reader=None):
        return verify_console_accessibility(
            repository=REPO, assessed_commit=SHA, surface=self.surface(),
            github_get=lambda path: artifacts() if meta is None else meta,
            artifact_reader=lambda **kwargs: receipt() if reader is None else reader,
        )

    def test_positive_only_for_complete_authenticated_audit(self):
        result = self.verify()
        self.assertEqual(result.criterion().criterion, "accessibility")
        self.assertEqual(result.criterion().verification_state, "observed")
        self.assertFalse(result.receipt()["full_wcag_conformance_claimed"])

    def test_absent_artifact_is_not_a_pass(self):
        self.assertIsNone(self.verify(meta={"total_count": 0, "artifacts": []}))

    def test_bad_expired_or_untrusted_artifact_fails_closed(self):
        for key, value in (("expired", True), ("size_in_bytes", 2)):
            meta = artifacts()
            meta["artifacts"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ConsoleAccessibilityBlocked):
                self.verify(meta=meta)
        meta = artifacts()
        meta["artifacts"].append(copy.deepcopy(meta["artifacts"][0]))
        meta["total_count"] = 2
        with self.assertRaises(ConsoleAccessibilityBlocked):
            self.verify(meta=meta)
        meta = artifacts()
        meta["artifacts"][0]["workflow_run"]["head_sha"] = "b" * 40
        with self.assertRaises(ConsoleAccessibilityBlocked):
            self.verify(meta=meta)

    def test_unknown_fields_overclaims_and_weak_evidence_rejected(self):
        for patch in (
            {"operator_email": "private@example.invalid"},
            {"productionWrites": 1},
            {"paidCalls": True},
            {"allRolesCertified": True},
            {"fullWcagCertified": True},
            {"desktopScans": 13},
            {"contrastNodes": 0},
            {"routeNames": list(reversed(NAMES))},
            {"targetCommit": "b" * 40},
            {"tags": []},
            {"keyboardFocusVisible": False},
        ):
            with self.subTest(patch=patch), self.assertRaises(ConsoleAccessibilityBlocked):
                validate_a11y_receipt({**receipt(), **patch},
                                      run_id=RUN, source_sha=SHA, served_sha=SHA)

    def test_invalid_artifact_payload_must_fail_not_downgrade(self):
        with self.assertRaises(ConsoleAccessibilityBlocked):
            self.verify(reader={"invalid": True})


if __name__ == "__main__":
    unittest.main()
