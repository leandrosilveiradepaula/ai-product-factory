"""Negative and positive source-integrity tests for the exact-SHA Vercel fallback."""
import copy
import unittest

from ai_product_factory.verified_vercel_bot_preview import (
    VercelPreviewWitnessBlocked, resolve_verified_vercel_bot_preview,
)

REPO = "example/studio"
SHA = "a" * 40
INSPECTOR = "https://vercel.com/example-team/studio/1234567890abcdefghijklmnop"
PREVIEW = "https://studio-git-feature-example-team.vercel.app"


def fixtures():
    pulls = [{
        "number": 2, "state": "open", "draft": False, "merged_at": None,
        "head": {"sha": SHA, "ref": "factory/change-set-12345678",
                 "repo": {"full_name": REPO}},
        "base": {"ref": "main"},
    }]
    statuses = [{"context": "Vercel", "state": "success", "target_url": INSPECTOR}]
    comments = [{
        "user": {"login": "vercel[bot]"},
        "performed_via_github_app": {"slug": "vercel"},
        "body": "| Project | Deployment | Actions | Updated |\n"
                "| studio | ![Ready](https://vercel.com/static/status/ready.svg) "
                "[Ready](" + INSPECTOR + ") | [Preview](" + PREVIEW + ") | Now |",
    }]
    return {"repository": REPO, "candidate_sha": SHA,
            "pulls": pulls, "statuses": statuses, "comments": comments}


class VerifiedVercelBotPreviewTests(unittest.TestCase):
    def test_exact_sha_status_and_authenticated_bot_same_deployment(self):
        self.assertEqual(resolve_verified_vercel_bot_preview(**fixtures()), PREVIEW)

    def test_missing_status_or_pending_bot_update_is_not_positive(self):
        p = fixtures()
        p["statuses"] = []
        self.assertIsNone(resolve_verified_vercel_bot_preview(**p))
        p = fixtures()
        p["comments"] = []
        self.assertIsNone(resolve_verified_vercel_bot_preview(**p))

    def test_rejects_drift_and_spoofing(self):
        cases = [
            lambda p: p["pulls"][0]["head"].update(sha="b" * 40),
            lambda p: p["pulls"][0]["head"].update(ref="main"),
            lambda p: p["pulls"][0]["head"]["repo"].update(full_name="evil/repo"),
            lambda p: p["pulls"][0].update(draft=True),
            lambda p: p["pulls"][0].update(merged_at="2026-11-17T00:00:00Z"),
            lambda p: p["statuses"].insert(0, {"context": "Vercel", "state": "failure"}),
            lambda p: p["statuses"][0].update(target_url="https://evil.example/deploy"),
            lambda p: p["comments"][0]["body"].replace("unused", "unused"),
        ]
        for mutation in cases[:-1]:
            with self.subTest(mutation=repr(mutation)):
                p = fixtures()
                mutation(p)
                with self.assertRaises(VercelPreviewWitnessBlocked):
                    resolve_verified_vercel_bot_preview(**p)

    def test_rejects_untrusted_bot_and_wrong_origin(self):
        for path, value in [
            (("comments", 0, "user", "login"), "vercel-helper"),
            (("comments", 0, "performed_via_github_app", "slug"), "attacker"),
        ]:
            p = fixtures()
            p["comments"][0][path[2]][path[3]] = value
            self.assertIsNone(resolve_verified_vercel_bot_preview(**p))
        p = fixtures()
        p["comments"][0]["body"] = p["comments"][0]["body"].replace(
            PREVIEW, "https://attacker-example-team.vercel.app")
        with self.assertRaises(VercelPreviewWitnessBlocked):
            resolve_verified_vercel_bot_preview(**p)

    def test_rejects_prior_sha_and_ambiguous_preview(self):
        p = fixtures()
        p["comments"][0]["body"] = p["comments"][0]["body"].replace(
            INSPECTOR, "https://vercel.com/example-team/studio/00000000000000000000")
        self.assertIsNone(resolve_verified_vercel_bot_preview(**p))
        p = fixtures()
        p["comments"][0]["body"] = p["comments"][0]["body"].replace(
            "[Preview](" + PREVIEW + ")", "[Preview](" + PREVIEW + ") "
            "[Preview](https://studio-other-example-team.vercel.app)")
        with self.assertRaises(VercelPreviewWitnessBlocked):
            resolve_verified_vercel_bot_preview(**p)

    def test_bounded_inputs_and_no_silent_downgrade(self):
        p = fixtures()
        p["pulls"] *= 2
        with self.assertRaises(VercelPreviewWitnessBlocked):
            resolve_verified_vercel_bot_preview(**p)
        p = fixtures()
        p["comments"][0]["body"] = "A" * 10001
        with self.assertRaises(VercelPreviewWitnessBlocked):
            resolve_verified_vercel_bot_preview(**p)

    def test_workflow_uses_provider_linked_fallback_without_bypassing_browser(self):
        from pathlib import Path
        text = (Path(__file__).resolve().parents[1]
                / ".github/workflows/cross-repo-preview-browser-evidence.yml").read_text()
        self.assertIn("resolve_verified_vercel_bot_preview", text)
        self.assertIn("commits/{sha}/pulls", text)
        self.assertIn("issues/{pulls[0]['number']}/comments", text)
        self.assertIn("Dispatch trusted Factory browser verifier and wait", text)
        self.assertIn("Persist cross-repo browser evidence in Control Plane", text)
        self.assertIn("Resume eligible failed Preview after real first-party browser proof", text)


if __name__ == "__main__":
    unittest.main()
