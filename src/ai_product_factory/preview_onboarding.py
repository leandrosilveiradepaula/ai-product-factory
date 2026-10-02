from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class PreviewPolicyDetection:
    policy: dict | None
    evidence: dict
    reason: str


def _has_explicit_preview_policy(manifest: dict) -> bool:
    preview=manifest.get("preview")
    if not isinstance(preview,dict):
        return False
    return any(key in preview for key in ("required","provider","mode","required_paths"))


def _is_vercel_target(value: object) -> bool:
    raw=str(value or "").strip()
    if not raw:
        return False
    try:
        host=(urlparse(raw).hostname or "").lower()
    except ValueError:
        return False
    return host=="vercel.com" or host.endswith(".vercel.com")


def detect_github_vercel_preview_policy(
    *,
    manifest: dict,
    default_branch: str,
    commit_sha: str,
    statuses: list[dict],
    checks: list[dict],
) -> PreviewPolicyDetection:
    """Infer only the safe positive case: a GitHub repository is integrated with Vercel.

    Existing explicit policy always wins. Absence of evidence never becomes
    preview-not-required; callers must remain fail-closed.
    """
    if _has_explicit_preview_policy(manifest):
        preview=manifest.get("preview")
        return PreviewPolicyDetection(
            policy=None,
            evidence={"source":"existing_manifest","preview":preview},
            reason="existing_policy_preserved",
        )

    signals:list[dict]=[]
    for row in statuses:
        context=str(row.get("context") or "")
        if "vercel" not in context.lower() or not _is_vercel_target(row.get("target_url")):
            continue
        signals.append({
            "kind":"commit_status",
            "context":context,
            "state":str(row.get("state") or ""),
            "id":row.get("id"),
        })

    for row in checks:
        app=row.get("app") or {}
        if str(app.get("slug") or "").lower()!="vercel":
            continue
        signals.append({
            "kind":"check_run",
            "name":str(row.get("name") or ""),
            "status":str(row.get("status") or ""),
            "conclusion":row.get("conclusion"),
            "id":row.get("id"),
        })

    if not signals:
        return PreviewPolicyDetection(
            policy=None,
            evidence={
                "source":"github_read_probe",
                "default_branch":default_branch,
                "commit_sha":commit_sha,
            },
            reason="no_vercel_integration_evidence",
        )

    evidence={
        "source":"github_vercel_integration",
        "default_branch":default_branch,
        "commit_sha":commit_sha,
        "signals":signals,
    }
    return PreviewPolicyDetection(
        policy={
            "provider":"vercel",
            "mode":"github",
            "required":True,
        },
        evidence=evidence,
        reason="vercel_github_integration_verified",
    )
