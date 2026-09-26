from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectVercelPreviewConfig:
    team_id: str
    project_name: str
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
    team_id=str(preview.get("team_id") or os.getenv("FACTORY_VERCEL_TEAM_ID","")).strip()
    project_name=str(preview.get("project_name") or os.getenv("FACTORY_VERCEL_PROJECT_NAME","")).strip()
    if not team_id or not project_name:
        raise ValueError("project preview configuration requires Vercel team_id and project_name")
    return ProjectVercelPreviewConfig(team_id=team_id,project_name=project_name,github_org=owner,github_repo=repo)
