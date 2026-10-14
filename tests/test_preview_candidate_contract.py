import unittest

from scripts.preview_candidate_contract import (
    PreviewEligibility, REQUIRED_CHECKS, browser_dispatch_eligibility, candidate_eligibility,
)

SHA = "a" * 40
OLD_SHA = "b" * 40
REPOSITORY = "operator/ai-product-factory"


def pull_request(*, head_sha=SHA, draft=False, state="open", base="main",
                 base_repo=REPOSITORY, head_repo=REPOSITORY):
    return {"state": state, "draft": draft,
            "base": {"ref": base, "repo": {"full_name": base_repo}},
            "head": {"sha": head_sha, "repo": {"full_name": head_repo}}}


def successful_checks(sha=SHA):
    return [{"name": name, "head_sha": sha, "status": "completed", "conclusion": "success"}
            for name in REQUIRED_CHECKS]


def assess(pr=None, checks=None, changed_files=None):
    return candidate_eligibility(
        pull_request() if pr is None else pr,
        expected_sha=SHA, repository=REPOSITORY,
        checks=successful_checks() if checks is None else checks,
        changed_files=["apps/console/app/page.tsx"] if changed_files is None else changed_files,
    )


class PreviewCandidateContractTests(unittest.TestCase):
    def test_ready_exact_head_green_checks_and_console_change_pass(self):
        result = assess()
        self.assertTrue(result.allowed)
        self.assertEqual(result.reason, "eligible")

    def test_draft_unknown_or_closed_are_ineligible(self):
        for draft in (True, None, "false"):
            with self.subTest(draft=draft):
                self.assertEqual(assess(pull_request(draft=draft)).reason, "pr_draft_or_unknown")
        for state in ("closed", "merged", None):
            with self.subTest(state=state):
                self.assertEqual(assess(pull_request(state=state)).reason, "pr_not_open")

    def test_sha_changed_during_ci_poll_does_not_promote_old_sha(self):
        self.assertEqual(
            assess(pull_request(head_sha=OLD_SHA)).reason, "stale_candidate_sha"
        )
        self.assertEqual(
            assess(checks=successful_checks(OLD_SHA)).reason,
            "missing_exact_green_check:test",
        )

    def test_base_move_and_fork_fail_closed(self):
        for override in (
            {"base": "development"}, {"base_repo": "other/factory"},
            {"head_repo": "other/factory"},
        ):
            with self.subTest(override=override):
                self.assertEqual(assess(pull_request(**override)).reason, "untrusted_repo_or_base")

    def test_missing_green_checks_fail_closed(self):
        checks = successful_checks()
        for index in range(len(checks)):
            missing = checks[:index] + checks[index + 1:]
            with self.subTest(check=checks[index]["name"]):
                self.assertEqual(
                    assess(checks=missing).reason,
                    "missing_exact_green_check:" + checks[index]["name"],
                )
        checks[0] = {**checks[0], "conclusion": "skipped"}
        self.assertFalse(assess(checks=checks).allowed)

    def test_non_console_change_and_unknown_file_set_not_promotable(self):
        self.assertEqual(assess(changed_files=["docs/STATUS.md"]).reason, "preview_not_applicable")
        self.assertEqual(assess(changed_files=[]).reason, "unverified_changed_files")
        self.assertEqual(assess(changed_files=[None]).reason, "unverified_changed_files")

    def test_browser_requires_exact_sha_observed_on_preview_ref(self):
        good = assess()
        for action in ("reused", "updated", "created_then_updated"):
            self.assertTrue(browser_dispatch_eligibility(
                promotion_action=action, observed_ref_sha=SHA,
                expected_sha=SHA, candidate=good,
            ).allowed)
        for action in ("", "not_applicable_draft", "stale", "blocked", "invalid", None):
            self.assertEqual(browser_dispatch_eligibility(
                promotion_action=action, observed_ref_sha=SHA,
                expected_sha=SHA, candidate=good,
            ).reason, "promotion_not_confirmed")
        self.assertEqual(browser_dispatch_eligibility(
            promotion_action="updated", observed_ref_sha=OLD_SHA,
            expected_sha=SHA, candidate=good,
        ).reason, "preview_ref_sha_mismatch")

    def test_browser_rejects_previous_assessment_for_new_head(self):
        old = PreviewEligibility(True, "eligible", OLD_SHA)
        result = browser_dispatch_eligibility(
            promotion_action="reused", observed_ref_sha=SHA, expected_sha=SHA, candidate=old,
        )
        self.assertFalse(result.allowed)

    def test_wrong_repo_or_malformed_identity_rejected(self):
        self.assertFalse(candidate_eligibility(
            pull_request(), expected_sha="abc", repository=REPOSITORY,
            checks=successful_checks(), changed_files=["apps/console/app/page.tsx"]
        ).allowed)
        self.assertFalse(candidate_eligibility(
            pull_request(), expected_sha=SHA, repository="invalid",
            checks=successful_checks(), changed_files=["apps/console/app/page.tsx"]
        ).allowed)


if __name__ == "__main__":
    unittest.main()
