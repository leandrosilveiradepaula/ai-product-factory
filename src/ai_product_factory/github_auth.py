from __future__ import annotations

import os

from .github_app_runtime import resolve_github_app_installation_token


def resolve_github_token(repository: str, *, explicit_token: str | None = None) -> str:
    """Resolve a GitHub credential without assuming the Actions token is cross-repo."""
    if "/" not in repository:
        raise ValueError("repository must be in owner/name form")

    if explicit_token and explicit_token.strip():
        return explicit_token.strip()

    native=os.getenv("GITHUB_TOKEN","").strip()
    factory_token=os.getenv("FACTORY_GITHUB_TOKEN","").strip()

    if os.getenv("GITHUB_ACTIONS","").strip().lower()=="true":
        current=os.getenv("GITHUB_REPOSITORY","").strip()
        if current and current.lower()==repository.lower():
            if native:
                return native
            raise ValueError("repo-scoped GITHUB_TOKEN is required for the current Actions repository")
        app_token = resolve_github_app_installation_token(repository)
        if app_token:
            return app_token
        if factory_token:
            return factory_token
        raise PermissionError(
            "repo-scoped GITHUB_TOKEN cannot access a different repository; install/verify the Factory GitHub App or configure FACTORY_GITHUB_TOKEN"
        )

    if factory_token:
        return factory_token
    if native:
        return native
    raise ValueError("GitHub credential is required")
