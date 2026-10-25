import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ai_product_factory.github_loop import CIState
from ai_product_factory.github_rest import GitHubRestAdapter, GitHubRequestError
from ai_product_factory.preview_candidate_promotion import (
    PreviewPromotionBlocked, PreviewPromotionPolicy, promote_preview_candidate,
)

BASE = "a" * 40
CANDIDATE = "b" * 40
CHANGE_SET = "673a2fc7-5f8c-40da-8bec-18ff6bb7eeed"
BRANCH = "preview/factory-cs-673a2fc7"


def item(policy=None):
    preview = {"provider": "vercel", "mode": "github", "required": True}
    if policy is None:
        policy = {
            "mode": "github_ref_cas", "enabled": True, "source": "change_set",
            "branch_prefix": "preview/factory-cs",
            "base_ref": "preview/hardening-release-candidate",
            "max_ahead_commits": 8,
        }
    preview["promotion"] = policy
    return SimpleNamespace(
        manifest={"preview": preview},
        change_set_id=CHANGE_SET, candidate_commit=CANDIDATE,
        pr_number=197, repository="sample/other-repo",
        branch="factory/change-set-673a2fc7", run_id="eafd1ac1-b57d-47d9-98eb-55a90003e6db",
    )


def pr(**fields):
    payload = dict(
        number=197, state="open", merged=False, draft=False, head_sha=CANDIDATE,
        head_repository="sample/other-repo", head_ref="factory/change-set-673a2fc7",
        base_ref="preview/hardening-release-candidate", base_sha=BASE,
    )
    payload.update(fields)
    return SimpleNamespace(**payload)


def github():
    gh = MagicMock()
    gh.repository = "sample/other-repo"
    gh.get_pull_request.return_value = pr()
    gh.get_ci_state.return_value = CIState.SUCCESS
    gh.compare_commits.return_value = {
        "status": "ahead", "behind_by": 0, "ahead_by": 4,
        "files": ["src/a.ts", "src/b.test.ts"],
    }
    gh.get_commit_statuses.return_value = []
    return gh


class PromotionTests(unittest.TestCase):
    def invoke(self, gh=None, candidate=None, check_epoch=None, audit=None):
        gh = gh or github()
        evidence = []
        outcome = promote_preview_candidate(
            item=candidate or item(), github=gh, check_epoch=check_epoch or (lambda: None),
            audit=audit or (lambda name, payload: evidence.append((name, payload))),
        )
        return outcome, gh, evidence

    def test_missing_policy_never_reads_github_or_writes(self):
        target = item()
        target.manifest["preview"].pop("promotion")
        gh = github()
        out, _, _ = self.invoke(gh=gh, candidate=target)
        self.assertEqual(out["status"], "not_configured")
        gh.get_pull_request.assert_not_called()
        gh.create_branch_at_sha.assert_not_called()

    def test_promotion_on_existing_base_uses_cas_not_merge(self):
        gh = github()
        gh.get_branch_sha.side_effect = [BASE, CANDIDATE]
        out, gh, events = self.invoke(gh=gh)
        self.assertEqual(out, {"status": "promoted", "branch": BRANCH})
        gh.fast_forward_preview_ref_cas.assert_called_once_with(
            branch=BRANCH, expected_sha=BASE, candidate_sha=CANDIDATE,
        )
        gh.create_branch_at_sha.assert_not_called()
        self.assertEqual(events[0][0], "preview.promotion_intent")
        self.assertEqual(events[-1][0], "preview.promotion_completed")

    def test_missing_ref_created_at_base_before_exact_cas(self):
        gh = github()
        gh.get_branch_sha.side_effect = [GitHubRequestError(404), BASE, CANDIDATE]
        out, _, _ = self.invoke(gh=gh)
        self.assertEqual(out["status"], "promoted")
        gh.create_branch_at_sha.assert_called_once_with(BRANCH, BASE)

    def test_ref_already_candidate_does_not_retrigger_deployment(self):
        gh = github()
        gh.get_branch_sha.return_value = CANDIDATE
        out, _, events = self.invoke(gh=gh)
        self.assertEqual(out["status"], "ref_already_candidate")
        self.assertEqual(events[-1][0], "preview.promotion_ref_reused")
        gh.fast_forward_preview_ref_cas.assert_not_called()

    def test_existing_vercel_status_reuses_without_git_writes(self):
        gh = github()
        gh.get_commit_statuses.return_value = [{"context": "Vercel", "state": "success"}]
        out, _, _ = self.invoke(gh=gh)
        self.assertEqual(out["status"], "existing_vercel_status")
        gh.get_branch_sha.assert_not_called()

    def test_quota_denies_before_any_branch_write(self):
        gh = github()
        gh.get_commit_statuses.return_value = [{
            "context": "Vercel", "state": "failure",
            "description": "Deployment rate limited — retry in 24 hours.",
        }]
        with self.assertRaisesRegex(PreviewPromotionBlocked, "vercel_quota_blocked"):
            self.invoke(gh=gh)
        gh.create_branch_at_sha.assert_not_called()
        gh.fast_forward_preview_ref_cas.assert_not_called()

    def test_changed_status_before_cas_denies(self):
        gh = github()
        gh.get_branch_sha.return_value = BASE
        gh.get_commit_statuses.side_effect = [
            [], [], [{"context": "Vercel", "state": "failure",
                      "description": "build-rate-limit"}],
        ]
        with self.assertRaisesRegex(PreviewPromotionBlocked, "vercel_quota_blocked"):
            self.invoke(gh=gh)
        gh.fast_forward_preview_ref_cas.assert_not_called()

    def test_epoch_revoked_denies_before_create(self):
        gh = github()
        gh.get_branch_sha.side_effect = GitHubRequestError(404)
        with self.assertRaisesRegex(PermissionError, "generation"):
            self.invoke(gh=gh, check_epoch=lambda: (_ for _ in ()).throw(PermissionError("generation")))
        gh.create_branch_at_sha.assert_not_called()
        gh.fast_forward_preview_ref_cas.assert_not_called()

    def test_concurrent_branch_movement_denied(self):
        gh = github()
        gh.get_branch_sha.return_value = "c" * 40
        with self.assertRaisesRegex(PreviewPromotionBlocked, "preview_ref_drift"):
            self.invoke(gh=gh)
        gh.fast_forward_preview_ref_cas.assert_not_called()

    def test_concurrent_ref_creation_denied_without_adopting(self):
        gh = github()
        gh.get_branch_sha.side_effect = GitHubRequestError(404)
        gh.create_branch_at_sha.side_effect = GitHubRequestError(422)
        with self.assertRaisesRegex(PreviewPromotionBlocked, "preview_ref_create_conflict"):
            self.invoke(gh=gh)
        gh.fast_forward_preview_ref_cas.assert_not_called()

    def test_wrong_pr_sha_or_repo_denied(self):
        for changed in ({"head_sha": "c" * 40}, {"head_repository": "other/repo"},
                        {"base_ref": "main"}, {"draft": True}, {"state": "closed"}):
            with self.subTest(changed=changed):
                gh = github()
                gh.get_pull_request.return_value = pr(**changed)
                with self.assertRaisesRegex(PreviewPromotionBlocked, "candidate_pr_drift"):
                    self.invoke(gh=gh)
                gh.get_branch_sha.assert_not_called()

    def test_native_ci_failure_or_pending_denied(self):
        for ci in (CIState.FAILURE, CIState.PENDING):
            with self.subTest(ci=ci):
                gh = github()
                gh.get_ci_state.return_value = ci
                with self.assertRaisesRegex(PreviewPromotionBlocked, "candidate_native_ci_not_green"):
                    self.invoke(gh=gh)
                gh.get_branch_sha.assert_not_called()

    def test_non_ancestral_or_unbounded_comparison_denied(self):
        for evidence in (
            {"status": "diverged", "behind_by": 1, "ahead_by": 4},
            {"status": "ahead", "behind_by": 0, "ahead_by": 33},
            {"status": "ahead", "behind_by": 0, "ahead_by": True},
        ):
            with self.subTest(evidence=evidence):
                gh = github()
                gh.compare_commits.return_value = evidence
                with self.assertRaisesRegex(PreviewPromotionBlocked, "candidate_not_bounded_fast_forward"):
                    self.invoke(gh=gh)

    def test_policy_denies_unsafe_refs_and_disabled_opt_in(self):
        for policy in (
            {"mode": "github_ref_cas", "enabled": False, "source": "pull_request",
             "branch_prefix": "preview/pr", "base_ref": "main"},
            {"mode": "github_ref_cas", "enabled": True, "source": "pull_request",
             "branch_prefix": "main", "base_ref": "main"},
            {"mode": "github_ref_cas", "enabled": True, "source": "change_set",
             "branch_prefix": "preview/../main", "base_ref": "main"},
            {"mode": "github_ref_cas", "enabled": True, "source": "pull_request",
             "branch_prefix": "preview/pr", "base_ref": "refs/heads/main"},
            {"mode": "github_ref_cas", "enabled": True, "source": "pull_request",
             "branch_prefix": "preview/pr", "base_ref": "main", "max_ahead_commits": True},
        ):
            with self.subTest(policy=policy):
                with self.assertRaises(PreviewPromotionBlocked):
                    self.invoke(candidate=item(policy))

    def test_a_non_crm_project_uses_its_own_pr_policy(self):
        target = item({
            "mode": "github_ref_cas", "enabled": True, "source": "pull_request",
            "branch_prefix": "preview/candidate", "base_ref": "preview/test",
        })
        target.pr_number = 9
        target.branch = "factory/new"
        gh = github()
        gh.get_pull_request.return_value = pr(number=9, base_ref="preview/test", head_ref="factory/new")
        gh.get_branch_sha.side_effect = [BASE, CANDIDATE]
        out, _, _ = self.invoke(gh=gh, candidate=target)
        self.assertEqual(out["branch"], "preview/candidate-9")


class GitHubAtomicCasTests(unittest.TestCase):
    def adapter(self, transport):
        with patch.dict(os.environ, {"FACTORY_GITHUB_TOKEN": "dummy"}, clear=True):
            return GitHubRestAdapter(repository="sample/other-repo", transport=transport)

    def test_atomic_graphql_update_ref_requires_exact_expected_oid(self):
        calls = []
        def transport(method, url, headers, body):
            data = json.loads(body) if body is not None else None
            calls.append((method, url, data))
            if "/compare/" in url:
                return 200, {"status": "ahead", "behind_by": 0, "ahead_by": 4, "files": []}
            if "/git/ref/" in url:
                return 200, {"node_id": "REF_safe", "object": {"sha": BASE}}
            if url.endswith("/graphql"):
                return 200, {"data": {"updateRef": {"ref": {"target": {"oid": CANDIDATE}}}}}
            raise AssertionError(url)
        out = self.adapter(transport).fast_forward_preview_ref_cas(
            branch=BRANCH, expected_sha=BASE, candidate_sha=CANDIDATE,
        )
        self.assertEqual(out, CANDIDATE)
        mutation = calls[-1][2]
        self.assertIn("expectedOid:$expected", mutation["query"])
        self.assertIn("force:false", mutation["query"])
        self.assertEqual(mutation["variables"]["expected"], BASE)
        self.assertEqual(mutation["variables"]["target"], CANDIDATE)

    def test_atomic_cas_rejects_server_conflict_and_wrong_lease(self):
        for kind in ("remote_changed", "graphql_conflict", "wrong_output"):
            with self.subTest(kind=kind):
                def transport(method, url, headers, body):
                    if "/compare/" in url:
                        return 200, {"status": "ahead", "behind_by": 0, "ahead_by": 1}
                    if "/git/ref/" in url:
                        return 200, {"node_id": "REF_safe", "object": {
                            "sha": "c" * 40 if kind == "remote_changed" else BASE}}
                    if kind == "graphql_conflict":
                        return 200, {"errors": [{"message": "Reference was moved"}]}
                    return 200, {"data": {"updateRef": {"ref": {"target": {"oid": BASE}}}}}
                with self.assertRaises(RuntimeError):
                    self.adapter(transport).fast_forward_preview_ref_cas(
                        branch=BRANCH, expected_sha=BASE, candidate_sha=CANDIDATE)

    def test_cas_rejects_production_force_and_diverged_sha(self):
        adapter = self.adapter(lambda *_: (200, {}))
        for branch in ("main", "production", "refs/heads/main", "preview/../main"):
            with self.subTest(branch=branch):
                with self.assertRaises(ValueError):
                    adapter.fast_forward_preview_ref_cas(
                        branch=branch, expected_sha=BASE, candidate_sha=CANDIDATE)
        with self.assertRaises(ValueError):
            adapter.fast_forward_preview_ref_cas(
                branch=BRANCH, expected_sha=CANDIDATE, candidate_sha=CANDIDATE)


if __name__ == "__main__":
    unittest.main()
