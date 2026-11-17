"""No-secret deterministic diagnostics for the same independent B4 source checks."""
import unittest

from ai_product_factory.independent_b4_greenfield_e2e import (
    B4GreenfieldE2EBlocked,
    _b4_fixed_reason,
    _b4_best_reason,
    _verify_non_runtime_ancestor,
)

TARGET = "owner/private-greenfield"
OLD, NEW = "a" * 40, "b" * 40
COMPARE = "/repos/" + TARGET + "/compare/" + OLD + "..." + NEW


class B4SafeDiagnosticsTests(unittest.TestCase):
    def test_canned_reasons_only_never_echo_untrusted_error(self):
        self.assertEqual(_b4_fixed_reason(
            B4GreenfieldE2EBlocked("b4_exact_sha_quality_lane_missing")),
            "b4_exact_sha_quality_lane_missing")
        for exc in (
            ValueError("Bearer secret-token"),
            PermissionError("HTTP 403 body includes API key"),
            B4GreenfieldE2EBlocked("b4_broken\nPRIVATE-TOKEN"),
            B4GreenfieldE2EBlocked("external provider URL"),
            B4GreenfieldE2EBlocked("b4_" + "a" * 150),
        ):
            code = _b4_fixed_reason(exc)
            self.assertEqual(code, "b4_independent_source_unavailable")
            self.assertNotIn("secret", code.lower())
            self.assertNotIn("PRIVATE", code)

    def test_deepest_cross_repo_blocker_preferred_over_unrelated_greenfield(self):
        self.assertEqual(_b4_best_reason([
            "b4_real_change_set_e2e_missing_or_ambiguous",
            "b4_cross_repo_read_unavailable",
        ]), "b4_cross_repo_read_unavailable")
        self.assertEqual(_b4_best_reason([
            "b4_not_human_originated_greenfield",
            "b4_browser_e2e_checks_incomplete",
        ]), "b4_browser_e2e_checks_incomplete")
        self.assertEqual(_b4_best_reason([
            "b4_not_human_originated_greenfield",
            "b4_real_change_set_e2e_missing_or_ambiguous",
        ]), "b4_greenfield_verified_candidate_missing_or_ambiguous")

    def assert_denied(self, get, code):
        with self.assertRaises(B4GreenfieldE2EBlocked) as cm:
            _verify_non_runtime_ancestor(
                cross_repo_get=get, target_repo=TARGET,
                predecessor=OLD, current=NEW,
            )
        self.assertEqual(str(cm.exception), code)

    def test_permission_denial_never_leaks_details(self):
        self.assert_denied(
            lambda path: (_ for _ in ()).throw(
                PermissionError("b4_explicit_cross_repo_credential_required")),
            "b4_cross_repo_explicit_credential_missing")
        self.assert_denied(
            lambda path: (_ for _ in ()).throw(
                PermissionError("Bearer secret-token from HTTP 403")),
            "b4_cross_repo_access_denied")
        self.assert_denied(
            lambda path: (_ for _ in ()).throw(
                ValueError("upstream URL and auth metadata")),
            "b4_cross_repo_read_unavailable")
        self.assert_denied(
            lambda path: (_ for _ in ()).throw(
                RuntimeError("private API response")),
            "b4_cross_repo_read_unavailable")

    def test_valid_exact_non_runtime_compare_remains_accepted(self):
        calls=[]
        def get(path):
            calls.append(path)
            return {
                "status":"ahead", "behind_by":0, "ahead_by":2,
                "total_commits":2,
                "files":[
                    {"filename":"docs/OPERATIONS.md","status":"modified"},
                    {"filename":"scripts/verify_migration_forward_recovery.sh","status":"added"},
                    {"filename":".github/workflows/validate.yml","status":"modified"},
                ],
            }
        _verify_non_runtime_ancestor(
            cross_repo_get=get, target_repo=TARGET,
            predecessor=OLD, current=NEW,
        )
        self.assertEqual(calls, [COMPARE])

    def test_runtime_change_still_denied(self):
        def get(path):
            return {
                "status":"ahead", "behind_by":0, "ahead_by":1,
                "total_commits":1,
                "files":[{"filename":"app/server.js","status":"modified"}],
            }
        self.assert_denied(get,"b4_browser_witness_runtime_changed")


if __name__ == "__main__":
    unittest.main()
