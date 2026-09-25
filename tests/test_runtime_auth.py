import unittest
from ai_product_factory.runtime_auth import AuthKind,RuntimeAuthResolver
class Tests(unittest.TestCase):
 def test_api_key(self):self.assertEqual(RuntimeAuthResolver({"OPENAI_API_KEY":"x"}).resolve_primary_api().kind,AuthKind.OPENAI_API_KEY)
 def test_api_wif_requires_provider_and_service_account(self):
  self.assertEqual(RuntimeAuthResolver({"OPENAI_API_WIF_PROVIDER_ID":"p"}).resolve_primary_api().kind,AuthKind.NONE)
  self.assertEqual(RuntimeAuthResolver({"OPENAI_API_WIF_PROVIDER_ID":"p","OPENAI_API_WIF_SERVICE_ACCOUNT_ID":"s"}).resolve_primary_api().kind,AuthKind.OPENAI_API_WIF)
 def test_codex_wif_is_separate(self):
  r=RuntimeAuthResolver({"CODEX_WORKLOAD_IDENTITY_RULE_ID":"r","CODEX_WORKLOAD_IDENTITY_TOKEN_FILE":"/tmp/oidc"})
  self.assertEqual(r.resolve_primary_api().kind,AuthKind.NONE);self.assertEqual(r.resolve_codex().kind,AuthKind.CODEX_WORKLOAD_IDENTITY)
 def test_unofficial_chatgpt_token_is_not_accepted(self):
  self.assertEqual(RuntimeAuthResolver({"CHATGPT_ACCESS_TOKEN":"x"}).resolve().kind,AuthKind.NONE)
 def test_secret_not_exposed(self):
  self.assertNotIn("secret",repr(RuntimeAuthResolver({"OPENAI_API_KEY":"secret"}).resolve()))
if __name__=="__main__":unittest.main()
