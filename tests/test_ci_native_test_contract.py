"""Prove bounded real Vitest count mismatch from test/source at same SHA."""
from __future__ import annotations

import unittest
from unittest.mock import Mock

from ai_product_factory.ci_native_test_contract import (
    verify_native_vitest_static_count,
)

SHA="a"*40
TEST="src/lib/sidebar-navigation-contract.test.ts"
SOURCE="src/components/layout/Sidebar.tsx"
TEST_CONTENT=(
    "import { readFileSync } from 'node:fs';\n"
    "import { describe, it, expect } from 'vitest';\n"
    "const sidebar = readFileSync('src/components/layout/Sidebar.tsx', 'utf8');\n"
    "describe('navigation', () => {\n"
    "    it('does something', () => {\n"
    "       expect(true).toBe(true)\n"
    "    });\n"
    "    it('closes mobile menu', () => {\n"
    "       const item = sidebar;\n"
    "       expect((sidebar.match(/onNavigate=\\{closeMobileMenu\\}/g) ?? []).length).toBe(16);\n"
    "    });\n"
    "});\n"
).replace("\\\\","\\")
SOURCE_CONTENT="<NavItem onNavigate={closeMobileMenu} />\n"*17
LOG=(
    "2026-10-25T02:57:16Z \x1b[31mAssertionError\x1b[0m: "
    "expected 17 to be 16 // Object.is equality\n"
    "2026-10-25T02:57:16Z \x1b[2m❯\x1b[0m "+TEST+":10:81\n"
)


def adapter(files=None):
    docs=files if files is not None else {TEST:TEST_CONTENT,SOURCE:SOURCE_CONTENT}
    gh=Mock()
    def get(path,*,ref):
        if ref!=SHA or path not in docs:
            raise RuntimeError("wrong SHA or file missing")
        return docs[path]
    gh.get_file_text.side_effect=get
    return gh


class VerifiedVitestCountTests(unittest.TestCase):
    def attest(self,log=LOG,files=None):
        return verify_native_vitest_static_count(
            log,github=adapter(files),candidate_sha=SHA,
        )

    def test_exact_candidate_real_contract_addition_is_attested(self):
        result=self.attest()
        self.assertIsNotNone(result)
        self.assertEqual(result.test_path,TEST)
        self.assertEqual(result.source_path,SOURCE)
        self.assertEqual((result.expected,result.actual),(16,17))
        self.assertEqual(result.as_summary(),
            "Verified native Vitest count: test="+TEST+" source="+SOURCE+
            " expected=16 actual=17")

    def test_full_vitest_job_ignores_unrelated_passing_test_paths(self):
        # Real native Vitest jobs list many passing files and can print
        # path:line:column diagnostics unrelated to the *failed* assertion.
        passing = "".join(
            f"2026-10-25T02:57:11Z ✓ src/lib/unrelated_{i}.test.ts:4:9\n"
            for i in range(90)
        )
        mirrored = (
            "2026-10-25T02:57:16Z \x1b[31mAssertionError\x1b[22m: "
            "expected 17 to be 16 // Object.is equality\n"
            "2026-10-25T02:57:16Z - Expected\n"
            "2026-10-25T02:57:16Z + 17\n"
            "2026-10-25T02:57:16Z \x1b[2m❯\x1b[22m "
            + TEST + ":\x1b[2m10:81\x1b[22m\n"
        )
        got = self.attest(passing + LOG + passing + mirrored + passing)
        self.assertIsNotNone(got)
        self.assertEqual((got.expected, got.actual), (16, 17))
        self.assertEqual(got.test_path, TEST)

    def test_bounded_failure_stacks_must_agree_and_be_present(self):
        for noisy in (
            LOG.replace("❯", "->"),
            LOG + "❯ src/lib/other.test.ts:10:81\n",
            LOG + "AssertionError: expected 17 to be 16 // Object.is equality\n"
                  "❯ src/lib/another.test.ts:10:81\n",
            LOG + "AssertionError: expected 19 to be 16 // Object.is equality\n"
                  "❯ " + TEST + ":10:81\n",
        ):
            with self.subTest(log=noisy[-100:]):
                self.assertIsNone(self.attest(noisy))

    def test_unrelated_log_or_multiple_assertions_never_authors_scope(self):
        for log in (
            "",
            "unknown CI failure",
            LOG+"AssertionError: expected 5 to be 4 // Object.is equality\n",
            LOG+"❯ src/lib/other.test.ts:10:81\n",
            LOG.replace(TEST,"src/lib/unrelated.test.ts"),
            LOG.replace(":10:81",":11:81"),
            LOG.replace("expected 17","expected 18"),
        ):
            with self.subTest(log=log[:65]):
                self.assertIsNone(self.attest(log))

    def test_conflicting_test_or_source_bytes_do_not_authorize_scope(self):
        docs={TEST:TEST_CONTENT,SOURCE:SOURCE_CONTENT}
        variations=[
            {TEST:"no import or expectation"},
            {SOURCE:"<NavItem onNavigate={closeMobileMenu} />"},
            {TEST:TEST_CONTENT.replace("toBe(16)","toBe(15)")},
            {TEST:TEST_CONTENT.replace("onNavigate", "onOther")},
            {TEST:TEST_CONTENT.replace("src/components/layout/Sidebar.tsx",
                                       "src/components/layout/Other.tsx")},
            {SOURCE:"sb_secret_superSensitiveValue"+SOURCE_CONTENT},
            {TEST:TEST_CONTENT+"x"*40000},
        ]
        for change in variations:
            with self.subTest(paths=tuple(change)):
                self.assertIsNone(self.attest(files={**docs,**change}))

    def test_noncrm_pattern_is_generic(self):
        test="test/navbar.spec.ts"
        source="src/components/Nav.tsx"
        sample=TEST_CONTENT.replace(TEST, test).replace(
            "src/components/layout/Sidebar.tsx",source
        ).replace("sidebar", "navbar").replace(
            "onNavigate=\\{closeMobileMenu\\}","onClick=\\{closeModal\\}"
        )
        count="<Link onClick={closeModal} />\n"*17
        log=LOG.replace(TEST,test)
        got=self.attest(log,files={test:sample,source:count})
        self.assertIsNotNone(got)
        self.assertEqual(got.source_path,source)

    def test_bad_sha_input_and_oversized_log_fail_closed(self):
        self.assertIsNone(verify_native_vitest_static_count(
            LOG,github=adapter(),candidate_sha="not_sha"))
        self.assertIsNone(self.attest(LOG*15000))


if __name__=="__main__":
    unittest.main()
