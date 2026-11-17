"""Cross-repo B4 GitHub provenance is explicit, narrow, read-only and fail-closed."""
import unittest

from ai_product_factory.cross_repo_b4_read import cross_repo_b4_reader
from ai_product_factory.bounded_github_evidence_read import GitHubEvidenceTransportBlocked

FACTORY = "leandrosilveiradepaula/ai-product-factory"
STUDIO = "leandrosilveiradepaula/dark-channel-studio"
A, B = "a" * 40, "b" * 40
COMPARE = "/repos/" + STUDIO + "/compare/" + A + "..." + B


class CrossRepoB4ReadTests(unittest.TestCase):
    def test_exact_target_compare_uses_only_target_credential(self):
        calls = []
        def resolve(repo):
            calls.append(("resolve", repo))
            return "fake-target-credential"
        def read(token, path):
            calls.append(("get", token, path))
            return {"status": "ahead", "behind_by": 0, "ahead_by": 2}
        get = cross_repo_b4_reader(factory_repository=FACTORY,
                                    github_read=read, token_resolver=resolve)
        self.assertEqual(get(COMPARE)["status"], "ahead")
        self.assertEqual(calls, [
            ("resolve", STUDIO),
            ("get", "fake-target-credential", COMPARE),
        ])

    def test_denies_non_compare_and_current_factory_without_token_resolution(self):
        calls = []
        def resolve(repo):
            calls.append(repo)
            return "fake-token"
        get = cross_repo_b4_reader(factory_repository=FACTORY,
                                    github_read=lambda *_: self.fail("not allowed"),
                                    token_resolver=resolve)
        for path in (
            "/repos/" + FACTORY + "/compare/" + A + "..." + B,
            "/repos/" + STUDIO + "/pulls/2",
            "/repos/" + STUDIO + "/compare/main...main",
            "/repos/" + STUDIO + "/compare/" + A + "..." + B + "?unsafe=1",
            "/repos/" + STUDIO + "/compare/" + A + "..." + B + "/files",
            "/repos/" + STUDIO + "/issues/1/comments",
            "/repos/" + STUDIO + "/git/trees/" + A,
            "/repos/" + STUDIO + "/compare/" + A + "..." + B + "\nAuthorization: evil",
            "",
            None,
        ):
            with self.subTest(path=repr(path)):
                with self.assertRaises((PermissionError, GitHubEvidenceTransportBlocked)):
                    get(path)
        self.assertEqual(calls, [])

    def test_missing_credential_denies_with_no_native_actions_token_fallback(self):
        def fail_closed(repo):
            self.assertEqual(repo, STUDIO)
            raise PermissionError("crossrepo missing")
        get = cross_repo_b4_reader(factory_repository=FACTORY,
                                    github_read=lambda *_: self.fail("network called"),
                                    token_resolver=fail_closed)
        with self.assertRaises(PermissionError):
            get(COMPARE)

    def test_empty_or_invalid_token_and_factory_scope_deny(self):
        for bad in ("", " ", None):
            get = cross_repo_b4_reader(factory_repository=FACTORY,
                                        github_read=lambda *_: self.fail("network called"),
                                        token_resolver=lambda _repo, value=bad: value)
            with self.assertRaises(PermissionError):
                get(COMPARE)
        with self.assertRaises(ValueError):
            cross_repo_b4_reader(factory_repository="invalid",
                                 github_read=lambda *_: {},token_resolver=lambda _: "x")

if __name__ == "__main__":
    unittest.main()
