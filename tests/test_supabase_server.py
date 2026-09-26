import unittest
from unittest.mock import patch

from ai_product_factory.supabase_server import resolve_supabase_server_config


class SupabaseServerConfigTests(unittest.TestCase):
    def test_prefers_modern_secret_key_and_omits_bearer(self):
        env={"SUPABASE_URL":"https://example.supabase.co","SUPABASE_SECRET_KEY":"sb_secret_modern","SUPABASE_SERVICE_ROLE_KEY":"legacy"}
        with patch.dict("os.environ",env,clear=True):
            cfg=resolve_supabase_server_config()
        self.assertEqual(cfg.key,"sb_secret_modern")
        self.assertEqual(cfg.headers,{"apikey":"sb_secret_modern"})

    def test_legacy_service_role_keeps_bearer(self):
        env={"SUPABASE_URL":"https://example.supabase.co","SUPABASE_SERVICE_ROLE_KEY":"legacy-jwt"}
        with patch.dict("os.environ",env,clear=True):
            cfg=resolve_supabase_server_config()
        self.assertEqual(cfg.headers["apikey"],"legacy-jwt")
        self.assertEqual(cfg.headers["Authorization"],"Bearer legacy-jwt")

    def test_missing_credentials_fail_closed(self):
        with patch.dict("os.environ",{},clear=True):
            with self.assertRaises(RuntimeError):
                resolve_supabase_server_config()


if __name__ == "__main__":
    unittest.main()
