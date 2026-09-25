import json
import os
import unittest
from unittest.mock import patch

from ai_product_factory import cli
from ai_product_factory.model_executor import ModelResult, ModelRole


class FakeProvider:
    def execute_for_complexity(self, request, complexity, *, reasoning_effort=None):
        return ModelResult(
            role=ModelRole.PRIMARY,
            output="ok",
            provider_ref="resp_test",
            usage={"total_tokens": 7.0},
        )


class OpenAICommandTests(unittest.TestCase):
    def test_openai_execute_command(self):
        argv = [
            "ai-product-factory",
            "openai-execute",
            "--task-id", "t1",
            "--objective", "Do work",
            "--complexity", "low",
            "--reasoning-effort", "low",
        ]
        with patch("sys.argv", argv), patch.object(cli, "OpenAIResponsesProvider", return_value=FakeProvider()):
            with patch("builtins.print") as printer:
                code = cli.main()
        self.assertEqual(code, 0)
        payload = json.loads(printer.call_args.args[0])
        self.assertEqual(payload["role"], "primary")
        self.assertEqual(payload["provider_ref"], "resp_test")
        self.assertEqual(payload["usage"]["total_tokens"], 7.0)


if __name__ == "__main__":
    unittest.main()
