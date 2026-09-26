from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch


@dataclass(frozen=True)
class PreviewApplicability:
    required: bool
    reason: str
    matched_paths: tuple[str, ...] = ()


def evaluate_preview_applicability(*, manifest: dict, changed_files: tuple[str, ...]) -> PreviewApplicability:
    preview=manifest.get("preview") if isinstance(manifest,dict) else None
    if not isinstance(preview,dict):
        return PreviewApplicability(True,"no explicit preview policy; fail closed")

    if preview.get("required") is False:
        reason=str(preview.get("reason") or "project policy explicitly marks Preview not applicable")
        return PreviewApplicability(False,reason)

    paths=preview.get("required_paths")
    if paths is not None:
        if not isinstance(paths,list) or not all(isinstance(x,str) and x.strip() for x in paths):
            raise ValueError("preview.required_paths must be a list of non-empty glob strings")
        patterns=tuple(x.strip() for x in paths)
        matched=tuple(path for path in changed_files if any(fnmatch(path,pattern) for pattern in patterns))
        if not matched:
            return PreviewApplicability(False,"no changed file matches preview.required_paths")
        return PreviewApplicability(True,"changed files match preview.required_paths",matched)

    return PreviewApplicability(True,"preview required by project policy")
