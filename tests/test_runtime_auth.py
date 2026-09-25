import unittest

from ai_product_factory.runtime_auth import AuthKind, RuntimeAuthResolver


class RuntimeAuthResolverTests(unittest.TestCase):
    def test_no_credentials(self):
        auth = RuntimeAuthResolver({}).resolve()
        self.assertEqual(auth.kind, AuthKind.NONE)
        self.assertFalse(auth.configured)

    def test_api_key_is_supported(self):
        auth = RuntimeAuthResolver({"OPENAI_API_KEY": "secret"}).resolve()
        self.assertEqual(auth.kind, AuthKind.OPENAI_API_KEY)
        self.assertEqual(auth.source, "OPENAI_API_KEY")

    def test_chatgpt_token_precedes_api_key(self):
        auth = RuntimeAuthResolver({
            "CHATGPT_ACCESS_TOKEN": "secret-a",
            "OPENAI_API_KEY": "secret-b",
        }).resolve()
        self.assertEqual(auth.kind, AuthKind.CHATGPT_ACCESS_TOKEN)

    def test_workload_identity_has_highest_precedence(self):
        resolver = RuntimeAuthResolver({
            "OPENAI_WORKLOAD_IDENTITY_FILE": "/tmp/identity.json",
            "CHATGPT_ACCESS_TOKEN": "secret-a",
            "OPENAI_API_KEY": "secret-b",
        })
        self.assertEqual(resolver.resolve().kind, AuthKind.WORKLOAD_IDENTITY)
        self.assertEqual(
            resolver.available_kinds(),
            (
                AuthKind.WORKLOAD_IDENTITY,
                AuthKind.CHATGPT_ACCESS_TOKEN,
                AuthKind.OPENAI_API_KEY,
            ),
        )

    def test_secret_value_is_not_exposed(self):
        auth = RuntimeAuthResolver({"CHATGPT_ACCESS_TOKEN": "do-not-leak"}).resolve()
        self.assertNotIn("do-not-leak", repr(auth))


if __name__ == "__main__":
    unittest.main()
