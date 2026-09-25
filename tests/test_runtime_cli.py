import unittest
from unittest.mock import patch

from ai_product_factory.product_stage_executor import ProductStageExecutor
from ai_product_factory.runtime_auth import AuthKind
from ai_product_factory.runtime_cli import build_handler


class RuntimeCliTests(unittest.TestCase):
    def test_runtime_builds_primary_handler_for_api_key(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test"}, clear=True):
            handler = build_handler()
        self.assertIsInstance(handler, ProductStageExecutor)

    def test_runtime_fails_before_claim_when_auth_is_missing(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                build_handler()
        self.assertIn(AuthKind.NONE.value, str(ctx.exception))

    def test_unimplemented_chatgpt_token_does_not_silently_fall_back(self):
        with patch.dict("os.environ", {"CHATGPT_ACCESS_TOKEN": "x"}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                build_handler()
        self.assertIn(AuthKind.CHATGPT_ACCESS_TOKEN.value, str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
