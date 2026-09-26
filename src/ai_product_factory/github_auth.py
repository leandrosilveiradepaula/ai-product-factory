from __future__ import annotations

import os


def resolve_github_token(repository: str, *, explicit_token: str | None = None) -> str:
    """Resolve a GitHub credential without assuming the Actions token is cross-repo."""
    if "/" not in repository:
        raise ValueError("repository must be in owner/name form")

    if explicit_token and explicit_token.strip():
        return explicit_token.strip()

    factory_token=os.getenv("FACTORY_GITHUB_TOKEN","").strip()
    if factory_token:
        return factory_token

    native=os.getenv("GITHUB_TOKEN","").strip()
    if not native:
        raise ValueError("GitHub credential is required")

    if os.getenv("GITHUB_ACTIONS","").strip().lower()=="true":
        current=os.getenv("GITHUB_REPOSITORY","").strip()
        if not current or current.lower()!=repository.lower():
            raise PermissionError(
                "repo-scoped GITHUB_TOKEN cannot access a different repository; configure FACTORY_GITHUB_TOKEN"
            )

    return native
