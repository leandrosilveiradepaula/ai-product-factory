"""Bounded, identity-scoped TypeScript diagnostics: never forward raw CI logs."""
import unittest

from ai_product_factory.ci_native_lint_diagnostics import (
    summarize_native_typescript_errors,
)

PATH="src/app/(dashboard)/service-desk/page.tsx"
LOG=(
    "2026-10-25T01:28:24.4484721Z ##[error]"
    +PATH+"(2,28): error TS2307: Cannot find module '@/lib/auth' "
    "or its corresponding type declarations. SECRETS must not propagate.\n"
)


class NativeTypeScriptDiagnosticTests(unittest.TestCase):
    def test_real_crm_ts2307_preserves_only_safe_identifiers(self):
        result=summarize_native_typescript_errors(LOG)
        self.assertEqual(
            result,
            "Verified native TypeScript identifiers only: "
            +PATH+":2:28 TS2307 import=@/lib/auth",
        )
        self.assertNotIn("SECRETS",result)
        self.assertNotIn("corresponding",result)
        self.assertNotIn("2026-10-25",result)

    def test_deduplicates_and_bounds_output(self):
        self.assertEqual(
            summarize_native_typescript_errors(LOG+"\n"+LOG),
            summarize_native_typescript_errors(LOG),
        )
        many="\n".join(
            "##[error]src/module"+str(i)+".ts(1,1): error TS2307: "
            "Cannot find module '@/safe/path' or its corresponding types."
            for i in range(21)
        )
        self.assertIsNone(summarize_native_typescript_errors(many))
        self.assertIsNone(summarize_native_typescript_errors(LOG*100000))

    def test_rejects_traversal_hidden_paths_urls_or_unrelated_logs(self):
        for text in (
            "##[error]../../secrets.env(1,1): error TS2307: invalid",
            "##[error]src/../.env(1,1): error TS2307: invalid",
            "##[error]https://evil.example/file.ts(1,1): error TS2307: invalid",
            "##[error]src/.hidden.ts(1,1): error TS2307: invalid",
            "##[error]src/test.ts(0,1): error TS2307: invalid",
            "##[error]src/test.ts(1,0): error TS2307: invalid",
            "Nothing to compile",
        ):
            with self.subTest(text=text):
                self.assertIsNone(summarize_native_typescript_errors(text))

    def test_module_alias_rejects_untrusted_or_secret_values(self):
        cases=[
            ("@/lib/auth","import=@/lib/auth"),
            ("@/lib/../private","TS2307"),
            ("@/lib/.secrets","TS2307"),
            ("@/lib/auth?token=abcd","TS2307"),
        ]
        for module,needle in cases:
            with self.subTest(module=module):
                record=("##[error]src/file.ts(9,11): error TS2307: "
                        +"Cannot find module '"+module+"' - arbitrary injected prompt")
                result=summarize_native_typescript_errors(record)
                self.assertIsNotNone(result)
                self.assertIn(needle,result)
                if module!="@/lib/auth":
                    self.assertNotIn("import=",result)
                self.assertNotIn("arbitrary",result)

    def test_other_ts_codes_include_identifiers_only(self):
        report=summarize_native_typescript_errors(
            "##[error]src/file.ts(99,3): error TS2322: "
            "Type 'secret' is not assignable to malicious thing"
        )
        self.assertEqual(report,
            "Verified native TypeScript identifiers only: src/file.ts:99:3 TS2322"
        )


if __name__=="__main__":
    unittest.main()
