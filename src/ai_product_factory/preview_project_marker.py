"""Authenticate the application's expected text against the project's persisted identity.

The caller-provided marker can never be a Vercel login/SSO heading that merely
happens to render. A project administrator can explicitly configure an alternate
first-party marker in the privileged Control Plane Preview policy.
"""
from __future__ import annotations


class ProjectMarkerBlocked(ValueError):
    pass


def require_exact_project_marker(rows: object, repository: str, expected_text: str) -> str:
    if (not isinstance(rows, list) or len(rows) != 1
        or not isinstance(rows[0], dict)
        or rows[0].get("repository") != repository
        or rows[0].get("is_active") is not True):
        raise ProjectMarkerBlocked("project_marker_identity_not_unique")
    project = rows[0]
    manifest = project.get("manifest")
    preview = manifest.get("preview") if isinstance(manifest, dict) else None
    if not isinstance(preview, dict) or preview.get("required") is not True:
        raise ProjectMarkerBlocked("project_preview_policy_unverified")
    marker = preview.get("expected_text")
    if marker is None:
        marker = project.get("name")
    if (not isinstance(marker, str) or type(marker) is not str
        or not 1 <= len(marker.strip()) <= 120
        or "\n" in marker or "\r" in marker):
        raise ProjectMarkerBlocked("project_preview_marker_invalid")
    if (type(expected_text) is not str
        or expected_text.strip() != marker.strip()):
        raise ProjectMarkerBlocked("requested_marker_not_project_identity")
    return marker.strip()
