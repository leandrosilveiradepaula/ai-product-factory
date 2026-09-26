from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Callable, Sequence

from .execution_worker import ImplementationArtifact
from .github_auth import resolve_github_token


RunCommand = Callable[..., subprocess.CompletedProcess[str]]
InvokeRecorder = Callable[[], None]

_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_FORBIDDEN_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "id_rsa",
    "id_ed25519",
}
_FORBIDDEN_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}


@dataclass(frozen=True)
class CodexCLIConfig:
    command: tuple[str, ...]
    timeout_seconds: int = 900
    max_files: int = 20
    max_bytes: int = 250_000

    @classmethod
    def from_env(cls) -> "CodexCLIConfig":
        raw = os.getenv("FACTORY_CODEX_COMMAND_JSON", "").strip()
        if raw:
            value = json.loads(raw)
            if not isinstance(value, list) or not value or not all(isinstance(x, str) and x for x in value):
                raise ValueError("FACTORY_CODEX_COMMAND_JSON must be a non-empty JSON string array")
            command = tuple(value)
        else:
            command = (
                "codex",
                "exec",
                "--sandbox",
                "workspace-write",
                "--ask-for-approval",
                "never",
                "-",
            )
        timeout = int(os.getenv("FACTORY_CODEX_TIMEOUT_SECONDS", "900"))
        max_files = int(os.getenv("FACTORY_CODEX_MAX_FILES", "20"))
        max_bytes = int(os.getenv("FACTORY_CODEX_MAX_BYTES", "250000"))
        if timeout < 1 or max_files < 1 or max_bytes < 1:
            raise ValueError("Codex execution limits must be positive")
        return cls(command=command, timeout_seconds=timeout, max_files=max_files, max_bytes=max_bytes)


class CodexCLIProducer:
    """Runs Codex in an isolated checkout and returns bounded full-file contents.

    GitHub credentials are used only by the parent process to clone the repository.
    They are deliberately removed before Codex starts.
    """

    def __init__(
        self,
        *,
        config: CodexCLIConfig | None = None,
        runner: RunCommand = subprocess.run,
        on_invoke: InvokeRecorder | None = None,
    ) -> None:
        self.config = config or CodexCLIConfig.from_env()
        self.runner = runner
        self.on_invoke = on_invoke or (lambda: None)

    def produce(self, item) -> ImplementationArtifact:
        self._require_wif()
        if not _REPOSITORY.fullmatch(item.repository):
            raise ValueError("repository must be in owner/name form")
        token = resolve_github_token(item.repository)
        with tempfile.TemporaryDirectory(prefix="factory-codex-") as tmp:
            root = pathlib.Path(tmp)
            checkout = root / "repo"
            askpass = root / "git-askpass.sh"
            askpass.write_text(
                "#!/bin/sh\n"
                "case \"$1\" in\n"
                "  *Username*) printf '%s\\n' 'x-access-token' ;;\n"
                "  *) printf '%s\\n' \"$FACTORY_GIT_TOKEN\" ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            askpass.chmod(0o700)
            clone_env = self._base_env()
            clone_env.update(
                {
                    "GIT_ASKPASS": str(askpass),
                    "GIT_TERMINAL_PROMPT": "0",
                    "FACTORY_GIT_TOKEN": token,
                }
            )
            clone = self.runner(
                [
                    "git",
                    "-c",
                    "core.hooksPath=/dev/null",
                    "clone",
                    "--depth",
                    "1",
                    "--branch",
                    "main",
                    f"https://github.com/{item.repository}.git",
                    str(checkout),
                ],
                env=clone_env,
                text=True,
                capture_output=True,
                timeout=120,
                check=False,
            )
            askpass.unlink(missing_ok=True)
            if clone.returncode != 0:
                raise RuntimeError("isolated repository checkout failed")

            self._git(checkout, "remote", "remove", "origin")
            prompt = self._prompt(item)
            self.on_invoke()
            result = self.runner(
                list(self.config.command),
                cwd=str(checkout),
                env=self._codex_env(),
                input=prompt,
                text=True,
                capture_output=True,
                timeout=self.config.timeout_seconds,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError("Codex CLI execution failed")

            files = self._collect_files(checkout)
            if not files:
                raise ValueError("Codex produced no repository changes")
            title = item.title.strip() or "Factory task"
            return ImplementationArtifact(
                plan_markdown=(
                    f"# Codex implementation plan\n\n"
                    f"Task: {title}\n\n"
                    "Implementation produced in an isolated checkout by the selective Codex worker. "
                    "GitHub delivery remains controlled by the Factory."
                ),
                files=files,
                commit_message=f"feat: {title[:72]}",
                pr_title=title[:120],
                pr_body=(
                    "Automated implementation produced by the selective Codex worker.\n\n"
                    "The Factory will validate CI and Preview, then stop at the human production merge gate."
                ),
            )

    def _require_wif(self) -> None:
        if os.getenv("FACTORY_CODEX_ENABLED", "").strip().lower() != "true":
            raise PermissionError("Codex execution is disabled")
        required = (
            "OPENAI_FEDERATION_RULE_ID",
            "OPENAI_WIF_AUDIENCE",
            "OPENAI_IDENTITY_TOKEN_FILE",
        )
        missing = [name for name in required if not os.getenv(name, "").strip()]
        if missing:
            raise PermissionError("Codex WIF configuration is incomplete: " + ", ".join(missing))
        token_file = pathlib.Path(os.environ["OPENAI_IDENTITY_TOKEN_FILE"])
        if not token_file.is_file():
            raise PermissionError("Codex identity token file does not exist")

    @staticmethod
    def _base_env() -> dict[str, str]:
        keep = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")
        return {key: os.environ[key] for key in keep if key in os.environ}

    def _codex_env(self) -> dict[str, str]:
        env = self._base_env()
        for key in (
            "OPENAI_FEDERATION_RULE_ID",
            "OPENAI_WIF_AUDIENCE",
            "OPENAI_IDENTITY_TOKEN_FILE",
            "OPENAI_WORKLOAD_IDENTITY_CONTEXT",
        ):
            value = os.getenv(key)
            if value:
                env[key] = value
        return env

    def _git(self, checkout: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str]:
        result = self.runner(
            ["git", *args],
            cwd=str(checkout),
            env=self._base_env(),
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("git inspection failed")
        return result

    def _collect_files(self, checkout: pathlib.Path) -> dict[str, str]:
        deleted = self._git(checkout, "diff", "HEAD", "--name-only", "--diff-filter=D").stdout.splitlines()
        if deleted:
            raise ValueError("Codex output cannot delete files")

        changed = self._git(
            checkout, "diff", "HEAD", "--name-only", "--diff-filter=ACMRTUXB"
        ).stdout.splitlines()
        untracked = self._git(
            checkout, "ls-files", "--others", "--exclude-standard"
        ).stdout.splitlines()

        paths = sorted({p.strip() for p in [*changed, *untracked] if p.strip()})
        if len(paths) > self.config.max_files:
            raise ValueError("Codex output exceeds FACTORY_CODEX_MAX_FILES")

        output: dict[str, str] = {}
        total = 0
        for relative in paths:
            self._validate_path(relative)
            path = checkout / relative
            if path.is_symlink() or not path.is_file():
                raise ValueError("Codex output must contain regular files only")
            data = path.read_bytes()
            total += len(data)
            if total > self.config.max_bytes:
                raise ValueError("Codex output exceeds FACTORY_CODEX_MAX_BYTES")
            try:
                output[relative] = data.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("Codex output contains a non-UTF-8 file") from exc
        return output

    @staticmethod
    def _validate_path(relative: str) -> None:
        path = pathlib.PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts or ".git" in path.parts:
            raise ValueError("unsafe Codex output path")
        lower_name = path.name.lower()
        if lower_name in _FORBIDDEN_NAMES or path.suffix.lower() in _FORBIDDEN_SUFFIXES:
            raise ValueError("Codex output contains a forbidden secret-bearing path")
        if any(part.lower() in {"credentials", "secrets"} for part in path.parts):
            raise ValueError("Codex output contains a forbidden secret-bearing path")

    @staticmethod
    def _prompt(item) -> str:
        return (
            "Implement the assigned repository task directly in the current checkout.\n"
            "Do not commit, push, open pull requests, change remotes, or access credentials.\n"
            "Do not create or modify .env, credential, private-key, or secret files.\n"
            "Do not run any benchmark unless the task explicitly requires it. "
            "The Agent SQL 63-question benchmark is explicitly forbidden as an implicit action.\n"
            "Keep the change narrowly scoped and run only relevant local deterministic tests.\n\n"
            f"Task title: {item.title}\n"
            f"Task description:\n{item.description}\n"
        )
