"""Locate existing exports for failed native TypeScript import repairs.

Never use a model guess, search result, issue comment, or a new write scope as
a substitute for an exported symbol verified at the exact candidate Git SHA.
Only an unambiguous read-only module may enter the context packet.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from .work_unit_context import redact_repository_text

_SHA=re.compile(r"[a-f0-9]{40}\Z")
_TS2307=re.compile(
    r"(?P<file>(?:src|app|apps|packages)/[A-Za-z0-9_.()/\[\]-]+)"
    r":(?P<line>[1-9][0-9]{0,5}):(?P<column>[1-9][0-9]{0,5})"
    r" TS2307 import=(?P<alias>@/[A-Za-z0-9_./-]{1,150})\Z"
)
_IMPORT=re.compile(
    r"""^\s*import\s*\{\s*(?P<symbol>[a-zA-Z_$][a-zA-Z0-9_$]*)\s*\}"""
    r"""\s*from\s*['"](?P<alias>@/[A-Za-z0-9_./-]{1,150})['"]\s*;?\s*$"""
)
_SKIP={"get","set","use","fetch","read","load","make","find","from","with","async"}
_EXTENSIONS=(".ts",".tsx",".js",".jsx")
_ROOTS=("src/","app/","apps/","packages/")


@dataclass(frozen=True)
class VerifiedReadonlyImport:
    source_file: str
    symbol: str
    exported_from: str


def _text(github: object, path: str, sha: str) -> str:
    value=github.get_file_text(path,ref=sha)
    if not isinstance(value,str) or len(value.encode("utf-8"))>16384:
        raise PermissionError("CI repair candidate module context exceeds safe byte limit")
    if redact_repository_text(value)!=value:
        raise PermissionError("CI repair candidate module context contains redacted material")
    return value


def _candidate_tokens(symbol: str) -> tuple[str,...]:
    words=re.findall(r"[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+|[0-9]+",symbol)
    return tuple(dict.fromkeys(
        word.lower() for word in words
        if len(word)>=4 and word.lower() not in _SKIP
    ))


def resolve_verified_readonly_imports(
    *, github: object, source: dict, base_commit: str, all_paths: tuple[str,...],
) -> tuple[VerifiedReadonlyImport,...]:
    repair=source.get("repair")
    if not isinstance(repair,dict) or repair.get("repair_kind")!="ci":
        return ()
    diagnostics=repair.get("verified_typecheck_diagnostics")
    if not isinstance(diagnostics,list) or not diagnostics:
        return ()
    if len(diagnostics)>4 or not _SHA.fullmatch(base_commit):
        raise PermissionError("unbounded or invalid CI repair import diagnostics")
    assignment=source.get("assignment")
    scopes=assignment.get("scope_keys") if isinstance(assignment,dict) else None
    if not isinstance(scopes,list) or not scopes:
        raise PermissionError("CI repair has no explicit write scope")
    files=set(all_paths)
    resolved=[]
    for diagnostic in diagnostics:
        if not isinstance(diagnostic,str):
            raise PermissionError("invalid CI repair TypeScript diagnostic")
        match=_TS2307.fullmatch(diagnostic)
        if match is None:
            # TS codes unrelated to import resolution do not request modules.
            if " TS2307 " in diagnostic:
                raise PermissionError("CI repair module import has no exact diagnostic")
            continue
        source_file,alias=match.group("file"),match.group("alias")
        if (source_file not in files or source_file not in scopes
            or any(part in ("", ".", "..") or part.startswith(".")
                   for part in source_file.split("/"))
            or "//" in alias or ".." in alias
            or any(part.startswith(".") for part in alias[2:].split("/"))):
            raise PermissionError("CI repair import source is not an exact scoped file")
        content=_text(github,source_file,base_commit)
        line=int(match.group("line"))
        split=content.splitlines()
        if line>len(split):
            raise PermissionError("CI repair import diagnostic line differs from pinned file")
        parsed=_IMPORT.fullmatch(split[line-1])
        if parsed is None or parsed.group("alias")!=alias:
            raise PermissionError("CI repair import alias differs from pinned file")
        symbol=parsed.group("symbol")
        tokens=_candidate_tokens(symbol)
        if not tokens:
            raise PermissionError("CI repair import symbol cannot be resolved safely")
        candidates=[]
        for path in all_paths:
            if (path==source_file or path in scopes
                or not path.startswith(_ROOTS)
                or not path.endswith(_EXTENSIONS)
                or path.endswith((".test.ts",".spec.ts",".test.tsx",".spec.tsx"))
                or any(part.startswith(".") or part in ("node_modules","dist","build","generated")
                       for part in path.split("/"))):
                continue
            stem=path.rsplit("/",1)[-1].split(".",1)[0].lower()
            if stem in tokens or any(stem.endswith(token) for token in tokens):
                candidates.append(path)
                if len(candidates)>16:
                    raise PermissionError("CI repair import source candidates exceed safe limit")
        matches=[]
        for path in candidates:
            module=_text(github,path,base_commit)
            exported=re.search(
                rf"(?m)^\s*export\s+(?:declare\s+)?(?:async\s+)?"
                rf"(?:function|const|let|class)\s+{re.escape(symbol)}\b",
                module,
            )
            if exported:
                matches.append(path)
        if len(matches)!=1:
            raise PermissionError("CI repair import has no unique verified exported module")
        resolved.append(VerifiedReadonlyImport(
            source_file=source_file,symbol=symbol,exported_from=matches[0],
        ))
    return tuple(dict.fromkeys(resolved))
