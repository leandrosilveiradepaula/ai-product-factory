#!/usr/bin/env python3
"""OWNER-only event for rotating an already human-merged source candidate.

Never merges PRs, starts Product Stages, spends model budget or grants access.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re

from ai_product_factory.released_existing_candidate import rotate_released_one

_FACTORY = "leandrosilveiradepaula/ai-product-factory"
_OWNER = "leandrosilveiradepaula"
_CMD = re.compile(
    r"/factory-rotate-released-candidate ([a-z0-9][a-z0-9-]{0,63}) "
    r"pr=([1-9][0-9]{0,5}) issue=([1-9][0-9]{0,6})\Z",
    re.ASCII,
)


def validate_event(event: object, env: dict[str, str]) -> tuple[str, int, int]:
    if (not isinstance(event, dict) or event.get("action") != "created"
        or env.get("GITHUB_REPOSITORY") != _FACTORY
        or env.get("GITHUB_ACTOR") != _OWNER
        or env.get("GITHUB_REF") != "refs/heads/main"):
        raise PermissionError("invalid OWNER event provenance")
    repo, issue, comment, sender = (
        event.get("repository"),event.get("issue"),
        event.get("comment"),event.get("sender"),
    )
    if (not isinstance(repo, dict) or repo.get("id") != 1387883686
        or repo.get("full_name") != _FACTORY
        or not isinstance(issue, dict) or issue.get("number") != 713
        or issue.get("state") != "open" or issue.get("pull_request") is not None
        or not isinstance(comment, dict)
        or comment.get("author_association") != "OWNER"
        or not isinstance(comment.get("user"),dict)
        or comment["user"].get("id") != 256917842
        or comment["user"].get("login") != _OWNER
        or not isinstance(sender,dict)
        or sender.get("id") != 256917842
        or sender.get("login") != _OWNER):
        raise PermissionError("OWNER comment identity mismatch")
    body=comment.get("body")
    match=_CMD.fullmatch(body) if isinstance(body,str) and len(body)<180 else None
    if match is None:
        raise PermissionError("not an exact released-source rotation command")
    key,number,issue_number=match.groups()
    return key,int(number),int(issue_number)


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--event-path", required=True)
    parser.add_argument("--check-event", action="store_true")
    parser.add_argument("--output")
    args=parser.parse_args(argv)
    try:
        path=Path(args.event_path)
        if not path.is_file() or path.stat().st_size>128000:
            raise PermissionError("invalid GitHub event file")
        event=json.loads(path.read_text(encoding="utf-8"))
        project,pr,issue=validate_event(event,dict(os.environ))
        if args.check_event:
            print("verified OWNER rotation command; no provider or database accessed")
            return 0
        if not args.output:
            raise PermissionError("rotation artifact path required")
        receipt=rotate_released_one(
            project, candidate_pr_number=pr, issue_number=issue,
        )
        Path(args.output).write_text(
            json.dumps(receipt,sort_keys=True)+"\n", encoding="utf-8",
        )
        print("released-source rotation CAS receipt verified")
        return 0
    except Exception:
        print("::error::released-source rotation refused; inspect approved evidence")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
