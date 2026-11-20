"""Strict read-only credential boundary for independent cross-repository B4 ancestry.

The current-repository GitHub Actions GITHUB_TOKEN cannot read a private target
repository. Only an explicitly resolved installation credential or
FACTORY_GITHUB_TOKEN can read the exact target SHA comparison; a failure
must leave the entire independent B4 criterion unverified.
"""
from __future__ import annotations

import json
import os
import re
from collections.abc import Callable

from .bounded_github_evidence_read import bounded_github_evidence_read
from .github_auth import resolve_github_token
from .github_app_runtime import _default_transport
from .supabase_server import resolve_supabase_server_config

TARGET_COMPARE = re.compile(
    r"/repos/(?P<repository>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/compare/"
    r"[0-9a-f]{40}\.\.\.[0-9a-f]{40}\Z"
)



def resolve_b4_cross_repo_token(repository: str) -> str:
    """Select explicitly delegated cross-repo reads on authenticated CI events.

    The GitHub App installation-token broker intentionally rejects workflow_run
    events. The post-validate certifier is a workflow_run and cannot ask that
    privileged broker for a token. Its repository secret already carries the
    explicitly authorized cross-repo credential. Use ONLY that credential in
    this context; never try the Actions token, App broker, or a guessed token.
    All other event types use the existing supported GitHub authorization path.
    """
    if (os.getenv("GITHUB_ACTIONS", "").strip().lower() == "true"
            and os.getenv("GITHUB_EVENT_NAME", "").strip() == "workflow_run"):
        # Never mint or return a private-repository token to the certifier.
        # All compare reads in this context must use the scoped OIDC broker.
        raise PermissionError("b4_certifier_direct_token_forbidden")
    return resolve_github_token(repository)



def _read_b4_immutable_compare_from_broker(path: str, *, transport=_default_transport):
    """Read only an already human-released App-bound SHA comparison.

    The OIDC broker never issues a token to workflow_run; it makes a scoped
    contents:read GitHub App request server-side and returns only filenames,
    status and commit counts. Reject missing OIDC or wrong broker without
    falling back to either repository credential.
    """
    match = TARGET_COMPARE.fullmatch(path)
    if match is None:
        raise PermissionError("b4_cross_repo_path_denied")
    try:
        cfg = resolve_supabase_server_config()
    except RuntimeError as exc:
        raise PermissionError("b4_explicit_cross_repo_broker_required") from None
    if (not cfg.url.endswith("/functions/v1/factory-runtime-control-plane")
            or cfg.key.startswith("sb_secret_")
            or cfg.key.count(".") != 2):
        raise PermissionError("b4_explicit_cross_repo_broker_required")
    repository = match.group("repository")
    suffix = path.split("/compare/", 1)[1]
    predecessor, current = suffix.split("...", 1)
    body = json.dumps({
        "repository": repository,
        "predecessor": predecessor,
        "current": current,
    }, separators=(",", ":")).encode("utf-8")
    status, result = transport(
        "POST", cfg.url + "/github-app/read-only-compare",
        {**cfg.headers, "Content-Type": "application/json"},
        body,
    )
    if status != 200:
        if status in (401, 403, 404):
            raise PermissionError("b4_cross_repo_access_denied")
        raise RuntimeError("b4_cross_repo_read_unavailable")
    if (not isinstance(result, dict)
            or result.get("status") != "ahead"
            or result.get("behind_by") != 0
            or not isinstance(result.get("files"), list)):
        raise RuntimeError("b4_cross_repo_read_unavailable")
    return result


def cross_repo_b4_reader(
    *, factory_repository: str,
    github_read: Callable[[str, str], object],
    token_resolver: Callable[[str], str] = resolve_b4_cross_repo_token,
) -> Callable[[str], object]:
    """Return a narrowly scoped, non-caching cross-repo GitHub compare reader.

    No arbitrary repository URL, file, token, release, PR, mutating endpoint,
    or current-Factory endpoint can be requested with the cross-repo token.
    Credential absence fails closed; no fallback to Actions GITHUB_TOKEN.
    """
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", factory_repository):
        raise ValueError("b4_factory_repository_invalid")
    if not callable(github_read) or not callable(token_resolver):
        raise TypeError("b4_cross_repo_reader_invalid")

    def read(path: str) -> object:
        match = TARGET_COMPARE.fullmatch(path) if isinstance(path, str) else None
        if not match:
            raise PermissionError("b4_cross_repo_path_denied")
        target = match.group("repository")
        if target.lower() == factory_repository.lower():
            raise PermissionError("b4_same_repo_cross_token_denied")
        if (os.getenv("GITHUB_ACTIONS", "").strip().lower() == "true"
                and os.getenv("GITHUB_EVENT_NAME", "").strip() == "workflow_run"):
            # Never call the App token-mint endpoint, never send a privileged
            # installation token to the certifier and never fall back to PAT.
            return _read_b4_immutable_compare_from_broker(path)
        token = token_resolver(target)
        if not isinstance(token, str) or not token.strip():
            raise PermissionError("b4_explicit_cross_repo_credential_required")
        return github_read(token, path)

    return bounded_github_evidence_read(read)
