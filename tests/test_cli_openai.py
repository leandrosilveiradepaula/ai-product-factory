import unittest

from ai_product_factory.cli import _build_parser


class OpenAICommandTests(unittest.TestCase):
    def test_cli_has_no_unmetered_openai_execute_command(self):
        parser = _build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args([
                "openai-execute",
                "--task-id", "t1",
                "--objective", "Do work",
            ])


if __name__ == "__main__":
    unittest.main()
