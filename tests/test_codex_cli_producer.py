import os
import pathlib
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ai_product_factory.codex_cli_producer import CodexCLIConfig, CodexCLIProducer


class CodexCLIProducerTests(unittest.TestCase):
    def test_codex_env_excludes_github_and_api_credentials(self):
        with tempfile.NamedTemporaryFile() as identity:
            env = {
                "PATH": os.environ.get("PATH", ""),
                "HOME": os.environ.get("HOME", ""),
                "FACTORY_CODEX_ENABLED": "true",
                "OPENAI_FEDERATION_RULE_ID": "rule",
                "OPENAI_IDENTITY_TOKEN_FILE": identity.name,
                "GITHUB_TOKEN": "github-secret",
                "FACTORY_GITHUB_TOKEN": "factory-secret",
                "OPENAI_API_KEY": "api-secret",
            }
            with patch.dict("os.environ", env, clear=True):
                producer = CodexCLIProducer(config=CodexCLIConfig(("codex", "exec")))
                child = producer._codex_env()
        self.assertNotIn("GITHUB_TOKEN", child)
        self.assertNotIn("FACTORY_GITHUB_TOKEN", child)
        self.assertNotIn("OPENAI_API_KEY", child)
        self.assertEqual(child["OPENAI_FEDERATION_RULE_ID"], "rule")

    def test_rejects_secret_bearing_output_paths(self):
        for path in (".env", "secrets/token.txt", "credentials/key.txt", "private.pem", "../escape.py"):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    CodexCLIProducer._validate_path(path)

    def test_full_producer_uses_isolated_checkout_and_returns_bounded_files(self):
        invoked = []
        real_run = subprocess.run

        def runner(command, **kwargs):
            if command[:2] == ["git", "-c"] and "clone" in command:
                checkout = pathlib.Path(command[-1])
                checkout.mkdir(parents=True)
                real_run(["git", "init", "-q"], cwd=checkout, check=True)
                real_run(["git", "config", "user.email", "factory@example.invalid"], cwd=checkout, check=True)
                real_run(["git", "config", "user.name", "Factory Test"], cwd=checkout, check=True)
                (checkout / "README.md").write_text("base\n", encoding="utf-8")
                real_run(["git", "add", "README.md"], cwd=checkout, check=True)
                real_run(["git", "commit", "-qm", "base"], cwd=checkout, check=True)
                real_run(["git", "remote", "add", "origin", "https://example.invalid/repo.git"], cwd=checkout, check=True)
                return subprocess.CompletedProcess(command, 0, "", "")
            if command and command[0] == "codex":
                checkout = pathlib.Path(kwargs["cwd"])
                (checkout / "src").mkdir()
                (checkout / "src" / "feature.py").write_text("VALUE = 1\n", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "done", "")
            return real_run(command, **kwargs)

        item = SimpleNamespace(
            repository="owner/repo",
            title="Implement feature",
            description="Add the feature safely.",
        )
        with tempfile.NamedTemporaryFile() as identity:
            env = {
                "PATH": os.environ.get("PATH", ""),
                "HOME": os.environ.get("HOME", ""),
                "FACTORY_CODEX_ENABLED": "true",
                "OPENAI_FEDERATION_RULE_ID": "rule",
                "OPENAI_IDENTITY_TOKEN_FILE": identity.name,
                "GITHUB_TOKEN": "managed-token",
            }
            with patch.dict("os.environ", env, clear=True):
                artifact = CodexCLIProducer(
                    config=CodexCLIConfig(("codex", "exec"), max_files=2, max_bytes=1000),
                    runner=runner,
                    on_invoke=lambda: invoked.append(True),
                ).produce(item)

        self.assertEqual(invoked, [True])
        self.assertEqual(artifact.files, {"src/feature.py": "VALUE = 1\n"})
        self.assertIn("Implement feature", artifact.pr_title)

    def test_default_command_is_workspace_bounded_and_noninteractive(self):
        with patch.dict("os.environ", {}, clear=True):
            config = CodexCLIConfig.from_env()
        self.assertIn("workspace-write", config.command)
        self.assertIn("--ask-for-approval", config.command)
        self.assertIn("never", config.command)
        self.assertNotIn("danger-full-access", config.command)


if __name__ == "__main__":
    unittest.main()
