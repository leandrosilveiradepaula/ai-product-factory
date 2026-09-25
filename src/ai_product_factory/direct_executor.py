from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from .autonomous_github import AutonomousGitHubLoop, GitHubWorkSession
from .control_plane import ControlPlaneStore


_BLOCKED_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    "id_rsa",
    "id_ed25519",
}
_BLOCKED_PARTS = {"..", ".git"}
_BLOCKED_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}


@dataclass(frozen=True)
class ChangeSet:
    files: dict[str, str]
    commit_message: str


@dataclass(frozen=True)
class DirectExecutionPolicy:
    max_files: int = 12
    max_total_bytes: int = 200_000


@dataclass(frozen=True)
class DirectExecutionResult:
    commit_sha: str
    file_count: int
    total_bytes: int


class DirectExecutor:
    """Applies bounded, auditable file changes without invoking Codex."""

    def __init__(
        self,
        github_loop: AutonomousGitHubLoop,
        store: ControlPlaneStore,
        *,
        policy: DirectExecutionPolicy | None = None,
    ) -> None:
        self.github_loop = github_loop
        self.store = store
        self.policy = policy or DirectExecutionPolicy()

    @staticmethod
    def _validate_path(path: str) -> None:
        p = PurePosixPath(path)
        if p.is_absolute():
            raise ValueError(f"absolute paths are forbidden: {path}")
        if any(part in _BLOCKED_PARTS for part in p.parts):
            raise ValueError(f"unsafe repository path: {path}")
        if p.name in _BLOCKED_NAMES:
            raise ValueError(f"secret-bearing file is forbidden: {path}")
        if p.suffix.lower() in _BLOCKED_SUFFIXES:
            raise ValueError(f"secret-bearing file extension is forbidden: {path}")

    def validate(self, changeset: ChangeSet) -> tuple[int, int]:
        if not changeset.files:
            raise ValueError("changeset cannot be empty")
        if not changeset.commit_message.strip():
            raise ValueError("commit_message is required")
        if len(changeset.files) > self.policy.max_files:
            raise ValueError(
                f"changeset exceeds max_files={self.policy.max_files}"
            )

        total_bytes = 0
        for path, content in changeset.files.items():
            self._validate_path(path)
            if not isinstance(content, str):
                raise TypeError(f"file content must be text: {path}")
            total_bytes += len(content.encode("utf-8"))

        if total_bytes > self.policy.max_total_bytes:
            raise ValueError(
                f"changeset exceeds max_total_bytes={self.policy.max_total_bytes}"
            )
        return len(changeset.files), total_bytes

    def execute(
        self,
        session: GitHubWorkSession,
        changeset: ChangeSet,
    ) -> DirectExecutionResult:
        file_count, total_bytes = self.validate(changeset)
        sha = self.github_loop.commit_implementation(
            session,
            files=changeset.files,
            message=changeset.commit_message,
        )
        self.store.record_tool_usage(
            run_id=session.run_id,
            tool_family="direct_executor",
            operation="apply_changeset",
            metadata={
                "commit": sha,
                "file_count": file_count,
                "total_bytes": total_bytes,
            },
        )
        return DirectExecutionResult(
            commit_sha=sha,
            file_count=file_count,
            total_bytes=total_bytes,
        )
