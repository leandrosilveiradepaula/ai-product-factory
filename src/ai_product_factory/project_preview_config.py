from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectVercelPreviewConfig:
    mode: str
    team_id: str | None
    project_name: str | None
    github_org: str
    github_repo: str


def resolve_project_vercel_preview_config(*, repository: str, manifest: dict) -> ProjectVercelPreviewConfig:
    if "/" not in repository:
        raise ValueError("repository must be in owner/name form")
    owner,repo=repository.split("/",1)
    preview=manifest.get("preview") if isinstance(manifest,dict) else None
    preview=preview if isinstance(preview,dict) else {}
    provider=str(preview.get("provider") or "vercel").strip().lower()
    if provider != "vercel":
        raise ValueError(f"unsupported preview provider: {provider}")
    mode=str(preview.get("mode") or os.getenv("FACTORY_VERCEL_PREVIEW_MODE","api")).strip().lower()
    if mode not in {"api","github"}:
        raise ValueError(f"unsupported Vercel preview mode: {mode}")
    team_id=str(preview.get("team_id") or os.getenv("FACTORY_VERCEL_TEAM_ID","")).strip() or None
    project_name=str(preview.get("project_name") or os.getenv("FACTORY_VERCEL_PROJECT_NAME","")).strip() or None
    if mode=="api" and (not team_id or not project_name):
        raise ValueError("Vercel API preview mode requires team_id and project_name")
    return ProjectVercelPreviewConfig(mode=mode,team_id=team_id,project_name=project_name,github_org=owner,github_repo=repo)
