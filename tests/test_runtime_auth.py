import unittest
from ai_product_factory.runtime_auth import AuthKind,RuntimeAuthResolver

class Tests(unittest.TestCase):
 def test_api_key(self):
  self.assertEqual(RuntimeAuthResolver({"OPENAI_API_KEY":"x"}).resolve_primary_api().kind,AuthKind.OPENAI_API_KEY)

 def test_api_wif_requires_official_github_wif_variables(self):
  incomplete=RuntimeAuthResolver({"OPENAI_IDENTITY_PROVIDER_ID":"p","OPENAI_API_KEY":"fallback"}).resolve_primary_api()
  self.assertEqual(incomplete.kind,AuthKind.NONE)
  self.assertFalse(incomplete.configured)
  self.assertIn("incomplete",incomplete.source)
  self.assertEqual(RuntimeAuthResolver({"OPENAI_IDENTITY_PROVIDER_ID":"p","OPENAI_SERVICE_ACCOUNT_ID":"s","OPENAI_WIF_AUDIENCE":"aud"}).resolve_primary_api().kind,AuthKind.OPENAI_API_WIF)


 def test_explicit_api_key_mode_ignores_complete_wif(self):
  r=RuntimeAuthResolver({
   "FACTORY_PRIMARY_AUTH_MODE":"api_key",
   "OPENAI_API_KEY":"key",
   "OPENAI_IDENTITY_PROVIDER_ID":"p",
   "OPENAI_SERVICE_ACCOUNT_ID":"s",
   "OPENAI_WIF_AUDIENCE":"aud",
  })
  self.assertEqual(r.resolve_primary_api().kind,AuthKind.OPENAI_API_KEY)

 def test_explicit_wif_mode_never_falls_back_to_api_key(self):
  r=RuntimeAuthResolver({
   "FACTORY_PRIMARY_AUTH_MODE":"wif",
   "OPENAI_API_KEY":"key",
   "OPENAI_IDENTITY_PROVIDER_ID":"p",
  })
  auth=r.resolve_primary_api()
  self.assertEqual(auth.kind,AuthKind.NONE)
  self.assertFalse(auth.configured)

 def test_invalid_primary_auth_mode_fails_closed(self):
  auth=RuntimeAuthResolver({"FACTORY_PRIMARY_AUTH_MODE":"magic","OPENAI_API_KEY":"key"}).resolve_primary_api()
  self.assertEqual(auth.kind,AuthKind.NONE)
  self.assertFalse(auth.configured)

 def test_codex_wif_requires_both_official_variables(self):
  incomplete=RuntimeAuthResolver({"OPENAI_FEDERATION_RULE_ID":"idpm_x","CODEX_ACCESS_TOKEN":"fallback"}).resolve_codex()
  self.assertEqual(incomplete.kind,AuthKind.NONE)
  self.assertFalse(incomplete.configured)
  self.assertIn("incomplete",incomplete.source)
  r=RuntimeAuthResolver({"OPENAI_FEDERATION_RULE_ID":"idpm_x","OPENAI_IDENTITY_TOKEN_FILE":"/run/openai/identity-token"})
  self.assertEqual(r.resolve_codex().kind,AuthKind.CODEX_WORKLOAD_IDENTITY)

 def test_codex_access_token_is_official_fallback_when_wif_absent(self):
  r=RuntimeAuthResolver({"CODEX_ACCESS_TOKEN":"token"})
  self.assertEqual(r.resolve_codex().kind,AuthKind.CODEX_ACCESS_TOKEN)
  self.assertTrue(r.resolve_codex().configured)

 def test_unofficial_chatgpt_token_is_not_accepted(self):
  self.assertEqual(RuntimeAuthResolver({"CHATGPT_ACCESS_TOKEN":"x"}).resolve().kind,AuthKind.NONE)

 def test_secret_not_exposed(self):
  self.assertNotIn("secret",repr(RuntimeAuthResolver({"OPENAI_API_KEY":"secret"}).resolve()))

if __name__=="__main__":unittest.main()
